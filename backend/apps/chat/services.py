import time
from typing import Any

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.accounts.models import RoleChoices
from apps.buildings.models import Edifici


def get_stream_user_id(user) -> str:
    """
    Retorna un identificador estable per a GetStream.

    No fem servir l'email com a identificador principal perquè podria canviar.
    """
    return f"user_{user.id}"


def create_stream_token_for_user(user) -> str:
    """
    Genera un token JWT per connectar l'usuari autenticat a GetStream.

    El secret de Stream només viu al backend. El frontend mai ha de conèixer
    STREAM_API_SECRET.
    """
    if not settings.STREAM_API_SECRET:
        raise ImproperlyConfigured("STREAM_API_SECRET no està configurat.")

    now = int(time.time())
    expiration_seconds = int(getattr(settings, "STREAM_TOKEN_EXPIRATION_SECONDS", 3600))

    payload = {
        "user_id": get_stream_user_id(user),
        "iat": now,
        "exp": now + expiration_seconds,
    }

    return jwt.encode(payload, settings.STREAM_API_SECRET, algorithm="HS256")


def get_accessible_buildings(user):
    """
    Retorna els edificis als quals l'usuari pot accedir segons la lògica actual.

    En el codi actual:
    - ADMIN o superuser pot veure tots els edificis actius.
    - OWNER funciona com a administrador de finca i veu els edificis que gestiona.
    - TENANT veu edificis on té habitatge vinculat.
    """
    if not user.is_authenticated:
        return Edifici.objects.none()

    role = getattr(getattr(user, "profile", None), "role", None)

    if user.is_superuser or role == RoleChoices.ADMIN:
        return Edifici.objects.filter(actiu=True).select_related(
            "grupComparable",
            "localitzacio",
        )

    if role == RoleChoices.OWNER:
        return Edifici.objects.filter(
            actiu=True,
            administradorFinca=user,
        ).select_related(
            "grupComparable",
            "localitzacio",
        )

    return Edifici.objects.filter(
        actiu=True,
        habitatges__usuari=user,
    ).distinct().select_related(
        "grupComparable",
        "localitzacio",
    )


def build_channel_descriptors(user) -> list[dict[str, Any]]:
    """
    Retorna els canals que el frontend podrà mostrar.

    Aquesta primera PR encara no crea canals reals a GetStream.
    Només calcula quins canals corresponen a l'usuari autenticat.
    """
    buildings = get_accessible_buildings(user)
    role = getattr(getattr(user, "profile", None), "role", None)

    channels = []

    for edifici in buildings:
        channels.append({
            "id": f"building_{edifici.idEdifici}",
            "type": "messaging",
            "kind": "building",
            "name": f"Comunitat edifici {edifici.idEdifici}",
            "building_id": edifici.idEdifici,
            "stream_channel_id": f"building_{edifici.idEdifici}",
            "description": "Xat comunitari intern de l'edifici.",
        })

        if role in (RoleChoices.ADMIN, RoleChoices.OWNER) and edifici.grupComparable_id:
            channels.append({
                "id": f"twin_group_{edifici.grupComparable_id}_admins",
                "type": "messaging",
                "kind": "twin_building",
                "name": f"Twin Building grup {edifici.grupComparable_id}",
                "group_id": edifici.grupComparable_id,
                "building_id": edifici.idEdifici,
                "stream_channel_id": f"twin_group_{edifici.grupComparable_id}_admins",
                "description": "Xat entre administradors d'edificis similars.",
            })

    unique_channels = {}
    for channel in channels:
        unique_channels[channel["id"]] = channel

    return list(unique_channels.values())