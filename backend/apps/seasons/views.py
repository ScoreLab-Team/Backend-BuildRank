from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Temporada
from .serializers import TemporadaSerializer


class TemporadaViewSet(viewsets.ModelViewSet):
    queryset = Temporada.objects.all()
    serializer_class = TemporadaSerializer
    permission_classes=[IsAuthenticated]

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        temporada = self.get_object()
        Temporada.objects.activate(temporada)
        return Response({"status": "temporada activada"})

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        temporada = self.get_object()
        Temporada.objects.deactivate(temporada)
        return Response({"status": "temporada desactivada"})