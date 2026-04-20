# apps/buildings/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, action
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.permissions import ABACMixin, IsAdminSistema
from apps.accounts.models import RoleChoices
 
from .models import (
    Edifici, Habitatge, Localitzacio, DadesEnergetiques,
    carrersBarcelona, EstatValidacio, AccioAudit, EdificiAuditLog,
)
from .serializers import (
    EdificiDetailSerializer, EdificiListSerializer,
    HabitatgeDetailSerializer, HabitatgeResumSerializer,
    LocalitzacioSerializer, DadesEnergetiquesSerializer,
    RankingSerializer,
)
from .permissions import (
    EsAdminEdifici,
    EsAdminOPropietariEdifici,
    EsAdminOPropietariHabitatge,
    EsOwnerOAdminHabitatge,
    EsOwnerOAdminDadesEnergetiques,
)
from .pagination import RankingPaginacio
 
 
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
        estatValidacio=EstatValidacio.EN_PROCES
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

class HabitatgeViewSet(viewsets.ModelViewSet):
    queryset = Habitatge.objects.all()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'profile'):
            return Habitatge.objects.none()

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
        serializer = EdificiDetailSerializer(data=request.data)
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
def autocomplete_carrers(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return Response([])

    resultados = (carrersBarcelona.objects
                  .filter(nom_oficial__icontains=query)
                  .values('nom_oficial', 'tipus_via', 'nre_min', 'nre_max')
                  .distinct()[:5])

    return Response(list(resultados))

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