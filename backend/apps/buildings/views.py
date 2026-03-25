# apps/buildings/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.shortcuts import get_object_or_404

from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, action
from apps.accounts.permissions import ABACMixin

from .models import Edifici, Habitatge, Localitzacio, DadesEnergetiques, carrersBarcelona
from .serializers import EdificiDetailSerializer, EdificiListSerializer, HabitatgeDetailSerializer, HabitatgeResumSerializer, LocalitzacioSerializer, DadesEnergetiquesSerializer
from .permissions import EsAdminEdifici, EsAdminOPropietariEdifici, EsAdminOPropietariHabitatge

class EdificiViewSet(viewsets.ModelViewSet):
    queryset = Edifici.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return EdificiListSerializer
        return EdificiDetailSerializer  # retrieve, update, create...permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), EsAdminEdifici()]
        elif self.action in ['retrieve', 'dades_energetiques', 'habitatge_detail']:
            return [IsAuthenticated(), EsAdminOPropietariEdifici()]
        # list, create, habitatges (resum públic)
        return [AllowAny()]
    
    # GET /edificis/{id}/habitatges/
    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def habitatges(self, request, pk=None):
        edifici = self.get_object()
        habitatges = edifici.habitatges.all()
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
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return HabitatgeResumSerializer
        return HabitatgeDetailSerializer
    def get_permissions(self):
        if self.action in ['update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), EsAdminOPropietariHabitatge()]
        elif self.action == 'retrieve':
            return [IsAuthenticated(), EsAdminOPropietariHabitatge()]
        # list
        return [AllowAny()]

class LocalitzacioViewSet(viewsets.ModelViewSet):
    queryset = Localitzacio.objects.all()
    serializer_class = LocalitzacioSerializer
    permission_classes = [IsAuthenticated]  # permite POST sin login


class DadesEnergetiquesViewSet(viewsets.ModelViewSet):
    queryset = DadesEnergetiques.objects.all()
    serializer_class = DadesEnergetiquesSerializer
    # permission_classes = [IsAuthenticated]


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