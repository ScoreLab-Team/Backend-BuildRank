from django.db.models import Prefetch
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Participacio
from .serializers import ParticipacioSerializer
from apps.leagues.models import Lliga
from apps.seasons.models import Temporada
from apps.buildings.models import Edifici

class ParticipacioViewSet(viewsets.ModelViewSet):
    queryset = Participacio.objects.all()
    serializer_class = ParticipacioSerializer
    permission_classes=[IsAuthenticated]

    @action(detail=True, methods=["post"])
    def update_score(self, request, pk=None):
        participacio = self.get_object()
        new_score = request.data.get("puntuacio")

        Participacio.objects.update_score(participacio, new_score)

        return Response({"status": "score updated"})

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):

        edifici_id = request.query_params.get("edifici")

        if not edifici_id:
            return Response(
                {"error": "edifici is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        edifici = get_object_or_404(Edifici, pk=edifici_id)


        participacio = (
            Participacio.objects
            .select_related(
                "lliga__temporada"
            )
            .filter(edifici_id=edifici_id)
            .order_by("-lliga__temporada__dataInici")
            .first() #Evita problemes si en algun moment un edifici esta participant a més d'una temporada
        )

        if not participacio:
            return Response(
                {"error": "Participacio not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "id": participacio.id,
            "edifici": participacio.edifici.idEdifici,
            "lliga": participacio.lliga.id,
            "nom_lliga": participacio.lliga.nom,
            "temporada": participacio.lliga.temporada.id_temporada,
            "nom_temporada": participacio.lliga.temporada.nom,
            "puntuacio": participacio.puntuacio,
            "posicio": participacio.posicio,
            "divisio": participacio.divisio,
            "grup_comparable": (
                participacio.edifici.grupComparable.idGrup
                if participacio.edifici.grupComparable else None
            )
        })