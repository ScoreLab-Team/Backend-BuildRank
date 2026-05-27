import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Profile
from apps.buildings.models import Habitatge

logger = logging.getLogger(__name__)


def _stream_is_configured() -> bool:
    from django.conf import settings
    return bool(
        getattr(settings, "STREAM_API_KEY", "") and getattr(settings, "STREAM_API_SECRET", "")
    )


@receiver(post_save, sender=Profile)
def sync_profile_to_stream(sender, instance, **kwargs):
    """
    Quan el perfil d'un usuari es guarda (rol, validació, etc.),
    sincronitza les seves dades a GetStream.
    """
    if not _stream_is_configured():
        return

    from .services import get_stream_client, sync_user_to_stream

    try:
        client = get_stream_client()
        sync_user_to_stream(client, instance.user)
    except Exception:
        logger.warning(
            "No s'ha pogut sincronitzar el perfil de l'usuari %s a GetStream.",
            instance.user_id,
            exc_info=True,
        )


@receiver(post_save, sender=Habitatge)
def add_tenant_to_building_channel(sender, instance, **kwargs):
    """
    Quan un habitatge s'associa a un usuari, l'afegeix automàticament
    al canal comunitari de l'edifici a GetStream.
    """
    if not instance.usuari_id or not _stream_is_configured():
        return

    from .services import (
        _ensure_building_channel,
        get_stream_client,
        get_stream_user_id,
        sync_user_to_stream,
    )

    try:
        client = get_stream_client()
        sync_user_to_stream(client, instance.usuari)
        stream_uid = get_stream_user_id(instance.usuari)
        _ensure_building_channel(client, instance.edifici, stream_uid, instance.usuari)
    except Exception:
        logger.warning(
            "No s'ha pogut afegir l'usuari %s al canal de l'edifici %s a GetStream.",
            instance.usuari_id,
            instance.edifici_id,
            exc_info=True,
        )
