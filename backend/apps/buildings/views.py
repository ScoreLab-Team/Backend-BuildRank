# apps/buildings/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.shortcuts import get_object_or_404

from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, action


from .models import Edifici, Habitatge, Localitzacio, DadesEnergetiques, carrersBarcelona
from .serializers import EdificiDetailSerializer, EdificiListSerializer, HabitatgeDetailSerializer, HabitatgeResumSerializer, LocalitzacioSerializer, DadesEnergetiquesSerializer
from .permissions import (
    EsAdminEdifici,
    EsAdminOPropietariEdifici,
    EsAdminOPropietariHabitatge,
    EsOwnerOAdminHabitatge,
    EsOwnerOAdminDadesEnergetiques,
)
from apps.accounts.models import RoleChoices

class EdificiViewSet(viewsets.ModelViewSet):
    """
    Aquest ViewSet gestiona automàticament:
    - GET /edificis/          -> list()
    - POST /edificis/         -> create()
    - GET /edificis/{id}/     -> retrieve()
    - PUT/PATCH /edificis/{id}/ -> update()
    - DELETE /edificis/{id}/  -> destroy()
    """

    queryset = Edifici.objects.all()

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not hasattr(user, 'profile'):
            return Edifici.objects.none()

        role = user.profile.role
        if role == RoleChoices.ADMIN:
            return Edifici.objects.all()
        if role == RoleChoices.OWNER:
            return Edifici.objects.filter(administradorFinca=user)
        if role == RoleChoices.TENANT:
            return Edifici.objects.filter(habitatges__usuari=user).distinct()
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
        return [IsAuthenticated()]
    
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


class EdificiListAPIView(APIView):
    # GET /edificis/: Llista tots els edificis
    def get(self, request):
        edificis = Edifici.objects.all()
        serializer = EdificiListSerializer(edificis, many=True)
        return Response(serializer.data)

    # POST /edificis/: Crea un nou edifici
    def post(self, request):
        serializer = EdificiDetailSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save() # Guarda a la base de dades
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EdificiDetailAPIView(APIView):
    # GET /edificis/{id}/: Retorna un edifici concret
    def get(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        serializer = EdificiDetailSerializer(edifici)
        return Response(serializer.data)

    # PUT /edificis/{id}/: Actualitza tot un edifici
    def put(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        serializer = EdificiDetailSerializer(edifici, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # PATCH /edificis/{id}/: Actualitza només una part de l'edifici
    def patch(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        # el partial=True permet enviar només algunes dades
        serializer = EdificiDetailSerializer(edifici, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    '''
    # DELETE /edificis/{id}/: Esborra un edifici
    def delete(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        edifici.delete()
        return Response(status=status.HTTP_204_NO_CONTENT) '''
    

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