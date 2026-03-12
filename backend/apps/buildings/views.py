# apps/buildings/views.py
from rest_framework import viewsets
from .models import Edifici, Habitatge, Localitzacio, DadesEnergetiques
from .serializers import EdificiSerializer, HabitatgeSerializer, LocalitzacioSerializer, DadesEnergetiquesSerializer

class EdificiViewSet(viewsets.ModelViewSet):
    queryset = Edifici.objects.all()
    serializer_class = EdificiSerializer

class HabitatgeViewSet(viewsets.ModelViewSet):
    queryset = Habitatge.objects.all()
    serializer_class = HabitatgeSerializer

class LocalitzacioViewSet(viewsets.ModelViewSet):
    queryset = Localitzacio.objects.all()
    serializer_class = LocalitzacioSerializer

class DadesEnergetiquesViewSet(viewsets.ModelViewSet):
    queryset = DadesEnergetiques.objects.all()
    serializer_class = DadesEnergetiquesSerializer