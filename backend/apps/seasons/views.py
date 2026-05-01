from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminSistema
from .models import Temporada
from .serializers import TemporadaSerializer


class TemporadaViewSet(viewsets.ModelViewSet):
    queryset = Temporada.objects.all()
    serializer_class = TemporadaSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAdminSistema()]

    @action(detail=True, methods=['post'], url_path='iniciar')
    def iniciar(self, request, pk=None):
        temporada = self.get_object()
        try:
            Temporada.objects.iniciar(temporada)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TemporadaSerializer(temporada).data)

    @action(detail=True, methods=['post'], url_path='tancar')
    def tancar(self, request, pk=None):
        temporada = self.get_object()
        try:
            Temporada.objects.tancar(temporada)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TemporadaSerializer(temporada).data)
