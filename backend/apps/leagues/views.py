from rest_framework import viewsets, status
from rest_framework.decorators import action, permission_classes
from rest_framework.response import Response
from .pagination import RankingPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotFound

from .models import Lliga, RankingHistorico
from .serializers import LligaSerializer
from apps.buildings.models import GrupComparable
from apps.participations.models import Participacio
from apps.accounts.permissions import ABACMixin, IsAdminSistema
from apps.seasons.models import Temporada, EstatTemporada
from apps.leagues.services import generar_snapshots_temporada

class LligaViewSet(viewsets.ModelViewSet):
    queryset = Lliga.objects.all()
    serializer_class = LligaSerializer
    permission_classes=[IsAuthenticated]

    @action(detail=False, methods=["get"])
    def evolucio(self, request):
        edifici_id = request.query_params.get("edifici")
        categoria = request.query_params.get("categoria")
        limit = request.query_params.get("limit")

        if not edifici_id or not categoria:
            return Response(
                {"error": "edifici and categoria are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Snapshot on demand: si hi ha temporada activa, mantenim RankingHistorico
        # actualitzat abans de retornar evolució.
        temporada_activa = (
            Temporada.objects
            .filter(estat=EstatTemporada.ACTIVA)
            .order_by("-dataInici", "-id_temporada")
            .first()
        )
        if temporada_activa:
            generar_snapshots_temporada(temporada_activa, categoria=categoria.upper())

        historial = RankingHistorico.objects.filter(
            edifici_id=edifici_id,
            categoria=categoria.upper()
        ).select_related("temporada").order_by("temporada__dataInici")

        if limit is not None:
            try:
                limit = int(limit)
            except (TypeError, ValueError):
                return Response(
                    {"error": "limit must be a positive integer"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if limit <= 0:
                return Response(
                    {"error": "limit must be a positive integer"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            historial = list(historial.order_by("-temporada__dataInici")[:limit])
            historial.reverse()

        data = [
            {
                "temporada": h.temporada.id_temporada,
                "nom_temporada": h.temporada.nom,
                "categoria": h.categoria,
                "puntuacio": h.puntuacio,
                "posicio": h.posicio,
                "divisio": h.divisio,
                "data_calcul": h.dataCalcul,
            }
            for h in historial
        ]

        return Response(data)
        
    @action(detail=True, methods=["post"])
    def generar_snapshot(self, request, pk=None):
        lliga = self.get_object()

        participacions = lliga.participations.select_related("edifici").order_by("-puntuacio")

        created_or_updated = 0

        for index, participacio in enumerate(participacions, start=1):
            RankingHistorico.objects.update_or_create(
                edifici=participacio.edifici,
                temporada=lliga.temporada,
                categoria=lliga.categoria,
                defaults={
                    "puntuacio": participacio.puntuacio,
                    "posicio": index,
                    "divisio": participacio.divisio,
                }
            )
            created_or_updated += 1

        return Response({
            "message": "Snapshot generated successfully",
            "lliga": lliga.id,
            "temporada": lliga.temporada.id_temporada,
            "categoria": lliga.categoria,
            "items": created_or_updated,
        })
