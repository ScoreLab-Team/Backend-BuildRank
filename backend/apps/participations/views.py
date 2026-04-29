from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Participacio
from .serializers import ParticipacioSerializer


class ParticipacioViewSet(viewsets.ModelViewSet):
    queryset = Participacio.objects.all()
    serializer_class = ParticipacioSerializer

    @action(detail=True, methods=["post"])
    def update_score(self, request, pk=None):
        participacio = self.get_object()
        new_score = request.data.get("puntuacio")

        Participacio.objects.update_score(participacio, new_score)

        return Response({"status": "score updated"})