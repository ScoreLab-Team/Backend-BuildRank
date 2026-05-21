# apps/seasons/signals.py
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Temporada, EstatTemporada
from apps.leagues.models import Lliga

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Temporada)
def crear_lligues_temporada(sender, instance, created, **kwargs):
    """
    Quan una temporada passa a ACTIVA, crea automàticament
    les 9 lligues (3 categories x 3 divisions) si no existeixen ja.
    """
    if instance.estat != EstatTemporada.ACTIVA:
        return

    # Idempotència: si ja té lligues no fem res
    if Lliga.objects.filter(temporada=instance).exists():
        logger.info("Temporada id=%s ja té lligues, no es creen de noves.", instance.pk)
        return

    Lliga.objects.create_progress_leagues(instance)

    logger.info(
        "9 lligues creades per la temporada '%s' (id=%s).",
        instance.nom, instance.pk
    )