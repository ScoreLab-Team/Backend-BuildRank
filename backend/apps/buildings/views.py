# apps/buildings/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from .models import Edifici, Habitatge, Localitzacio, DadesEnergetiques
from .serializers import EdificiSerializer, HabitatgeSerializer, LocalitzacioSerializer, DadesEnergetiquesSerializer, RankingSerializer
from .pagination import RankingPaginacio

'''
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
    serializer_class = EdificiSerializer
    permission_classes = [IsAuthenticated]
'''

class HabitatgeViewSet(viewsets.ModelViewSet):
    queryset = Habitatge.objects.all()
    serializer_class = HabitatgeSerializer
    # permission_classes = [IsAuthenticated]


class LocalitzacioViewSet(viewsets.ModelViewSet):
    queryset = Localitzacio.objects.all()
    serializer_class = LocalitzacioSerializer
    # permission_classes = [IsAuthenticated]


class DadesEnergetiquesViewSet(viewsets.ModelViewSet):
    queryset = DadesEnergetiques.objects.all()
    serializer_class = DadesEnergetiquesSerializer
    # permission_classes = [IsAuthenticated]


class EdificiListAPIView(APIView):
    # GET /edificis/: Llista tots els edificis
    def get(self, request):
        edificis = Edifici.objects.all()
        serializer = EdificiSerializer(edificis, many=True)
        return Response(serializer.data)

    # POST /edificis/: Crea un nou edifici
    def post(self, request):
        serializer = EdificiSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save() # Guarda a la base de dades
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EdificiDetailAPIView(APIView):
    # GET /edificis/{id}/: Retorna un edifici concret
    def get(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        serializer = EdificiSerializer(edifici)
        return Response(serializer.data)

    # PUT /edificis/{id}/: Actualitza tot un edifici
    def put(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        serializer = EdificiSerializer(edifici, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # PATCH /edificis/{id}/: Actualitza només una part de l'edifici
    def patch(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        # el partial=True permet enviar només algunes dades
        serializer = EdificiSerializer(edifici, data=request.data, partial=True)
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