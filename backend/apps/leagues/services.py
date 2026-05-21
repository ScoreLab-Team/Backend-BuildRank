from django.db import transaction

from apps.leagues.models import CategoriaRanking, Lliga, RankingHistorico
from apps.participations.models import Participacio


def generar_snapshots_temporada(temporada, categoria=CategoriaRanking.PROGRES):
    """Genera o actualitza snapshots de RankingHistorico per una temporada.

    Per defecte només consolida la categoria PROGRES, perquè el ranking final
    del producte queda definit per les divisions Bronze/Silver/Gold de progrés.
    És idempotent: si el snapshot ja existeix, s'actualitza.
    """
    lligues = (
        Lliga.objects
        .filter(temporada=temporada, categoria=categoria)
        .order_by("id")
    )

    resum = {
        "temporada": temporada.id_temporada,
        "categoria": str(categoria),
        "lligues_processades": 0,
        "items": 0,
    }

    with transaction.atomic():
        for lliga in lligues:
            resum["lligues_processades"] += 1

            participacions = (
                Participacio.objects
                .filter(lliga=lliga)
                .select_related("edifici")
                .order_by("-puntuacio", "edifici_id")
            )

            for posicio, participacio in enumerate(participacions, start=1):
                update_fields = []

                if participacio.posicio != posicio:
                    participacio.posicio = posicio
                    update_fields.append("posicio")

                if participacio.divisio != lliga.divisio:
                    participacio.divisio = lliga.divisio
                    update_fields.append("divisio")

                if update_fields:
                    participacio.save(update_fields=update_fields)

                RankingHistorico.objects.update_or_create(
                    edifici=participacio.edifici,
                    temporada=temporada,
                    categoria=lliga.categoria,
                    defaults={
                        "puntuacio": participacio.puntuacio,
                        "posicio": posicio,
                        "divisio": lliga.divisio,
                    },
                )
                resum["items"] += 1

    return resum
