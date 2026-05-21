# apps/seasons/signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Temporada, EstatTemporada
from apps.leagues.models import Lliga
from apps.buildings.models import Edifici
from apps.participations.models import Participacio

logger = logging.getLogger(__name__)


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
    print(f"[SIGNAL] post_save Temporada id={instance.pk} estat={instance.estat}")

    if instance.estat != EstatTemporada.ACTIVA:
        print(f"[SIGNAL] Ignorant, estat no és ACTIVA")
        return

    # ── 1. Crear lligues ────────────────────────────────────────────────────
    if not Lliga.objects.filter(temporada=instance).exists():
        Lliga.objects.create_progress_leagues(instance)
        print(f"[SIGNAL] 9 lligues creades")
    else:
        print(f"[SIGNAL] Lligues ja existien")

    # ── 2. Lligues PROGRES ──────────────────────────────────────────────────
    lligues_progres = {
        "Bronze": Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Bronze").first(),
        "Silver": Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Silver").first(),
        "Gold":   Lliga.objects.filter(temporada=instance, categoria="PROGRES", divisio="Gold").first(),
    }
    print(f"[SIGNAL] Lligues PROGRES: {lligues_progres}")

    # ── 3. Edificis actius amb puntuació ────────────────────────────────────
    edificis = list(
        Edifici.actius
        .filter(puntuacioBase__isnull=False)
        .order_by("puntuacioBase")
    )
    print(f"[SIGNAL] Edificis actius amb puntuació: {len(edificis)}")
    for e in edificis:
        print(f"  - Edifici id={e.pk} puntuacioBase={e.puntuacioBase}")

    if not edificis:
        print(f"[SIGNAL] Cap edifici, sortint")
        return

    # ── 4. Percentils ───────────────────────────────────────────────────────
    puntuacions = [e.puntuacioBase for e in edificis]
    n = len(puntuacions)
    p33 = puntuacions[int(n * 0.33)]
    p66 = puntuacions[int(n * 0.66)]
    print(f"[SIGNAL] n={n}, p33={p33}, p66={p66}")

    # ── 5. Crear participacions ─────────────────────────────────────────────
    for edifici in edificis:
        ja_existeix = Participacio.objects.filter(
            edifici=edifici,
            lliga__temporada=instance
        ).exists()
        print(f"[SIGNAL] Edifici id={edifici.pk} — ja_existeix={ja_existeix}")

        if ja_existeix:
            continue

        divisio = _assignar_divisio_per_percentil(edifici.puntuacioBase, (p33, p66))
        lliga = lligues_progres[divisio]
        print(f"[SIGNAL] Creant participació: edifici={edifici.pk} divisio={divisio} lliga={lliga}")

        participacio = Participacio.objects.create_participation(edifici=edifici, lliga=lliga)
        print(f"[SIGNAL] Participació creada id={participacio.pk}")