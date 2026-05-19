from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from .models import Notificacio
from .serializers import NotificacioSerializer


class NotificacioListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificacioSerializer

    def get_queryset(self):
        return Notificacio.objects.filter(destinatari=self.request.user)


class NoLlegidesCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notificacio.objects.filter(destinatari=request.user, llegida=False).count()
        return Response({'no_llegides': count})


class LlegirNotificacioView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notif = get_object_or_404(Notificacio, pk=pk, destinatari=request.user)
        notif.llegida = True
        notif.save(update_fields=['llegida'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class LlegirTotesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notificacio.objects.filter(destinatari=request.user, llegida=False).update(llegida=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
