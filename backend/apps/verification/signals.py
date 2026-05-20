# apps/verification/signals.py
import logging
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import AdminFincaDocumentVerification
from apps.participations.services import create_participation_for_edifici

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=AdminFincaDocumentVerification)
def signal_verificacio_aprovada(sender, instance, **kwargs):
    """
    Quan la verificació passa a APPROVED:
      1. Activa l'edifici si no ho estava.
      2. Crea la participació a la temporada activa.
    """
    if not instance.pk:
        return

    try:
        anterior = AdminFincaDocumentVerification.objects.get(pk=instance.pk)
    except AdminFincaDocumentVerification.DoesNotExist:
        return

    # Només actua en la transició → APPROVED
    if anterior.status == instance.Status.APPROVED or instance.status != instance.Status.APPROVED:
        return

    edifici = instance.edifici
    if not edifici:
        logger.warning("Verificació id=%s aprovada però sense edifici associat.", instance.pk)
        return

    # 1. Activar edifici si cal
    if not edifici.actiu:
        edifici.actiu = True
        edifici.save(update_fields=["actiu"])
        logger.info("Edifici id=%s activat per aprovació verificació id=%s.", edifici.pk, instance.pk)

    # 2. Crear participació
    participacio = create_participation_for_edifici(edifici)
    if participacio:
        logger.info(
            "Participacio id=%s creada per edifici id=%s en aprovar verificació id=%s.",
            participacio.pk, edifici.pk, instance.pk
        )