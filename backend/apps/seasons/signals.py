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
    """Retorna puntuacioBase si existeix, sinó puntuacioBaseOpenData."""
    if edifici.puntuacioBase is not None:
        return edifici.puntuacioBase
    return edifici.puntuacioBaseOpenData

def _assignar_divisio_per_percentil(puntuacio, llindars):
    """
    llindars = (p33, p66)
    < p33  → Bronze
    < p66  → Silver
    >= p66 → Gold
    """
    p33, p66 = llindars
    if puntuacio >= p66:
        return "Gold"
    elif puntuacio >= p33:
        return "Silver"
    else:
        return "Bronze"


@receiver(post_save, sender=Temporada)
def crear_lligues_i_participacions(sender, instance, **kwargs):
    logger.info(f"[SIGNAL] post_save Temporada id={instance.pk} estat={instance.estat}")

    if instance.estat != EstatTemporada.ACTIVA:
        logger.info(f"[SIGNAL] Ignorant, estat no és ACTIVA")
        return

    # ── 1. Crear lligues ────────────────────────────────────────────────────
    if not Lliga.objects.filter(temporada=instance).exists():
        Lliga.objects.create_progress_leagues(instance)
        logger.info(f"[SIGNAL] 9 lligues creades")
    else:
        logger.info(f"[SIGNAL] Lligues ja existien")

    # ── 2. Lligues PROGRES ──────────────────────────────────────────────────
    lligues_progres = {
        "Bronze": Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Bronze").first(),
        "Silver": Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Silver").first(),
        "Gold":   Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Gold").first(),
    }
    logger.info(f"[SIGNAL] Lligues PROGRES: {lligues_progres}")

    # ── 3. Edificis actius amb almenys una puntuació ────────────────────────
    from django.db.models import Q
    edificis = list(
        Edifici.actius
        .filter(
            Q(puntuacioBase__isnull=False) | Q(puntuacioBaseOpenData__isnull=False)
        )
        .order_by("puntuacioBase", "puntuacioBaseOpenData")  # nulls al final
    )

    if not edificis:
        logger.warning("Cap edifici actiu amb puntuació per assignar a la temporada id=%s.", instance.pk)
        return

    # ── 4. Percentils sobre puntuació efectiva ──────────────────────────────
    puntuacions = sorted([_puntuacio_efectiva(e) for e in edificis])
    n = len(puntuacions)
    p33 = puntuacions[int(n * 0.33)]
    p66 = puntuacions[int(n * 0.66)]

    logger.info(
        "Temporada id=%s — %d edificis. Llindars: p33=%.2f, p66=%.2f",
        instance.pk, n, p33, p66
    )

    # ── 5. Crear participacions ─────────────────────────────────────────────
    creades = 0
    for edifici in edificis:
        if Participacio.objects.filter(edifici=edifici, lliga__temporada=instance).exists():
            continue

        puntuacio = _puntuacio_efectiva(edifici)
        divisio = _assignar_divisio_per_percentil(puntuacio, (p33, p66))
        lliga = lligues_progres[divisio]
        Participacio.objects.create_participation(edifici=edifici, lliga=lliga)
        creades += 1

    logger.info("Temporada '%s' (id=%s): %d participacions creades.", instance.nom, instance.pk, creades)