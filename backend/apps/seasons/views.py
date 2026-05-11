from django.db.models import Q

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotFound

from apps.accounts.permissions import IsAdminSistema
from .models import Temporada
from .serializers import TemporadaSerializer
from apps.participations.models import Participacio
from apps.participations.serializers import RankingSerializer
from apps.leagues.models import Lliga
from apps.buildings.models import GrupComparable
from apps.leagues.pagination import RankingPagination


class TemporadaViewSet(viewsets.ModelViewSet):
    queryset = Temporada.objects.all()
    serializer_class = TemporadaSerializer
    permission_classes=[IsAuthenticated]

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'ranking', 'posicio_edifici']:
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

    @action(detail=True, methods=["get"])
    def ranking(self, request, pk=None):

        temporada = self.get_object()

        group_id = request.query_params.get("group")
        league_id = request.query_params.get("league")
        search = request.query_params.get("search")

        qs = Participacio.objects.select_related(
            "edifici",
            "edifici__localitzacio",
            "edifici__grupComparable",
            "lliga",
            "lliga__temporada",
        ).filter(
            lliga__temporada=temporada
        )

        # Filtre per grup comparable, si no existeix retorna error
        if group_id:

            if not GrupComparable.objects.filter(idGrup=group_id).exists():
                raise NotFound("Invalid group")

            qs = qs.filter(
                edifici__grupComparable__idGrup=group_id
            )

        # Filtre per lliga, si no existeix retorna error
        if league_id:

            if not Lliga.objects.filter(
                    id=league_id,
                    temporada=temporada
            ).exists():
                raise NotFound("Invalid league")

            qs = qs.filter(lliga_id=league_id)

        # Cerca per carrer, si es demana
        if search:

            qs = qs.filter(
                edifici__localitzacio__carrer__icontains=search
            )

        qs = qs.order_by("-puntuacio")

        paginator = RankingPagination()

        page = paginator.paginate_queryset(qs, request)

        serializer = RankingSerializer(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def posicio_edifici(self, request, pk=None):
        temporada = self.get_object()

        edifici_id = request.query_params.get("edifici")
        top_n = int(request.query_params.get("top", 3))

        scope = request.query_params.get("scope", "lliga")
        group_filter = request.query_params.get("group", "false").lower() == "true"

        if not edifici_id:
            return Response(
                {"error": "edifici is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        edifici_id = int(edifici_id)

        try:
            participacio = Participacio.objects.select_related(
                "edifici",
                "edifici__grupComparable",
                "lliga",
                "lliga__temporada"
            ).get(
                lliga__temporada=temporada,
                edifici_id=edifici_id
            )
        except Participacio.DoesNotExist:
            raise NotFound("Participacio not found")


        if scope == "temporada":
            qs = Participacio.objects.filter(lliga__temporada=temporada)
        else:
            qs = Participacio.objects.filter(lliga=participacio.lliga)

        qs = qs.select_related(
            "edifici",
            "edifici__grupComparable",
            "lliga",
            "lliga__temporada"
        )


        if group_filter:
            group = participacio.edifici.grupComparable
            if group:
                qs = qs.filter(edifici__grupComparable_id=group.idGrup)


        qs = qs.order_by("-puntuacio")

        posicio = qs.filter(
            puntuacio__gt=participacio.puntuacio
        ).count() + 1

        en_top = posicio <= top_n

        punts_per_top = 0

        if not en_top and qs.count() >= top_n:
            objectiu = qs[top_n - 1]
            punts_per_top = max(objectiu.puntuacio - participacio.puntuacio, 0)

        data = {
            "edifici_id": participacio.edifici.idEdifici,
            "posicio": posicio,
            "top_objectiu": top_n,
            "esta_en_top": en_top,
            "puntuacio_actual": participacio.puntuacio,
            "punts_per_top": punts_per_top,
            "scope": scope,
            "grup_comparat": group_filter,
        }

        if scope == "lliga":
            data["lliga"] = {
                "id": participacio.lliga.id,
                "nom": participacio.lliga.nom,
            }
        if group_filter:
            data["grup_utilitzat"] = participacio.edifici.grupComparable.idGrup \
                if participacio.edifici.grupComparable else None

        return Response(data)