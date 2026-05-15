import logging
import time
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from stream_chat import StreamChat

from apps.accounts.models import RoleChoices
from apps.buildings.models import Edifici

logger = logging.getLogger(__name__)


def _require_stream_settings() -> tuple[str, str]:
    api_key = getattr(settings, "STREAM_API_KEY", "")
    api_secret = getattr(settings, "STREAM_API_SECRET", "")
    if not api_key or not api_secret:
        raise ImproperlyConfigured(
            "STREAM_API_KEY i STREAM_API_SECRET han d'estar configurats."
        )
    return api_key, api_secret


def get_stream_client() -> StreamChat:
    api_key, api_secret = _require_stream_settings()
    return StreamChat(api_key=api_key, api_secret=api_secret)


def get_stream_user_id(user) -> str:
    """Retorna un identificador estable per a GetStream basat en l'ID de Django."""
    return f"user_{user.id}"


def sync_user_to_stream(client: StreamChat, user) -> None:
    """
    Sincronitza (crea o actualitza) l'usuari a GetStream.

    S'anomena upsert_user perquè és idempotent: si l'usuari ja existeix,
    actualitza les seves dades; si no, el crea.
    """
    profile = getattr(user, "profile", None)
    role = getattr(profile, "role", None)
    full_name = f"{user.first_name} {user.last_name}".strip() or user.email

    user_data: dict[str, Any] = {
        "id": get_stream_user_id(user),
        "name": full_name,
        "buildrank_role": role or "",
    }

    if user.is_superuser or role == RoleChoices.ADMIN:
        user_data["role"] = "admin"

    client.upsert_user(user_data)


def create_stream_token_for_user(user) -> str:
    """
    Genera un token JWT per connectar l'usuari autenticat a GetStream.

    Sincronitza les dades de l'usuari primer (best-effort: si falla la
    sincronització, el token es genera igualment). El secret de Stream
    mai surt del backend.
    """
    client = get_stream_client()
    stream_uid = get_stream_user_id(user)

    try:
        sync_user_to_stream(client, user)
    except Exception:
        logger.warning(
            "No s'ha pogut sincronitzar l'usuari %s a GetStream.", user.id, exc_info=True
        )

    expiration_seconds = int(getattr(settings, "STREAM_TOKEN_EXPIRATION_SECONDS", 3600))
    return client.create_token(stream_uid, expiration=int(time.time()) + expiration_seconds)


def get_accessible_buildings(user):
    """
    Retorna els edificis als quals l'usuari pot accedir.

    - ADMIN o superuser: tots els edificis actius.
    - OWNER: edificis on és administrador de finca.
    - TENANT: edificis on té habitatge vinculat.
    """
    if not user.is_authenticated:
        return Edifici.objects.none()

    role = getattr(getattr(user, "profile", None), "role", None)

    if user.is_superuser or role == RoleChoices.ADMIN:
        return Edifici.objects.filter(actiu=True).select_related(
            "grupComparable", "localitzacio"
        )

    if role == RoleChoices.OWNER:
        return Edifici.objects.filter(
            actiu=True, administradorFinca=user
        ).select_related("grupComparable", "localitzacio")

    return (
        Edifici.objects.filter(actiu=True, habitatges__usuari=user)
        .distinct()
        .select_related("grupComparable", "localitzacio")
    )


def _get_twin_group_admin_member_ids(group_id: int) -> list[str]:
    """
    Retorna els IDs de Stream de tots els ADMIN/OWNER que gestionen
    edificis del grup comparable indicat.
    """
    buildings = Edifici.objects.filter(
        actiu=True,
        grupComparable_id=group_id,
        administradorFinca__isnull=False,
    ).select_related("administradorFinca__profile")

    member_ids: list[str] = []
    for edifici in buildings:
        admin_user = edifici.administradorFinca
        if admin_user is None:
            continue
        role = getattr(getattr(admin_user, "profile", None), "role", None)
        if role in (RoleChoices.ADMIN, RoleChoices.OWNER) or admin_user.is_superuser:
            member_ids.append(get_stream_user_id(admin_user))

    return list(set(member_ids))


def _ensure_building_channel(
    client: StreamChat, edifici, stream_uid: str
) -> dict[str, Any]:
    """
    Crea el canal comunitari de l'edifici a GetStream si no existeix,
    i afegeix l'usuari com a membre. Operació idempotent.
    """
    channel_id = f"building_{edifici.idEdifici}"
    loc = edifici.localitzacio
    channel_name = (
        f"Comunitat {loc.carrer} {loc.numero}"
        if loc and loc.carrer
        else f"Comunitat edifici {edifici.idEdifici}"
    )

    channel = client.channel("messaging", channel_id, data={"name": channel_name})
    channel.create(stream_uid)
    channel.add_members([stream_uid])

    return {
        "id": channel_id,
        "type": "messaging",
        "kind": "building",
        "name": channel_name,
        "building_id": edifici.idEdifici,
        "stream_channel_id": channel_id,
        "description": "Xat comunitari intern de l'edifici.",
    }


def _ensure_twin_group_channel(
    client: StreamChat, group_id: int, stream_uid: str
) -> dict[str, Any]:
    """
    Crea el canal de twin buildings del grup comparable si no existeix,
    i afegeix com a membres tots els admins/owners del grup. Idempotent.
    """
    channel_id = f"twin_group_{group_id}_admins"

    channel = client.channel(
        "messaging",
        channel_id,
        data={"name": f"Twin Building grup {group_id}"},
    )
    channel.create(stream_uid)

    member_ids = _get_twin_group_admin_member_ids(group_id)
    if stream_uid not in member_ids:
        member_ids.append(stream_uid)
    channel.add_members(member_ids)

    return {
        "id": channel_id,
        "type": "messaging",
        "kind": "twin_building",
        "name": f"Twin Building grup {group_id}",
        "group_id": group_id,
        "stream_channel_id": channel_id,
        "description": "Xat entre administradors d'edificis similars.",
    }


def build_channel_descriptors(user) -> list[dict[str, Any]]:
    """
    Lectura pura: calcula els canals accessibles des de les dades de Django
    sense fer cap crida a l'API de GetStream.
    """
    buildings = get_accessible_buildings(user)
    role = getattr(getattr(user, "profile", None), "role", None)

    channels: list[dict[str, Any]] = []
    seen_twin_groups: set[int] = set()

    for edifici in buildings:
        loc = edifici.localitzacio
        channel_name = (
            f"Comunitat {loc.carrer} {loc.numero}"
            if loc and loc.carrer
            else f"Comunitat edifici {edifici.idEdifici}"
        )
        channel_id = f"building_{edifici.idEdifici}"
        channels.append({
            "id": channel_id,
            "type": "messaging",
            "kind": "building",
            "name": channel_name,
            "building_id": edifici.idEdifici,
            "stream_channel_id": channel_id,
            "description": "Xat comunitari intern de l'edifici.",
        })

        if (
            (role in (RoleChoices.ADMIN, RoleChoices.OWNER) or user.is_superuser)
            and edifici.grupComparable_id
            and edifici.grupComparable_id not in seen_twin_groups
        ):
            seen_twin_groups.add(edifici.grupComparable_id)
            twin_id = f"twin_group_{edifici.grupComparable_id}_admins"
            channels.append({
                "id": twin_id,
                "type": "messaging",
                "kind": "twin_building",
                "name": f"Twin Building grup {edifici.grupComparable_id}",
                "group_id": edifici.grupComparable_id,
                "stream_channel_id": twin_id,
                "description": "Xat entre administradors d'edificis similars.",
            })

    return channels


def get_or_create_channels_for_user(user) -> list[dict[str, Any]]:
    """
    Punt d'entrada principal per al frontend.

    1. Sincronitza l'usuari a GetStream.
    2. Per cada edifici accessible, crea/obté el canal comunitari.
    3. Per ADMIN/OWNER, crea/obté el canal de twin buildings (un per grup).
    4. Retorna la llista de descriptors de canals.
    """
    client = get_stream_client()
    stream_uid = get_stream_user_id(user)

    sync_user_to_stream(client, user)

    buildings = get_accessible_buildings(user)
    role = getattr(getattr(user, "profile", None), "role", None)

    channels: list[dict[str, Any]] = []
    seen_twin_groups: set[int] = set()

    for edifici in buildings:
        channels.append(_ensure_building_channel(client, edifici, stream_uid))

        if (
            (role in (RoleChoices.ADMIN, RoleChoices.OWNER) or user.is_superuser)
            and edifici.grupComparable_id
            and edifici.grupComparable_id not in seen_twin_groups
        ):
            seen_twin_groups.add(edifici.grupComparable_id)
            channels.append(
                _ensure_twin_group_channel(client, edifici.grupComparable_id, stream_uid)
            )

    return channels


def validate_building_channel_access(user, building_id: int) -> bool:
    """Comprova (costat Django) si l'usuari té accés al canal d'un edifici."""
    return get_accessible_buildings(user).filter(idEdifici=building_id).exists()


def validate_twin_channel_access(user, group_id: int) -> bool:
    """Comprova (costat Django) si l'usuari té accés al canal de twin buildings."""
    role = getattr(getattr(user, "profile", None), "role", None)
    if role == RoleChoices.TENANT and not user.is_superuser:
        return False
    return get_accessible_buildings(user).filter(grupComparable_id=group_id).exists()
