# apps/participations/services.py
import logging
from apps.seasons.models import Temporada
from apps.leagues.models import Lliga, DivisioLliga
from .models import Participacio

logger = logging.getLogger(__name__)


def create_participation_for_edifici(edifici):
    """
    Crea la Participacio d'un edifici per a la temporada activa.
    Idempotent: si ja existeix, retorna l'existent sense modificar-la.
    Retorna la Participacio o None si no es pot crear.
    """
    # 1. Temporada activa
    temporada = Temporada.objects.filter(estat='ACTIVA').first()
    if not temporada:
        logger.warning(
            "No hi ha temporada activa. Edifici id=%s no inscrit.", edifici.pk
        )
        return None

    # 2. Lliga Bronze de la temporada activa
    lliga = Lliga.objects.filter(
        temporada=temporada,
        divisio=DivisioLliga.BRONZE
    ).first()
    if not lliga:
        logger.warning(
            "No hi ha lliga Bronze per la temporada id=%s. Edifici id=%s no inscrit.",
            temporada.pk, edifici.pk
        )
        return None

    # 3. Idempotència
    if Participacio.objects.filter(edifici=edifici, lliga__temporada=temporada).exists():
        logger.info("Edifici id=%s ja té participació per la temporada id=%s.", edifici.pk, temporada.pk)
        return Participacio.objects.filter(edifici=edifici, lliga__temporada=temporada).first()

    # 4. Crear via manager (conté la lògica de puntuació)
    participacio = Participacio.objects.create_participation(edifici=edifici, lliga=lliga)
    logger.info(
        "Participacio id=%s creada: edifici=%s, lliga=%s (%s), temporada=%s, puntuacio=%.2f",
        participacio.pk, edifici.pk, lliga.pk, lliga.divisio,
        temporada.pk, participacio.puntuacio
    )
    return participacio