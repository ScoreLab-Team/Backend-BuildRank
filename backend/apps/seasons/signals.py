# apps/seasons/signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Temporada, EstatTemporada
from apps.leagues.models import Lliga
from apps.buildings.models import Edifici
from apps.participations.models import Participacio

logger = logging.getLogger(__name__)

def _puntuacio_efectiva(edifici):
    """Retorna la puntuació efectiva de l'edifici.

    Prioritat:
    1. puntuacioBase, si existeix.
    2. puntuacioBaseOpenData, si ve de CEE/Open Data.
    3. 0 si encara no té dades suficients.

    Els edificis sense puntuació també entren a la temporada perquè poden
    incorporar habitatges o dades durant la temporada i començar a progressar.
    """
    if edifici.puntuacioBase is not None:
        return edifici.puntuacioBase
    if edifici.puntuacioBaseOpenData is not None:
        return edifici.puntuacioBaseOpenData
    return 0

def _assignar_divisio_per_index(index, total):
    """Assigna divisió repartint la temporada en terços per ordre de puntuació.

    Això evita que molts edificis empatats a 0 acabin tots a la mateixa divisió
    només perquè els llindars percentils són iguals.
    """
    if total <= 1:
        return "Gold"

    ratio = (index + 1) / total

    if ratio <= 1 / 3:
        return "Bronze"
    if ratio <= 2 / 3:
        return "Silver"
    return "Gold"


@receiver(post_save, sender=Temporada)
def crear_lligues_i_participacions(sender, instance, **kwargs):
    logger.info(f"[SIGNAL] post_save Temporada id={instance.pk} estat={instance.estat}")

    if instance.estat != EstatTemporada.ACTIVA:
        logger.info(f"[SIGNAL] Ignorant, estat no és ACTIVA")
        return

    # ── 1. Crear lligues ────────────────────────────────────────────────────
    if not Lliga.objects.filter(temporada=instance).exists():
        Lliga.objects.create_progress_leagues(instance)
        logger.info(f"[SIGNAL] 3 lligues PROGRES creades")
    else:
        logger.info(f"[SIGNAL] Lligues ja existien")

    # ── 2. Lligues PROGRES ──────────────────────────────────────────────────
    lligues_progres = {
        "Bronze": Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Bronze").first(),
        "Silver": Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Silver").first(),
        "Gold":   Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Gold").first(),
    }
    logger.info(f"[SIGNAL] Lligues PROGRES: {lligues_progres}")

    # ── 3. Edificis actius gestionats ──────────────────────────────────────
    # No inscrivim automàticament tots els edificis Open Data/CEE massius.
    # Només entren edificis actius amb administrador de finca assignat.
    # Si un edifici gestionat encara no té puntuació, entra amb 0 i pot progressar.
    edificis = list(
        Edifici.actius
        .filter(administradorFinca__isnull=False)
        .select_related("administradorFinca")
    )

    if not edificis:
        logger.warning("Cap edifici actiu per assignar a la temporada id=%s.", instance.pk)
        return

    edificis_ordenats = sorted(
        edificis,
        key=lambda edifici: (_puntuacio_efectiva(edifici), edifici.pk),
    )
    n = len(edificis_ordenats)

    logger.info(
        "Temporada id=%s — %d edificis actius gestionats assignables a PROGRES.",
        instance.pk, n
    )

    # ── 4. Crear participacions ─────────────────────────────────────────────
    creades = 0
    for index, edifici in enumerate(edificis_ordenats):
        if Participacio.objects.filter(edifici=edifici, lliga__temporada=instance).exists():
            continue

        divisio = _assignar_divisio_per_index(index, n)
        lliga = lligues_progres[divisio]
        Participacio.objects.create_participation(edifici=edifici, lliga=lliga)
        creades += 1

    logger.info("Temporada '%s' (id=%s): %d participacions creades.", instance.nom, instance.pk, creades)