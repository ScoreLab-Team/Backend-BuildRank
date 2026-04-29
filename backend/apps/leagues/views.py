from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .pagination import RankingPagination

from .models import Lliga
from .serializers import LligaSerializer
from apps.buildings.models import GrupComparable
from apps.participations.models import Participacio

class LligaViewSet(viewsets.ModelViewSet):
    queryset = Lliga.objects.all()
    serializer_class = LligaSerializer

    @action(detail=True, methods=["get"])
    def ranking(self, request, pk=None):
        lliga = self.get_object()

        group_id = request.query_params.get("group")

        qs = lliga.participations.select_related("edifici").order_by("-puntuacio")

        if group_id:
            if not lliga.participations.filter(edifici__grupComparable_id=group_id).exists():
                return Response(
                    {"error": "Invalid group"},
                    status=404
                )

            qs = qs.filter(edifici__grupComparable_id=group_id)

        paginator = RankingPagination()
        page = paginator.paginate_queryset(qs, request)

        data = [
            {
                "edifici": p.edifici.idEdifici,
                "puntuacio": p.puntuacio,
                "posicio": p.posicio
            }
            for p in page
        ]

        return paginator.get_paginated_response(data)

    @action(detail=True, methods=["get"])
    def posicio_edifici(self, request, pk=None):
        lliga = self.get_object()

        edifici_id = request.query_params.get("edifici")
        top_n = int(request.query_params.get("top", 3))
        segment = request.query_params.get("segment", "false").lower() == "true"

        if not edifici_id:
            return Response(
                {"error": "edifici is required"},
                status=400
            )

        try:
            participacio = Participacio.objects.select_related("edifici").get(
                lliga=lliga,
                edifici_id=edifici_id
            )
        except Participacio.DoesNotExist:
            return Response(
                {"error": "Participacio not found"},
                status=404
            )

        qs = Participacio.objects.filter(lliga=lliga).select_related("edifici")

        if segment:
            group = participacio.edifici.grupComparable
            if group:
                qs = qs.filter(edifici__grupComparable=group)

        qs = qs.order_by("-puntuacio")

        posicio = qs.filter(
            puntuacio__gt=participacio.puntuacio
        ).count() + 1

        en_top = posicio <= top_n

        puntos_para_top = 0

        if not en_top:
            try:
                if qs.count() >= top_n:
                    objetivo = qs[top_n - 1]
                    puntos_para_top = max(objetivo.puntuacio - participacio.puntuacio, 0)
            except IndexError:
                puntos_para_top = 0

        return Response({
            "edifici_id": participacio.edifici.idEdifici,
            "liga": lliga.id,
            "posicion": posicio,
            "top_objetivo": top_n,
            "esta_en_top": en_top,
            "puntuacion_actual": participacio.puntuacio,
            "punt_per_top": puntos_para_top,
            "segmentat": segment,
            "grup_utilitzat": participacio.edifici.grupComparable.idGrup if participacio.edifici.grupComparable else None
        })