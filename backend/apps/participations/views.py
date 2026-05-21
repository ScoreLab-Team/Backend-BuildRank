from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from .models import Participacio
from .serializers import ParticipacioSerializer
from apps.leagues.models import Lliga
from apps.seasons.models import Temporada
from apps.buildings.models import Edifici, MilloraImplementada
from datetime import timedelta

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
            "puntuacio_inicial": participacio.puntuacio_inicial,
            "posicio": participacio.posicio,
            "divisio": participacio.divisio,
            "grup_comparable": (
                participacio.edifici.grupComparable.idGrup
                if participacio.edifici.grupComparable else None
            )
        })

    @action(detail=False, methods=["get"], url_path="evolucio_puntuacio")
    def evolucio_puntuacio(self, request):

        edifici_id = request.query_params.get("edifici")
        temporades = int(request.query_params.get("temporades", 5))

        if not edifici_id:
            return Response(
                {"error": "edifici is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        get_object_or_404(Edifici, pk=edifici_id)

        historial = (
            Participacio.objects
            .select_related("lliga__temporada")
            .filter(edifici_id=edifici_id)
            .order_by("-lliga__temporada__dataInici")[:temporades]
        )

        data = [
            {
                "temporada_id": p.lliga.temporada.id_temporada,
                "nom_temporada": p.lliga.temporada.nom,
                "lliga": p.lliga.nom,

                "puntuacio_inicial": p.puntuacio_inicial,
                "puntuacio_actual": p.puntuacio,

                "delta_puntuacio": (
                        p.puntuacio - p.puntuacio_inicial
                ),

                "posicio_actual": p.posicio,
            }
            for p in historial
        ]

        return Response(data)



    @action(detail=False, methods=["get"], url_path="progres_anual")
    def progres_anual(self, request):

        edifici_id = request.query_params.get("edifici")

        if not edifici_id:
            return Response(
                {"error": "edifici is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        edifici = get_object_or_404(Edifici, pk=edifici_id)

        avui = timezone.now().date()
        fa_un_any = avui - timedelta(days=365)

        participacions = (
            Participacio.objects
            .select_related("lliga__temporada")
            .filter(
                edifici_id=edifici_id,
                lliga__temporada__dataInici__gte=fa_un_any
            )
            .order_by("lliga__temporada__dataInici")
        )

        if not participacions.exists():
            return Response(
                {
                    "estat": "sense_dades",
                    "missatge": "No hi ha participacions en l'últim any."
                },
                status=status.HTTP_200_OK
            )


        participacio_inicial = participacions.first()


        participacio_actual = participacions.last()

        puntuacio_inicial = participacio_inicial.puntuacio
        puntuacio_actual = participacio_actual.puntuacio

        delta_puntuacio = puntuacio_actual - puntuacio_inicial


        THRESHOLD_ESTANCAMENT = 2.0

        if delta_puntuacio > THRESHOLD_ESTANCAMENT:
            tendencia = "millora"

        elif delta_puntuacio < -THRESHOLD_ESTANCAMENT:
            tendencia = "empitjorament"

        else:
            tendencia = "estancament"



        millores = (
            MilloraImplementada.objects
            .select_related("millora")
            .filter(
                edifici_id=edifici_id,
                dataExecucio__gte=fa_un_any
            )
            .order_by("-dataExecucio")
        )

        millores_data = [
            {
                "id": m.id,
                "nom": m.millora.nom,
                "categoria": m.millora.categoria,
                "data_execucio": m.dataExecucio,
                "cost_real": m.costReal,
                "estat_validacio": m.estatValidacio,
            }
            for m in millores
        ]

        # ---------------------------------------------------------
        # RESPOSTA
        # ---------------------------------------------------------

        return Response({
            "edifici": edifici.idEdifici,

            "periode": {
                "inici": fa_un_any,
                "fi": avui,
            },

            "temporada_inicial": {
                "id": participacio_inicial.lliga.temporada.id_temporada,
                "nom": participacio_inicial.lliga.temporada.nom,
                "data_inici": participacio_inicial.lliga.temporada.dataInici,
            },

            "temporada_actual": {
                "id": participacio_actual.lliga.temporada.id_temporada,
                "nom": participacio_actual.lliga.temporada.nom,
                "data_inici": participacio_actual.lliga.temporada.dataInici,
            },

            "puntuacio": {
                "inicial": puntuacio_inicial,
                "actual": puntuacio_actual,
                "delta": delta_puntuacio,
            },

            "tendencia": tendencia,

            "resum": {
                "millores_implementades": len(millores_data),
            },

            "millores": millores_data,
        })