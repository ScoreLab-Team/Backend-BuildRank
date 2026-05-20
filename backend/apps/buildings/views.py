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
from apps.buildings.services.badges import get_badges_resum_edifici, recalcular_insignies_edifici
 
from .models import (
    Edifici, Habitatge, Localitzacio, DadesEnergetiques,
    carrersBarcelona, EstatValidacio, RolVinculacioHabitatge, AccioAudit, EdificiAuditLog,
    CatalegMillora, SimulacioMillora, SimulacioMilloraItem, MilloraImplementada,
    EstatAplicacioSimulacio, EstatVotacioSimulacio, SentitVotSimulacio,
    VotacioSimulacioMillora, VotSimulacioMillora, BuildingBadge,
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
    ReclamarEdificiAdminSerializer, VotacioSimulacioMilloraSerializer,
    CrearVotacioSimulacioSerializer, VotarSimulacioSerializer,
    AcreditarSimulacioImplementadaSerializer,
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
            from apps.verification.access import effective_admin_buildings_queryset
            return effective_admin_buildings_queryset(qs, user)
        if role == RoleChoices.OWNER:
            return qs.filter(
                Q(habitatges__usuari=user) |
                Q(habitatges__propietari=user) |
                Q(habitatges__llogater=user)
            ).distinct()
        if role == RoleChoices.TENANT:
            return qs.filter(
                Q(habitatges__usuari=user) |
                Q(habitatges__propietari=user) |
                Q(habitatges__llogater=user)
            ).distinct()
        return Edifici.objects.none()

    def get_serializer_class(self):
        if self.action == 'list':
            return EdificiListSerializer
        return EdificiDetailSerializer  # retrieve, update, create...permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        """
        Crear un edifici no concedeix gestió immediata a l'admin finca.

        La vinculació efectiva s'ha de produir quan la verificació documental
        passa a approved. Això evita que un usuari pugui accedir a l'edifici
        mentre la documentació encara està pending/running/review.
        """
        if self.request.user.is_superuser:
            serializer.save()
        else:
            serializer.save(administradorFinca=None)

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
            habitatges = edifici.habitatges.filter(Q(usuari=request.user) | Q(propietari=request.user) | Q(llogater=request.user))
        
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
            if not habitatge.te_vinculacio(request.user):
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
            habitatges = edifici.habitatges.select_related('dadesEnergetiques').filter(Q(usuari=request.user) | Q(propietari=request.user) | Q(llogater=request.user))

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

    def _es_admin_de_finca_edifici(self, request, edifici):
        if not (
            request.user.is_authenticated
            and hasattr(request.user, 'profile')
            and request.user.profile.role == RoleChoices.ADMIN
        ):
            return False

        from apps.verification.access import admin_assignment_is_effective
        return admin_assignment_is_effective(request.user, edifici)

    def _pot_votar_votacio(self, user, edifici):
        if not user.is_authenticated or not hasattr(user, 'profile'):
            return False

        from apps.verification.access import admin_assignment_is_effective
        if admin_assignment_is_effective(user, edifici):
            return True

        if user.profile.role != RoleChoices.OWNER:
            return False

        return edifici.habitatges.filter(Q(usuari=user) | Q(propietari=user)).exists()

    def _electors_votacio_count(self, edifici):
        admin_count = 1 if edifici.administradorFinca_id else 0
        owners_count = edifici.habitatges.filter(
            usuari__isnull=False,
            usuari__profile__role=RoleChoices.OWNER,
        ).values('usuari').distinct().count()
        return max(admin_count + owners_count, 1)

    def _recalcular_estat_votacio(self, votacio):
        if votacio.estat != EstatVotacioSimulacio.ACTIVA:
            return votacio

        total_electors = self._electors_votacio_count(votacio.edifici)
        total_vots = votacio.total_vots
        vots_favor = votacio.vots_favor

        participacio = (total_vots / total_electors) * 100
        favor = (vots_favor / total_vots) * 100 if total_vots else 0

        ara = timezone.now()

        if participacio >= votacio.quorumPercent and favor >= votacio.majoriaPercent:
            votacio.estat = EstatVotacioSimulacio.APROVADA
            votacio.simulacio.estatAplicacio = EstatAplicacioSimulacio.APROVADA
            votacio.simulacio.votacioAprovadaAt = ara
            votacio.simulacio.save(update_fields=['estatAplicacio', 'votacioAprovadaAt'])
            votacio.save(update_fields=['estat', 'updatedAt'])
            return votacio

        if ara > votacio.dataFi:
            votacio.estat = EstatVotacioSimulacio.REBUTJADA
            votacio.simulacio.estatAplicacio = EstatAplicacioSimulacio.REBUTJADA
            votacio.simulacio.save(update_fields=['estatAplicacio'])
            votacio.save(update_fields=['estat', 'updatedAt'])
            return votacio

        return votacio

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
        methods=['post'],
        url_path=r'simulacions/(?P<simulacio_id>\d+)/sotmetre-votacio',
        permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici],
    )
    def sotmetre_simulacio_votacio(self, request, pk=None, simulacio_id=None):
        edifici = self.get_object()

        if not self._es_admin_de_finca_edifici(request, edifici):
            return Response(
                {"detail": "Només l'administrador de finca de l'edifici pot sotmetre simulacions a votació."},
                status=status.HTTP_403_FORBIDDEN,
            )

        simulacio = get_object_or_404(
            SimulacioMillora.objects.prefetch_related('items__millora'),
            pk=simulacio_id,
            edifici=edifici,
        )

        if hasattr(simulacio, 'votacio'):
            return Response(
                {"detail": "Aquesta simulació ja té una votació associada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if simulacio.estatAplicacio not in (
            EstatAplicacioSimulacio.ESBORRANY,
            EstatAplicacioSimulacio.REBUTJADA,
        ):
            return Response(
                {"detail": "Aquesta simulació no es pot sotmetre a votació en el seu estat actual."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CrearVotacioSimulacioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        data_fi = data.get('dataFi')
        if data_fi is None:
            data_fi = timezone.now() + timezone.timedelta(days=data.get('diesDurada', 14))

        titol = data.get('titol') or simulacio.descripcio or f"Votació simulació {simulacio.id}"

        with transaction.atomic():
            votacio = VotacioSimulacioMillora.objects.create(
                simulacio=simulacio,
                edifici=edifici,
                creadaPer=request.user,
                titol=titol,
                descripcio=data.get('descripcio', ''),
                dataFi=data_fi,
                quorumPercent=data.get('quorumPercent', 75),
                majoriaPercent=data.get('majoriaPercent', 50),
            )

            simulacio.estatAplicacio = EstatAplicacioSimulacio.EN_VOTACIO
            simulacio.save(update_fields=['estatAplicacio'])

        output = VotacioSimulacioMilloraSerializer(
            votacio,
            context={'request': request},
        )
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=['get'],
        url_path='votacions-simulacions',
        permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici],
    )
    def votacions_simulacions(self, request, pk=None):
        edifici = self.get_object()

        votacions = (
            edifici.votacions_simulacions
            .select_related('simulacio', 'edifici', 'creadaPer')
            .prefetch_related('simulacio__items__millora', 'vots')
            .order_by('-createdAt')
        )

        for votacio in votacions:
            self._recalcular_estat_votacio(votacio)

        serializer = VotacioSimulacioMilloraSerializer(
            votacions,
            many=True,
            context={'request': request},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path=r'votacions-simulacions/(?P<votacio_id>\d+)/votar',
        permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici],
    )
    def votar_simulacio(self, request, pk=None, votacio_id=None):
        edifici = self.get_object()

        votacio = get_object_or_404(
            VotacioSimulacioMillora.objects.select_related('edifici', 'simulacio'),
            pk=votacio_id,
            edifici=edifici,
        )

        votacio = self._recalcular_estat_votacio(votacio)

        if votacio.estat != EstatVotacioSimulacio.ACTIVA:
            return Response(
                {"detail": "Aquesta votació ja no està activa."},
                status=status.HTTP_409_CONFLICT,
            )

        if timezone.now() > votacio.dataFi:
            votacio = self._recalcular_estat_votacio(votacio)
            return Response(
                {"detail": "Aquesta votació ha finalitzat."},
                status=status.HTTP_409_CONFLICT,
            )

        if not self._pot_votar_votacio(request.user, edifici):
            return Response(
                {"detail": "No tens permisos per votar en aquesta votació."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = VotarSimulacioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        VotSimulacioMillora.objects.update_or_create(
            votacio=votacio,
            usuari=request.user,
            defaults={'sentit': serializer.validated_data['sentit']},
        )

        votacio = self._recalcular_estat_votacio(votacio)

        output = VotacioSimulacioMilloraSerializer(
            votacio,
            context={'request': request},
        )
        return Response(output.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=['post'],
        url_path=r'simulacions/(?P<simulacio_id>\d+)/acreditar-implementacio',
        permission_classes=[IsAuthenticated, EsAdminOPropietariEdifici],
    )
    def acreditar_implementacio_simulacio(self, request, pk=None, simulacio_id=None):
        edifici = self.get_object()

        if not self._es_admin_de_finca_edifici(request, edifici):
            return Response(
                {"detail": "Només l'administrador de finca pot acreditar l'aplicació d'una simulació aprovada."},
                status=status.HTTP_403_FORBIDDEN,
            )

        simulacio = get_object_or_404(
            SimulacioMillora.objects.prefetch_related('items__millora'),
            pk=simulacio_id,
            edifici=edifici,
        )

        if simulacio.estatAplicacio != EstatAplicacioSimulacio.APROVADA:
            return Response(
                {"detail": "Només es poden acreditar simulacions aprovades per votació."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AcreditarSimulacioImplementadaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        items = list(simulacio.items.select_related('millora'))

        if not items:
            return Response(
                {"detail": "La simulació no té millores associades."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        implementacions = []

        with transaction.atomic():
            for item in items:
                impl = MilloraImplementada.objects.create(
                    simulacio=simulacio,
                    edifici=edifici,
                    millora=item.millora,
                    dataExecucio=data['dataExecucio'],
                    costReal=data['costReal'],
                    documentacioAdjunta=data['documentacioAdjunta'],
                    estatValidacio=EstatValidacio.EN_REVISIO,
                    administradorFinca=request.user,
                )
                implementacions.append(impl)

            # La simulació NO passa a implementada en aquest punt.
            # L'admin de finca només acredita i puja evidències.
            # La validació final la fa l'admin de sistema a /millores-implementades/{id}/validar/.

        output = MilloraImplementadaSerializer(
            implementacions,
            many=True,
            context={'request': request},
        )
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

        serializer = EdificiCercaSerializer(edificis[:15], many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='badges')
    def badges(self, request, pk=None):
        """
        Retorna les insígnies assignades a l'edifici.

        Si s'indica ?temporada=<id>, es retornen:
        - insígnies permanents de l'edifici
        - insígnies estacionals d'aquella temporada

        Sense filtre de temporada, es retornen totes les assignacions visibles.
        """
        edifici = self.get_object()
        temporada_id = request.query_params.get('temporada')

        queryset = (
            BuildingBadge.objects
            .filter(edifici=edifici, badge__activa=True)
            .select_related('badge', 'temporada')
            .order_by('badge__categoria', 'badge__code', '-awarded_at')
        )

        if temporada_id:
            queryset = queryset.filter(
                Q(temporada_id=temporada_id) |
                Q(temporada__isnull=True)
            )

        resultats = []
        for assignacio in queryset:
            resultats.append({
                "id": assignacio.id,
                "code": assignacio.badge.code,
                "nom": assignacio.badge.nom,
                "descripcio": assignacio.badge.descripcio,
                "categoria": assignacio.badge.categoria,
                "scope": assignacio.badge.scope,
                "temporada": assignacio.temporada_id,
                "temporadaNom": assignacio.temporada.nom if assignacio.temporada_id else None,
                "valorSnapshot": (
                    str(assignacio.valor_snapshot)
                    if assignacio.valor_snapshot is not None
                    else None
                ),
                "metadata": assignacio.metadata,
                "awardedAt": assignacio.awarded_at,
            })

        return Response({
            "edifici": edifici.idEdifici,
            "temporada": temporada_id,
            "count": len(resultats),
            "summary": get_badges_resum_edifici(edifici, temporada=temporada_id, limit=3),
            "results": resultats,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='badges/recalcular')
    def recalcular_badges(self, request, pk=None):
        """
        Recalcula les insígnies de l'edifici.

        Només ho pot fer:
        - administrador de sistema / staff / superuser
        - administrador de finca de l'edifici
        """
        edifici = self.get_object()
        user = request.user

        is_system_admin = bool(user.is_staff or user.is_superuser)
        from apps.verification.access import admin_assignment_is_effective
        is_finca_admin = admin_assignment_is_effective(user, edifici)

        if not (is_system_admin or is_finca_admin):
            return Response(
                {"detail": "No tens permisos per recalcular les insígnies d'aquest edifici."},
                status=status.HTTP_403_FORBIDDEN,
            )

        temporada = None
        temporada_id = request.data.get("temporada") or request.query_params.get("temporada")

        if temporada_id:
            from apps.seasons.models import Temporada
            temporada = get_object_or_404(Temporada, pk=temporada_id)

        assignades = recalcular_insignies_edifici(edifici, temporada=temporada)

        return Response(
            {
                "edifici": edifici.idEdifici,
                "temporada": getattr(temporada, "pk", None),
                "count": len(assignades),
                "summary": get_badges_resum_edifici(edifici, temporada=temporada, limit=5),
            },
            status=status.HTTP_200_OK,
        )



class MilloraImplementadaViewSet(viewsets.GenericViewSet):
    queryset = MilloraImplementada.objects.select_related("millora", "edifici", "simulacio")
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
        # El camp conserva el nom històric administradorFinca, però aquí desa
        # l'usuari que ha fet la validació final. Per permisos, només pot ser admin sistema.
        millora_impl.administradorFinca = request.user
        millora_impl.save(update_fields=["estatValidacio", "observacionsAdmin", "administradorFinca"])

        if nou_estat == EstatValidacio.VALIDADA and millora_impl.simulacio_id:
            hi_ha_pendents_o_rebutjades = millora_impl.simulacio.implementacions_generades.exclude(
                estatValidacio=EstatValidacio.VALIDADA
            ).exists()

            if not hi_ha_pendents_o_rebutjades:
                millora_impl.simulacio.estatAplicacio = EstatAplicacioSimulacio.IMPLEMENTADA
                millora_impl.simulacio.save(update_fields=["estatAplicacio"])

        output_serializer = MilloraImplementadaSerializer(millora_impl)
        try:
            millora_validada = getattr(output_serializer, "instance", None)
            if millora_validada and getattr(millora_validada, "edifici_id", None):
                recalcular_insignies_edifici(millora_validada.edifici)
        except Exception:
            # El recalcul de badges no ha de bloquejar la validació d'una millora.
            pass

        return Response(output_serializer.data, status=status.HTTP_200_OK)



class HabitatgeViewSet(viewsets.ModelViewSet):
    queryset = Habitatge.objects.all()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'profile'):
            return Habitatge.objects.none()

        # Excepció per US-H2:
        # Permetem trobar l'habitatge si l'acció és sol·licitar-hi accés.
        if self.action == 'solicitar_acces':
            return Habitatge.objects.all()

        role = user.profile.role
        if role == RoleChoices.ADMIN:
            return Habitatge.objects.filter(edifici__administradorFinca=user)

        if role in (RoleChoices.OWNER, RoleChoices.TENANT):
            return Habitatge.objects.filter(
                Q(usuari=user) |
                Q(propietari=user) |
                Q(llogater=user)
            ).distinct()

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
    
    def create(self, request, *args, **kwargs):
        refCadastral = request.data.get('referenciaCadastral')
        edificiID = request.data.get('edifici')

        if not refCadastral:
            return Response({"error": "La referència cadastral és obligatòria."}, status=status.HTTP_400_BAD_REQUEST)

        if not hasattr(request.user, 'profile'):
            return Response({"error": "Usuari sense perfil funcional."}, status=status.HTTP_403_FORBIDDEN)

        role = request.user.profile.role
        if role not in (RoleChoices.OWNER, RoleChoices.TENANT):
            return Response(
                {"error": "Només propietaris i llogaters poden sol·licitar accés a un habitatge."},
                status=status.HTTP_403_FORBIDDEN,
            )

        rol_solicitat = (
            RolVinculacioHabitatge.OWNER
            if role == RoleChoices.OWNER
            else RolVinculacioHabitatge.TENANT
        )

        habitatge = Habitatge.objects.filter(referenciaCadastral=refCadastral).first()

        if habitatge:
            ocupant_actual_id = (
                habitatge.propietari_id or habitatge.usuari_id
                if rol_solicitat == RolVinculacioHabitatge.OWNER
                else habitatge.llogater_id
            )

            if ocupant_actual_id and ocupant_actual_id != request.user.id:
                return Response(
                    {"error": "Aquest rol ja està validat per a aquest habitatge."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if habitatge.solicitant and habitatge.solicitant != request.user:
                return Response(
                    {"error": "Aquest habitatge ja té una sol·licitud d'accés pendent de revisió per part d'un altre usuari."},
                    status=status.HTTP_409_CONFLICT
                )

            habitatge.solicitant = request.user
            habitatge.rolSolicitat = rol_solicitat
            habitatge.estatValidacio = EstatValidacio.EN_REVISIO

            if edificiID:
                habitatge.edifici_id = edificiID

            habitatge.save(update_fields=['solicitant', 'rolSolicitat', 'estatValidacio', 'edifici'])
            serializer = self.get_serializer(habitatge)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        if self.request.user.profile.role == RoleChoices.ADMIN:
            raise PermissionDenied("Els administradors de finca no poden crear habitatges.")

        role = self.request.user.profile.role
        if role not in (RoleChoices.OWNER, RoleChoices.TENANT):
            raise PermissionDenied("Només propietaris i llogaters poden sol·licitar habitatges.")

        rol_solicitat = (
            RolVinculacioHabitatge.OWNER
            if role == RoleChoices.OWNER
            else RolVinculacioHabitatge.TENANT
        )

        try:
            serializer.save(
                solicitant=self.request.user,
                rolSolicitat=rol_solicitat,
                estatValidacio=EstatValidacio.EN_REVISIO,
            )
        except IntegrityError:
            raise serializers.ValidationError(
                {"referenciaCadastral": "Ja existeix un habitatge amb aquesta referència cadastral."}
            )

    @action(detail=True, methods=['post'], url_path='solicitar-acces')
    def solicitar_acces(self, request, pk=None):
        # Sol·licitud de vincular-se a aquest habitatge com a propietari o llogater.
        habitatge = self.get_object()

        if not hasattr(request.user, 'profile'):
            return Response({"error": "Usuari sense perfil funcional."}, status=status.HTTP_403_FORBIDDEN)

        role = request.user.profile.role
        if role not in (RoleChoices.OWNER, RoleChoices.TENANT):
            return Response(
                {"error": "Només propietaris i llogaters poden sol·licitar accés a un habitatge."},
                status=status.HTTP_403_FORBIDDEN,
            )

        rol_solicitat = (
            RolVinculacioHabitatge.OWNER
            if role == RoleChoices.OWNER
            else RolVinculacioHabitatge.TENANT
        )

        ocupant_actual_id = (
            habitatge.propietari_id or habitatge.usuari_id
            if rol_solicitat == RolVinculacioHabitatge.OWNER
            else habitatge.llogater_id
        )

        if ocupant_actual_id and ocupant_actual_id != request.user.id:
            return Response(
                {"detail": "Aquest rol ja està validat per a aquest habitatge."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if habitatge.solicitant and habitatge.solicitant != request.user:
            return Response(
                {"error": "Ja hi ha una sol·licitud pendent per aquest habitatge."},
                status=status.HTTP_409_CONFLICT
            )

        habitatge.estatValidacio = EstatValidacio.EN_REVISIO
        habitatge.solicitant = request.user
        habitatge.rolSolicitat = rol_solicitat
        habitatge.save(update_fields=['estatValidacio', 'solicitant', 'rolSolicitat'])

        return Response(
            {
                "detail": "Sol·licitud enviada correctament.",
                "rolSolicitat": rol_solicitat,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=True, methods=['post'], url_path='validar-acces')
    def validar_acces(self, request, pk=None):
        # L'administrador de finca aprova o rebutja la sol·licitud.
        habitatge = self.get_object()

        if habitatge.edifici.administradorFinca != request.user:
            return Response(
                {"error": "No tens permisos per validar accessos en aquest edifici."},
                status=status.HTTP_403_FORBIDDEN
            )

        if habitatge.estatValidacio != EstatValidacio.EN_REVISIO or not habitatge.solicitant:
            return Response(
                {"error": "Aquest habitatge no té cap sol·licitud pendent de revisió."},
                status=status.HTTP_400_BAD_REQUEST
            )

        nouEstat = request.data.get('estat')

        rol_solicitat = habitatge.rolSolicitat
        if not rol_solicitat and hasattr(habitatge.solicitant, 'profile'):
            if habitatge.solicitant.profile.role == RoleChoices.OWNER:
                rol_solicitat = RolVinculacioHabitatge.OWNER
            elif habitatge.solicitant.profile.role == RoleChoices.TENANT:
                rol_solicitat = RolVinculacioHabitatge.TENANT

        if rol_solicitat not in (RolVinculacioHabitatge.OWNER, RolVinculacioHabitatge.TENANT):
            return Response(
                {"error": "No es pot determinar si la sol·licitud és de propietari o llogater."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if nouEstat == EstatValidacio.VALIDADA:
            ocupant_actual_id = (
                habitatge.propietari_id or habitatge.usuari_id
                if rol_solicitat == RolVinculacioHabitatge.OWNER
                else habitatge.llogater_id
            )

            if ocupant_actual_id and ocupant_actual_id != habitatge.solicitant_id:
                return Response(
                    {"error": "Aquest rol ja està ocupat per un altre usuari."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            habitatge.rolSolicitat = rol_solicitat
            habitatge.assignar_solicitant_validat()
            habitatge.estatValidacio = EstatValidacio.VALIDADA
            habitatge.solicitant = None
            habitatge.rolSolicitat = None
            habitatge.save(update_fields=[
                'usuari',
                'propietari',
                'llogater',
                'estatValidacio',
                'solicitant',
                'rolSolicitat',
            ])

            return Response(
                {"message": "Sol·licitud aprovada. Vinculació assignada correctament."},
                status=status.HTTP_200_OK
            )

        elif nouEstat == EstatValidacio.REBUTJADA:
            te_vinculacio_validada = bool(
                habitatge.usuari_id or habitatge.propietari_id or habitatge.llogater_id
            )

            habitatge.estatValidacio = (
                EstatValidacio.VALIDADA
                if te_vinculacio_validada
                else EstatValidacio.REBUTJADA
            )
            habitatge.solicitant = None
            habitatge.rolSolicitat = None
            habitatge.save(update_fields=['estatValidacio', 'solicitant', 'rolSolicitat'])

            return Response({"detail": "Sol·licitud rebutjada."}, status=status.HTTP_200_OK)

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
            return DadesEnergetiques.objects.filter(
            Q(dades_energetiques__usuari=user) |
            Q(dades_energetiques__propietari=user) |
            Q(dades_energetiques__llogater=user)
        ).distinct()
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
            
            # No assignem encara: cal verificació documental approved.
            return Response(
                {
                    "message": (
                        "Edifici localitzat. Per administrar-lo cal completar "
                        "i aprovar la verificació documental."
                    ),
                    "edifici_id": edifici.idEdifici,
                    "requereix_verificacio": True,
                },
                status=status.HTTP_200_OK,
            )
        
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
            reglament=data.get('reglament'),
            orientacioPrincipal=data.get('orientacioPrincipal'),
            administradorFinca=None,
        )

        return Response(
            {
                "message": (
                    "Edifici creat. Per administrar-lo cal completar "
                    "i aprovar la verificació documental."
                ),
                "edifici_id": nouEdifici.idEdifici,
                "requereix_verificacio": True,
            },
            status=status.HTTP_201_CREATED
        )
