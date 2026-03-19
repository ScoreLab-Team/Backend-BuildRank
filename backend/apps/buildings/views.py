# apps/buildings/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated

from .models import Edifici, Habitatge, Localitzacio, DadesEnergetiques
from .serializers import EdificiSerializer, HabitatgeSerializer, LocalitzacioSerializer, DadesEnergetiquesSerializer

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

    '''
    # DELETE /edificis/{id}/: Esborra un edifici
    def delete(self, request, pk):
        edifici = get_object_or_404(Edifici, pk=pk)
        edifici.delete()
        return Response(status=status.HTTP_204_NO_CONTENT) '''