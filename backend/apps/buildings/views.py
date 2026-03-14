# apps/buildings/views.py
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Edifici, Habitatge, Localitzacio, DadesEnergetiques
from .serializers import EdificiSerializer, HabitatgeSerializer, LocalitzacioSerializer, DadesEnergetiquesSerializer

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


class HabitatgeViewSet(viewsets.ModelViewSet):
    queryset = Habitatge.objects.all()
    serializer_class = HabitatgeSerializer
    permission_classes = [IsAuthenticated]


class LocalitzacioViewSet(viewsets.ModelViewSet):
    queryset = Localitzacio.objects.all()
    serializer_class = LocalitzacioSerializer
    permission_classes = [IsAuthenticated]


class DadesEnergetiquesViewSet(viewsets.ModelViewSet):
    queryset = DadesEnergetiques.objects.all()
    serializer_class = DadesEnergetiquesSerializer
    permission_classes = [IsAuthenticated]