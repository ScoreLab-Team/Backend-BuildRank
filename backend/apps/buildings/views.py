# apps/buildings/views.py
import random

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, action, permission_classes
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import IntegrityError
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.accounts.permissions import ABACMixin, IsAdminSistema, IsAdminFinca
from apps.accounts.models import RoleChoices, ValidacioAdmin
 
from .models import (
    Edifici, Habitatge, Localitzacio, DadesEnergetiques,
    carrersBarcelona, EstatValidacio, AccioAudit, EdificiAuditLog,
    CatalegMillora, SimulacioMillora, SimulacioMilloraItem, MilloraImplementada,
)
from .serializers import (
    EdificiDetailSerializer, EdificiListSerializer, EdificiMapSerializer,
    EdificiCercaSerializer,
    HabitatgeDetailSerializer, HabitatgeMeUpdateSerializer, HabitatgeResumSerializer,
    LocalitzacioSerializer, DadesEnergetiquesSerializer,
    RankingSerializer,
    CatalegMilloraSerializer,
    SimulacioMilloraPreviewSerializer,
    SimulacioMilloraSerializer, MilloraImplementadaSerializer,
    ValidacioMilloraSerializer,
    ReclamarEdificiAdminSerializer,
)
from .permissions import (
    EsAdminEdifici,
    EsAdminOPropietariEdifici,
    EsAdminOPropietariHabitatge,
    EsOwnerOAdminHabitatge,
    EsOwnerOAdminDadesEnergetiques,
    EsAdminMilloraImplementada,
    HasAPIKey,
    log_denial,
)

from .services.nominatim import NominatimRateLimiter, reverse_geocode, es_barcelona, parse_carrer_numero
from .services.building_lookup import buscar_edifici

from .pagination import RankingPaginacio
from django.db import transaction
from .simulation.engine import simular_millores
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')
 
 
def _registrar_audit(*, edifici, accio, usuari, request,
                     camps_modificats=None, motiu=''):
    """
    Crea un registre a EdificiAuditLog.
    Centralitzat aquí per reutilitzar-lo des de qualsevol viewset.
    """
    EdificiAuditLog.objects.create(
        edifici=edifici,
        edifici_id_snapshot=edifici.idEdifici,
        accio=accio,
        usuari=usuari,
        camps_modificats=camps_modificats,
        motiu=motiu,
        ip=_get_client_ip(request),
    )
 
 
def _validar_consistencia_desactivacio(edifici):
    """
    Comprova inconsistències abans de desactivar un edifici.
    Retorna una llista d'advertències (strings).
    Si hi ha blocadors retorna-los com advertències crítiques
    (la vista decideix si blocar o no).
    """
    advertencies = []
 
    # 1. Millores implementades en procés
    millores_pendents = edifici.implementacions.filter(
        estatValidacio=EstatValidacio.EN_REVISIO
    ).count()
    if millores_pendents:
        advertencies.append(
            f"Hi ha {millores_pendents} millora(es) implementada(es) en procés de validació."
        )
 
    # 2. Simulacions actives (creades en els últims 90 dies)
    limit_simulacions = timezone.now().date() - timezone.timedelta(days=90)
    simulacions_recents = edifici.simulacions.filter(
        dataSimulacio__gte=limit_simulacions
    ).count()
    if simulacions_recents:
        advertencies.append(
            f"Hi ha {simulacions_recents} simulació(ons) de millora dels últims 90 dies."
        )
 
    # 3. Habitatges amb usuaris assignats
    habitatges_ocupats = edifici.habitatges.filter(usuari__isnull=False).count()
    if habitatges_ocupats:
        advertencies.append(
            f"Hi ha {habitatges_ocupats} habitatge(s) amb usuaris assignats."
        )
 
    return advertencies


# ---------------------------------------------------------------------------
# ViewSets
# ---------------------------------------------------------------------------

class CatalegMilloraViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Endpoint de catàleg de millores per al frontend.
    Permet listar i consultar les millores actives disponibles per simular.
    """
    serializer_class = CatalegMilloraSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = CatalegMillora.objects.filter(activa=True)

        categoria = self.request.query_params.get("categoria")
        if categoria:
            queryset = queryset.filter(categoria=categoria)

        return queryset.order_by("categoria", "nom")

class EdificiViewSet(viewsets.ModelViewSet):
    queryset = Edifici.objects.all()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'profile'):
            return Edifici.objects.none()

        # Superuser veu tots (inclosos desactivats si ho demana)
        if user.is_superuser:
            inclou_desactivats = (
                self.request.query_params.get('inclou_desactivats', 'false').lower() == 'true'
            )
            return Edifici.objects.all() if inclou_desactivats else Edifici.actius.all()

        role = user.profile.role
        qs = Edifici.actius.all()
        if role == RoleChoices.ADMIN:
            return qs.filter(administradorFinca=user)
        if role == RoleChoices.OWNER:
            return qs.filter(habitatges__usuari=user).distinct()
        if role == RoleChoices.TENANT:
            return qs.filter(habitatges__usuari=user).distinct()
        return Edifici.objects.none()

    def get_serializer_class(self):
        if self.action == 'list':
            return EdificiListSerializer
        return EdificiDetailSerializer  # retrieve, update, create...permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        """
        Quan un administrador de finca crea un edifici, el backend el vincula
        automàticament a l'usuari autenticat. El frontend no ha d'enviar
        administradorFinca manualment.
        """
        serializer.save(administradorFinca=self.request.user)

    def get_permissions(self):
        if self.action in ['destroy']:
            return [IsAuthenticated(), EsAdminEdifici()]
        elif self.action in ['create']:
            return [IsAuthenticated(), EsAdminEdifici()]
        elif self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), EsAdminEdifici()]
        elif self.action in ['retrieve', 'dades_energetiques', 'habitatge_detail']:
            return [IsAuthenticated(), EsAdminOPropietariEdifici()]
        elif self.action in ['list', 'habitatges']:
            return [IsAuthenticated(), EsAdminOPropietariEdifici()]
        elif self.action in ['desactivar', 'reactivar']:
            return [IsAuthenticated(), IsAdminSistema()]  # 
        return [IsAuthenticated()]  # per defecte, només autenticats poden accedir 
    
     # ------------------------------------------------------------------
    # US20 — Task #169 + #170 + #171
    # POST /edificis/{id}/desactivar/
    #
    # Sense paràmetres addicionals → DRY-RUN (#170): retorna advertències
    # ?confirmat=true             → executa la desactivació (#169 + #171)
    # Body opcional: { "motiu": "..." }
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticated, IsAdminSistema])
    def desactivar(self, request, pk=None):        
        edifici = self.get_object()
 
        if not edifici.actiu:
            return Response(
                {"detail": "L'edifici ja està desactivat."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        # Validació de consistència (#171)
        advertencies = _validar_consistencia_desactivacio(edifici)
        confirmat = request.query_params.get('confirmat', 'false').lower() == 'true'
 
        # --- DRY-RUN (#170): retorna advertències sense executar ---
        if not confirmat:
            return Response(
                {
                    "detail": (
                        "Revisió prèvia. Afegeix ?confirmat=true per executar la desactivació."
                    ),
                    "edifici_id": edifici.idEdifici,
                    "advertencies": advertencies,
                    "pot_desactivar": True,  # En aquest projecte les advertències no bloquen
                },
                status=status.HTTP_200_OK,
            )
 
        # --- Execució real (#169) ---
        motiu = request.data.get('motiu', '').strip()
 
        # Snapshot dels camps que canvien (per a l'audit)
        camps_modificats = {
            "actiu":             [True, False],
            "dataDesactivacio":  [None, timezone.now().isoformat()],
            "motivDesactivacio": [edifici.motivDesactivacio or '', motiu],
        }
 
        edifici.actiu = False
        edifici.dataDesactivacio = timezone.now()
        edifici.motivDesactivacio = motiu
        edifici.save(update_fields=['actiu', 'dataDesactivacio', 'motivDesactivacio'])
 
        # Registre d'auditoria (#171)
        _registrar_audit(
            edifici=edifici,
            accio=AccioAudit.DESACTIVAR,
            usuari=request.user,
            request=request,
            camps_modificats=camps_modificats,
            motiu=motiu,
        )
 
        return Response(
            {
                "detail": f"Edifici {edifici.idEdifici} desactivat correctament.",
                "edifici_id": edifici.idEdifici,
                "dataDesactivacio": edifici.dataDesactivacio,
                "motiu": edifici.motivDesactivacio,
                "advertencies_en_el_moment": advertencies,
            },
            status=status.HTTP_200_OK,
        )
 
    # ------------------------------------------------------------------
    # US20 — Reactivació
    # POST /edificis/{id}/reactivar/
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'],
            permission_classes=[IsAuthenticated, IsAdminSistema])
    def reactivar(self, request, pk=None):
        # Hem de buscar entre TOTS els edificis (inclosos desactivats)
        edifici = get_object_or_404(Edifici.objects.all(), pk=pk)
 
        if edifici.actiu:
            return Response(
                {"detail": "L'edifici ja està actiu."},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        motiu = request.data.get('motiu', '').strip()
 
        camps_modificats = {
            "actiu":             [False, True],
            "dataDesactivacio":  [edifici.dataDesactivacio.isoformat()
                                  if edifici.dataDesactivacio else None, None],
            "motivDesactivacio": [edifici.motivDesactivacio, ''],
        }
 
        edifici.actiu = True
        edifici.dataDesactivacio = None
        edifici.motivDesactivacio = ''
        edifici.save(update_fields=['actiu', 'dataDesactivacio', 'motivDesactivacio'])
 
        _registrar_audit(
            edifici=edifici,
            accio=AccioAudit.REACTIVAR,
            usuari=request.user,
            request=request,
            camps_modificats=camps_modificats,
            motiu=motiu,
        )
 
        return Response(
            {
                "detail": f"Edifici {edifici.idEdifici} reactivat correctament.",
                "edifici_id": edifici.idEdifici,
            },
            status=status.HTTP_200_OK,
        )

    # GET /edificis/{id}/habitatges/
    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici])
    def habitatges(self, request, pk=None):
        edifici = self.get_object()

        if request.user.profile.role == RoleChoices.ADMIN:
            habitatges = edifici.habitatges.all()
        else:
            habitatges = edifici.habitatges.filter(usuari=request.user)
        
        serializer = HabitatgeResumSerializer(habitatges, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici],
        url_path='habitatges/(?P<referenciaCadastral>[A-Za-z0-9]+)')
    def habitatge_detail(self, request, pk=None, referenciaCadastral=None):
        edifici = self.get_object()

        try:
            habitatge = edifici.habitatges.get(referenciaCadastral=referenciaCadastral)
        except Habitatge.DoesNotExist:
            return Response({"detail": "Habitatge no trobat."}, status=404)

        # Propietari només pot veure el seu
        if edifici.administradorFinca != request.user:
            if habitatge.usuari != request.user:
                return Response({"detail": "No tens permisos."}, status=403)

        serializer = HabitatgeDetailSerializer(habitatge, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], permission_classes=[EsAdminOPropietariEdifici])
    def dades_energetiques(self, request, pk=None):
        edifici = self.get_object()  # ja aplica check_object_permissions automàticament

        # Filtrem segons rol
        if edifici.administradorFinca == request.user:
            habitatges = edifici.habitatges.select_related('dadesEnergetiques').all()
        else:
            habitatges = edifici.habitatges.select_related('dadesEnergetiques').filter(usuari=request.user)

        dades = []
        for habitatge in habitatges:
            if habitatge.dadesEnergetiques:
                serializer = DadesEnergetiquesSerializer(
                    habitatge.dadesEnergetiques,
                    context={'request': request}
                )
                dades.append({
                    "habitatge": f"{habitatge.planta}-{habitatge.porta}",
                    "referenciaCadastral": habitatge.referenciaCadastral,
                    "dadesEnergetiques": serializer.data
                })

        if not dades:
            return Response({"detail": "No hi ha dades energètiques disponibles."}, status=404)

        return Response(dades)
    @action(
        detail=True,
        methods=['patch'],
        url_path='me/habitatge/(?P<referenciaCadastral>[A-Za-z0-9]+)',
        permission_classes=[IsAuthenticated],
    )
    def me_habitatge(self, request, pk=None, referenciaCadastral=None):
        edifici = get_object_or_404(Edifici, pk=pk)

        habitatge = get_object_or_404(
            Habitatge.objects.select_related('dadesEnergetiques', 'edifici'),
            edifici=edifici,
            usuari=request.user,
            referenciaCadastral=referenciaCadastral,
        )

        serializer = HabitatgeMeUpdateSerializer(
            habitatge,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        output = HabitatgeDetailSerializer(habitatge, context={'request': request})
        return Response(output.data, status=status.HTTP_200_OK)
    
    def _preparar_items_simulacio(self, millores_validated):
        """
        Converteix l'entrada validada del serializer en objectes reals del catàleg.
        """
        ids = [item["milloraId"] for item in millores_validated]
        millores_map = {
            millora.idMillora: millora
            for millora in CatalegMillora.objects.filter(idMillora__in=ids, activa=True)
        }

        items = []
        for item in millores_validated:
            millora = millores_map[item["milloraId"]]
            items.append({
                "millora": millora,
                "quantitat": item.get("quantitat"),
                "coberturaPercent": item.get("coberturaPercent", 100),
            })

        return items

    @action(
        detail=True,
        methods=['post'],
        url_path='simulacions/preview',
        permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici]
    )
    def simulacions_preview(self, request, pk=None):
        """
        Preview de simulació.
        No guarda res a la base de dades.
        Pensat perquè Flutter pugui mostrar una comparativa abans/després.
        """
        edifici = self.get_object()

        serializer = SimulacioMilloraPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items = self._preparar_items_simulacio(serializer.validated_data["millores"])
        resultat = simular_millores(edifici, items)

        return Response(resultat, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['get', 'post'],
        url_path='simulacions',
        permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici]
    )
    def simulacions(self, request, pk=None):
        """
        GET: llista simulacions guardades de l'edifici.
        POST: calcula i guarda una simulació.
        """
        edifici = self.get_object()

        if request.method == 'GET':
            simulacions = (
                edifici.simulacions
                .prefetch_related("items__millora")
                .order_by("-dataSimulacio", "-id")
            )
            serializer = SimulacioMilloraSerializer(simulacions, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = SimulacioMilloraPreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        items = self._preparar_items_simulacio(serializer.validated_data["millores"])
        resultat = simular_millores(edifici, items)

        with transaction.atomic():
            simulacio = SimulacioMillora.objects.create(
                descripcio=serializer.validated_data.get("descripcio", ""),
                edifici=edifici,
                creadaPer=request.user,
                versioMotor=resultat["versioMotor"],
                reduccioConsumPrevista=resultat["delta"]["reduccioConsumKwhAny"],
                reduccioEmissionsPrevista=resultat["delta"]["reduccioEmissionsKgCO2Any"],
                costEstimat=resultat["delta"]["costTotalEstimat"],
                estalviAnual=resultat["delta"]["estalviAnualEstimatiu"],
                hipotesiBase=resultat["abans"],
                resultat=resultat,
                millora=items[0]["millora"] if len(items) == 1 else None,
            )

            resultat_items = resultat.get("items", [])
            for item_input, item_resultat in zip(items, resultat_items):
                SimulacioMilloraItem.objects.create(
                    simulacio=simulacio,
                    millora=item_input["millora"],
                    quantitat=item_resultat.get("quantitatAplicada"),
                    coberturaPercent=item_resultat.get("coberturaPercent", item_input.get("coberturaPercent", 100)),
                    costEstimatParcial=item_resultat.get("costEstimat", 0),
                    reduccioConsumParcial=item_resultat.get("reduccioConsumKwhAny", 0),
                    reduccioEmissionsParcial=item_resultat.get("reduccioEmissionsKgCO2Any", 0),
                    impactePuntsParcial=item_resultat.get("impactePunts", 0),
                    resultatParcial=item_resultat,
                )

        output = SimulacioMilloraSerializer(simulacio)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=["get"],
        url_path="millores-implementades",
        permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici],
    )
    def millores_implementades(self, request, pk=None):
        edifici = self.get_object()

        implementacions = (
            edifici.implementacions
            .select_related("millora")
            .order_by("-dataExecucio", "-id")
        )

        serializer = MilloraImplementadaSerializer(implementacions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @action(
        detail=False,
        methods=["get"],
        url_path="mapa",
        permission_classes=[IsAuthenticated],
    )
    def mapa(self, request):
        """
        GET /api/buildings/edificis/mapa/

        Retorna els edificis actius amb coordenades vàlides en format GeoJSON.

        Query params opcionals:
        - scope=public|mine
        - bbox=minLng,minLat,maxLng,maxLat
        - tipologia=Residencial
        - score_min=60
        - q=text
        - limit=500
        """
        scope = request.query_params.get("scope", "public").lower().strip()

        if scope == "mine":
            queryset = self.get_queryset()
        else:
            queryset = Edifici.actius.all()

        queryset = (
            queryset
            .select_related("localitzacio", "grupComparable")
            .filter(
                localitzacio__isnull=False,
                localitzacio__latitud__isnull=False,
                localitzacio__longitud__isnull=False,
            )
            .exclude(localitzacio__latitud=0.0)
            .exclude(localitzacio__longitud=0.0)
        )

        tipologia = request.query_params.get("tipologia")
        if tipologia:
            queryset = queryset.filter(tipologia=tipologia)

        search = request.query_params.get("q", "").strip()
        if search:
            queryset = queryset.filter(
                Q(localitzacio__carrer__icontains=search)
                | Q(localitzacio__barri__icontains=search)
                | Q(localitzacio__codiPostal__icontains=search)
            )

        score_min_raw = request.query_params.get("score_min")
        if score_min_raw:
            try:
                score_min = float(score_min_raw)
            except ValueError:
                return Response(
                    {"detail": "El paràmetre score_min ha de ser numèric."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(
                Q(puntuacioBase__gte=score_min)
                | Q(puntuacioBaseOpenData__gte=score_min)
            )

        bbox_raw = request.query_params.get("bbox")
        if bbox_raw:
            try:
                min_lng, min_lat, max_lng, max_lat = [
                    float(value.strip())
                    for value in bbox_raw.split(",")
                ]
            except ValueError:
                return Response(
                    {
                        "detail": (
                            "El paràmetre bbox ha de tenir el format "
                            "minLng,minLat,maxLng,maxLat."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            queryset = queryset.filter(
                localitzacio__longitud__gte=min_lng,
                localitzacio__longitud__lte=max_lng,
                localitzacio__latitud__gte=min_lat,
                localitzacio__latitud__lte=max_lat,
            )

        limit_raw = request.query_params.get("limit", "500")
        try:
            limit = int(limit_raw)
        except ValueError:
            return Response(
                {"detail": "El paràmetre limit ha de ser un enter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = max(1, min(limit, 1000))

        total = queryset.count()
        queryset = queryset.order_by("idEdifici")[:limit]

        serializer = EdificiMapSerializer(
            queryset,
            many=True,
            context={"request": request},
        )

        return Response(
            {
                "type": "FeatureCollection",
                "count": total,
                "features": serializer.data,
                "meta": {
                    "scope": scope,
                    "limit": limit,
                    "truncated": total > limit,
                },
            },
            status=status.HTTP_200_OK,
        )
    
    @action(detail=False, methods=['get'], url_path='cerca')
    def cerca_per_carrer(self, request):
        """
        Endpoint per buscar edificis pel nom del carrer.
        """
        query = request.query_params.get('q', '')

        if not query or len(query) < 3:
            return Response([])
        
        edificis = Edifici.objects.filter(
            localitzacio__carrer__icontains=query
        ).select_related('localitzacio').distinct()

        serializer = EdificiCercaSerializer(edificis, many=True)
        return Response(serializer.data)

class MilloraImplementadaViewSet(viewsets.GenericViewSet):
    queryset = MilloraImplementada.objects.select_related("millora", "edifici")
    serializer_class = MilloraImplementadaSerializer
    permission_classes = [IsAuthenticated, EsAdminMilloraImplementada]

    @action(detail=True, methods=["post"], url_path="validar")
    def validar(self, request, pk=None):
        millora_impl = self.get_object()

        input_serializer = ValidacioMilloraSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)

        nou_estat = input_serializer.validated_data["estatValidacio"]
        observacions = input_serializer.validated_data.get("observacionsAdmin", "")

        if millora_impl.estatValidacio not in (
            EstatValidacio.PENDENT_DOCUMENTACIO, EstatValidacio.EN_REVISIO
        ):
            return Response(
                {"detail": "Només es poden validar millores en estat 'PendentDocumentacio' o 'EnRevisió'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        millora_impl.estatValidacio = nou_estat
        millora_impl.observacionsAdmin = observacions
        millora_impl.administradorFinca = request.user
        millora_impl.save(update_fields=["estatValidacio", "observacionsAdmin", "administradorFinca"])

        output_serializer = MilloraImplementadaSerializer(millora_impl)
        return Response(output_serializer.data, status=status.HTTP_200_OK)


class HabitatgeViewSet(viewsets.ModelViewSet):
    queryset = Habitatge.objects.all()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'profile'):
            return Habitatge.objects.none()

        # Excepció per US-H2
        # Permetem que qualsevol usuari trobi l'habitatge si el que vol és sol·licitar-hi accés
        if self.action == 'solicitar_acces':
            return Habitatge.objects.all()

        role = user.profile.role
        if role == RoleChoices.ADMIN:
            return Habitatge.objects.filter(edifici__administradorFinca=user)
        if role in (RoleChoices.OWNER, RoleChoices.TENANT):
            return Habitatge.objects.filter(usuari=user)
        return Habitatge.objects.none()

    def get_serializer_class(self):
        if self.action == 'list':
            return HabitatgeResumSerializer
        return HabitatgeDetailSerializer
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), EsOwnerOAdminHabitatge()]
        elif self.action == 'retrieve':
            return [IsAuthenticated(), EsAdminOPropietariHabitatge()]
        elif self.action == 'list':
            return [IsAuthenticated(), EsAdminOPropietariHabitatge()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        if self.request.user.profile.role == RoleChoices.ADMIN:
            raise PermissionDenied("Els administradors de finca no poden crear habitatges.")
        try:
            serializer.save(solicitant=self.request.user)
        except IntegrityError:
            raise serializers.ValidationError(
                {"referenciaCadastral": "Ja existeix un habitatge amb aquesta referència cadastral."}
            )

    @action(detail=True, methods=['post'], url_path='solicitar-acces')
    def solicitar_acces(self, request, pk=None):
        # Sol·licitud de vincular-se a aquest habitatge
        habitatge = self.get_object()

        # Comprovar si l'habitatge ja està ocupat per un usuari validat
        if habitatge.usuari:
            return Response(
                {"detail": "Aquest habitatge ja té un resident assignat."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Posem l'estat en revisió i guardem qui és l'usuari que ho demana
        habitatge.estatValidacio = EstatValidacio.EN_REVISIO
        habitatge.solicitant = request.user
        habitatge.save(update_fields=['estatValidacio', 'solicitant'])

        return Response(
            {"detail": "Sol·licitud enviada correctament. Pendent de l'aprovació de l'Administrador."},
            status=status.HTTP_200_OK
        )
    
    @action(detail=True, methods=['post'], url_path='validar-acces')
    def validar_acces(self, request, pk=None):
        # L'Administrador de finca aprova o rebutja la sol·licitud
        habitatge = self.get_object()

        # Només l'admin d'aquest edifici pot validar-ho
        if habitatge.edifici.administradorFinca != request.user:
            return Response(
                {"error": "No tens permisos per validar accessos en aquest edifici."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Comprovem que realment hi hagi algú pendent
        if habitatge.estatValidacio != EstatValidacio.EN_REVISIO or not habitatge.solicitant:
            return Response(
                {"error": "Aquest habitatge no té cap sol·licitud pendent de revisió."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        nouEstat = request.data.get('estat')
        
        if nouEstat == EstatValidacio.VALIDADA:
            habitatge.usuari = habitatge.solicitant
            habitatge.estatValidacio = EstatValidacio.VALIDADA
            habitatge.solicitant = None
            habitatge.save(update_fields=['usuari', 'estatValidacio', 'solicitant'])

            return Response(
                {"message": "Sol·licitud aprovada. Resident assignat."},
                status=status.HTTP_200_OK
            )
        
        elif nouEstat == EstatValidacio.REBUTJADA:
            # habitatge.estatValidacio = EstatValidacio.REBUTJADA
            # habitatge.solicitant = None
            # habitatge.save(update_fields=['estatValidacio', 'solicitant'])

            # decidim eliminar l'habitatge, si la sol·licitud queda rebutjada per l'admin de finca
            habitatge.delete()
            return Response({"message": "Sol·licitud rebutjada i habitatge eliminat."}, status=status.HTTP_204_NO_CONTENT)
        
        return Response({"error": "Estat no vàlid."}, status=status.HTTP_400_BAD_REQUEST)
        
    @action(detail=False, methods=['get'])
    def pendents(self, request):
        # Retorna només els habitatges que estan pendents de validació
        user = request.user
        if getattr(user.profile, 'role', None) != RoleChoices.ADMIN:
            return Response(
                {"detail": "Només els administradors poden veure les sol·licituds pendents."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Busquem habitatges del seu edifici que estiguin EN_REVISIO
        queryset = Habitatge.objects.filter(
            edifici__administradorFinca=user,
            estatValidacio=EstatValidacio.EN_REVISIO
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class LocalitzacioViewSet(viewsets.ModelViewSet):
    queryset = Localitzacio.objects.all()
    serializer_class = LocalitzacioSerializer
    permission_classes = [IsAuthenticated]  # permite POST sin login


class DadesEnergetiquesViewSet(viewsets.ModelViewSet):
    queryset = DadesEnergetiques.objects.all()
    serializer_class = DadesEnergetiquesSerializer

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'profile'):
            return DadesEnergetiques.objects.none()

        role = user.profile.role
        if role == RoleChoices.ADMIN:
            return DadesEnergetiques.objects.filter(dades_energetiques__edifici__administradorFinca=user).distinct()
        if role in (RoleChoices.OWNER, RoleChoices.TENANT):
            return DadesEnergetiques.objects.filter(dades_energetiques__usuari=user).distinct()
        return DadesEnergetiques.objects.none()

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), EsOwnerOAdminDadesEnergetiques()]
        elif self.action in ['list', 'retrieve']:
            return [IsAuthenticated(), EsAdminOPropietariHabitatge()]
        return [IsAuthenticated()]


class EdificisMostrarAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # GET /edificis/mostrar/: Llista tots els edificis
    def get(self, request):
        edificis = Edifici.objects.all()
        serializer = EdificiListSerializer(edificis, many=True)
        return Response(serializer.data)

class EdificiCrearAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # POST /edificis/crear/: Crea un nou edifici
    def post(self, request):
        serializer = EdificiDetailSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save() # Guarda a la base de dades
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class EdificiVeureAPIView(ABACMixin, APIView):
    permission_classes = [IsAuthenticated]

    # GET /edificis/{id}/veure/: Retorna un edifici concret
    def get(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)

        # verificiacio ABAC
        self.check_edifici_access(request, edifici.idEdifici)

        # serializer = EdificiSerializer(edifici)
        serializer = EdificiDetailSerializer(edifici)
        return Response(serializer.data)

class EdificiEditarAPIView(ABACMixin, APIView):
    permission_classes = [IsAuthenticated]

    # PUT /edificis/{id}/editar/: Actualitza tot un edifici
    def put(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)

        # verificiacio ABAC
        self.check_edifici_access(request, edifici.idEdifici)

        # serializer = EdificiSerializer(edifici, data=request.data)
        serializer = EdificiDetailSerializer(edifici, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # PATCH /edificis/{id}/: Actualitza només una part de l'edifici
    def patch(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)

        # verificiacio ABAC
        self.check_edifici_access(request, edifici.idEdifici)

        # el partial=True permet enviar només algunes dades
        serializer = EdificiDetailSerializer(edifici, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class EdificiEsborrarAPIView(ABACMixin, APIView):
    permission_classes = [IsAuthenticated]

    # DELETE /edificis/{id}/esborrar: Esborra un edifici
    def delete(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)

        self.check_edifici_access(request, edifici.idEdifici)

        edifici.delete()
        return Response({"detail": "Edifici esborrat correctament."}, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def autocomplete_carrers(request):
    """
    Suggeriments de carrers per al formulari d'alta d'edifici.

    La cerca és tolerant:
    - cerca a nom_oficial i nom_curt
    - ignora paraules habituals com "carrer", "de", "avinguda"
    - retorna codi_via i codi_carrer_ine per facilitar depuració
    """
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return Response([])

    stopwords = {
        'carrer', 'calle', 'c/', 'c',
        'avinguda', 'avenida', 'av', 'av.',
        'passeig', 'paseo', 'pg', 'pg.',
        'plaça', 'plaza', 'pl', 'pl.',
        'de', 'del', 'la', 'les', 'el', 'els',
    }

    terms = [
        term.strip()
        for term in query.replace(',', ' ').split()
        if term.strip().lower() not in stopwords
    ]

    if not terms:
        terms = [query]

    queryset = carrersBarcelona.objects.all()

    for term in terms:
        queryset = queryset.filter(
            Q(nom_oficial__icontains=term)
            | Q(nom_curt__icontains=term)
            | Q(tipus_via__icontains=term)
        )

    resultats = (
        queryset
        .values(
            'codi_via',
            'codi_carrer_ine',
            'nom_oficial',
            'nom_curt',
            'tipus_via',
            'nre_min',
            'nre_max',
        )
        .order_by('nom_oficial', 'nre_min')
        .distinct()[:10]
    )

    return Response(list(resultats))

class RankingViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RankingSerializer
    pagination_class = RankingPaginacio

    def get_queryset(self):
        queryset = Edifici.objects.all()
        liga = self.request.query_params.get('liga')

        if liga:
            queryset = queryset.filter(liga=liga)

        return queryset.order_by('-score')

    @action(detail=True, methods=['get'])
    def posicion(self, request, pk=None):
        edifici = get_object_or_404(Edifici, pk=pk)

        # Aqui es troba el top que s'utilitza per defecte
        top_n = int(request.query_params.get('top', 5))

        liga_edificis = Edifici.objects.filter(liga=edifici.liga).order_by('-score')

        posicio = liga_edificis.filter(score__gt=edifici.score).count() + 1

        en_top = posicio <= top_n

        puntos_faltantes = 0

        if not en_top:
            # 🔹 obtener el edificio en la posición objetivo
            try:
                objetivo = liga_edificis[top_n - 1]  # índice empieza en 0
                puntos_faltantes = objetivo.score - edifici.score
            except IndexError:
                # si no hay suficientes edificios
                puntos_faltantes = 0

        return Response({
            "edificio_id": edifici.id,
            "liga": edifici.liga,
            "posicion": posicio,
            "top_objetivo": top_n,
            "esta_en_top": en_top,
            "puntos_actuales": edifici.score,
            "puntos_para_top": max(puntos_faltantes, 0)
        })

    '''
    Para el ranking global: GET /ranking/
    Para el ranking en liga especifica: GET /ranking/?liga=oro
    Para el ranking en liga especifica paginado: GET /ranking/?liga=oro&page=2&page_size=10
    Para la informacion individual, top5 por defecto: GET /ranking/{id}/posicion/
    Para la informacion individual con un top especifico: GET /ranking/{id}/posicion/?top=3


    '''



class ThirdPartyServiceView(APIView):
    """
    POST /api/third-party/score/

    Body:
        { "points": [{"lat": 41.38, "lng": 2.17}, ...] }

    Resposta per punt:
        { "lat": 41.38, "lng": 2.17, "score": 73.4, "match_type": "exacta" }
        { "lat": 41.38, "lng": 2.17, "score": 42.0, "match_type": "cap" }   # Score random si no trobat
    """

    permission_classes = [HasAPIKey]

    def post(self, request):
        points = request.data.get("points", [])

        if not isinstance(points, list):
            return Response(
                {"error": "'points' ha de ser una llista."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rate_limiter = NominatimRateLimiter()
        results = []

        for point in points:
            lat = point.get("lat")
            lng = point.get("lng")

            if lat is None or lng is None:
                results.append({
                    "score": round(random.uniform(0, 100), 2),
                    "match_type": "cap",
                })
                continue

            address = reverse_geocode(lat, lng, rate_limiter)
            if address is None or not es_barcelona(address, lat, lng):
                results.append({
                    "lat": lat,
                    "lng": lng,
                    "score": round(random.uniform(0, 100), 2),
                    "match_type": "cap",
                })
                continue

            carrer, numero = parse_carrer_numero(address)
            if not carrer:
                results.append({
                    "lat": lat,
                    "lng": lng,
                    "score": round(random.uniform(0, 100), 2),
                    "match_type": "cap",
                })
                continue

            edifici, match_type = buscar_edifici(carrer, numero)

            if edifici and edifici.puntuacioBase:
                score = round(edifici.puntuacioBase, 2)
            else:
                score = round(random.uniform(0, 100), 2)
                match_type = "cap"

            results.append({
                "score": score,
                "match_type": match_type,
            })

        return Response({"results": results})

# US-AF1: Alta i assignació d'edificis per a Administradors de Finca
class AdminFincaEdificiAltaView(APIView):
    permission_classes = [IsAuthenticated, IsAdminFinca]

    def post(self, request):
        perfil = request.user.profile

        # Validar estat d'activació de l'Admin
        if perfil.estatValidacioAdmin != ValidacioAdmin.APROVAT:
            return Response(
                {"error": "El teu compte d'administrador encara està pendent de validació o ha estat rebutjat."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ReclamarEdificiAdminSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data

        # Buscar si la localització / edifici ja existeix
        loc = Localitzacio.objects.filter(
            carrer__iexact=data['carrer'],
            numero=data['numero'],
            codiPostal=data['codiPostal']
        ).first()

        # Si l'edifici ja existeix
        if loc and hasattr(loc, 'edifici'):
            edifici = loc.edifici

            # Bloquejar si ja té administrador
            if edifici.administradorFinca:
                if edifici.administradorFinca == request.user:
                    return Response({"message": "Ja ets l'administrador d'aquest edifici."}, status=status.HTTP_200_OK)
                
                # Registrem l'intent denegat per auditoria
                log_denial(request, "Vincular edifici", "L'edifici ja té un administrador assignat", edifici.idEdifici)
                return Response(
                    {"error": "Aquest edifici ja té un administrador de finca assignat."}, 
                    status=status.HTTP_409_CONFLICT
                )
            
            # Assignar si existeix però no té admin
            edifici.administradorFinca = request.user
            edifici.save()
            return Response({"message": "Edifici assignat correctament."}, status=status.HTTP_200_OK)
        
        # Si l'edifici no existeix, el creem i l'assignem
        if not loc:
            loc = Localitzacio.objects.create(
                carrer=data['carrer'],
                numero=data['numero'],
                codiPostal=data['codiPostal'],
                barri="Desconegut"
            )

        nouEdifici = Edifici.objects.create(
            localitzacio=loc,
            anyConstruccio=data.get('anyConstruccio'),
            tipologia=data.get('tipologia'),
            superficieTotal=data.get('superficieTotal'),
            administradorFinca=request.user
        )

        return Response(
            {"message": "Edifici creat i assignat correctament.", "edifici_id": nouEdifici.idEdifici}, 
            status=status.HTTP_201_CREATED
        )
