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
        "email": user.email,
        "buildrank_role": role or "",
    }

    if user.is_superuser or role == RoleChoices.ADMIN:
        user_data["role"] = "admin"

    stream_uid = user_data["id"]
    try:
        client.upsert_user(user_data)
    except Exception as exc:
        if "was deleted" not in str(exc):
            raise
        try:
            client.reactivate_user(stream_uid)
            client.upsert_user(user_data)
        except Exception:
            # User was hard-deleted in GetStream and cannot be restored.
            # Log and continue — sync is best-effort.
            logger.warning("No s'ha pogut restaurar l'usuari %s a GetStream (hard-deleted).", stream_uid)


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

def _format_building_address(edifici) -> str:
    loc = getattr(edifici, "localitzacio", None)
    if not loc:
        return f"Edifici {edifici.idEdifici}"

    parts = []
    if loc.carrer:
        parts.append(str(loc.carrer))
    if loc.numero is not None:
        parts.append(str(loc.numero))

    address = " ".join(parts).strip()
    return address or f"Edifici {edifici.idEdifici}"


def _format_user_name(user) -> str:
    full_name = f"{user.first_name} {user.last_name}".strip()
    return full_name or user.email


def _is_admin_finca_of_building(user, edifici) -> bool:
    if not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    role = getattr(getattr(user, "profile", None), "role", None)
    return role == RoleChoices.ADMIN and edifici.administradorFinca_id == user.id


def _is_valid_target_admin(user) -> bool:
    if user is None:
        return False

    if user.is_superuser:
        return True

    role = getattr(getattr(user, "profile", None), "role", None)
    return role == RoleChoices.ADMIN


def _build_twin_admin_descriptor(edifici) -> dict[str, Any]:
    admin = edifici.administradorFinca
    loc = getattr(edifici, "localitzacio", None)

    return {
        "edifici_id": edifici.idEdifici,
        "adreca": _format_building_address(edifici),
        "barri": getattr(loc, "barri", "") if loc else "",
        "codiPostal": getattr(loc, "codiPostal", "") if loc else "",
        "zonaClimatica": getattr(loc, "zonaClimatica", "") if loc else "",
        "tipologia": edifici.tipologia,
        "superficieTotal": edifici.superficieTotal,
        "puntuacioBase": edifici.puntuacioBase,
        "grupComparable": edifici.grupComparable_id,
        "admin": {
            "id": admin.id,
            "stream_user_id": get_stream_user_id(admin),
            "email": admin.email,
            "name": _format_user_name(admin),
        },
    }


def get_twin_building_admin_candidates(user, edifici_id: int) -> list[dict[str, Any]]:
    """
    Retorna administradors de finca d'edificis comparables al de partida.

    Regles:
    - L'usuari ha de ser l'administrador de finca de l'edifici origen.
    - L'edifici origen ha de tenir GrupComparable.
    - Només es retornen edificis actius del mateix grup.
    - No es retorna el propi edifici.
    - No es retorna el mateix administrador.
    - Només es retornen edificis amb administrador de finca vàlid.
    """
    try:
        source = (
            Edifici.objects
            .select_related("localitzacio", "grupComparable", "administradorFinca__profile")
            .get(pk=edifici_id, actiu=True)
        )
    except Edifici.DoesNotExist as exc:
        raise ValueError("No s'ha trobat l'edifici origen.") from exc

    if not _is_admin_finca_of_building(user, source):
        raise PermissionError(
            "Només l'administrador de finca d'aquest edifici pot consultar edificis comparables."
        )

    if not source.grupComparable_id:
        return []

    candidates = (
        Edifici.objects
        .filter(
            actiu=True,
            grupComparable_id=source.grupComparable_id,
            administradorFinca__isnull=False,
        )
        .exclude(pk=source.pk)
        .exclude(administradorFinca_id=user.id)
        .select_related("localitzacio", "grupComparable", "administradorFinca__profile")
        .order_by("idEdifici")
    )

    results: list[dict[str, Any]] = []
    for edifici in candidates:
        if _is_valid_target_admin(edifici.administradorFinca):
            results.append(_build_twin_admin_descriptor(edifici))

    return results


def get_or_create_twin_building_admin_channel(
    user,
    source_edifici_id: int,
    target_edifici_id: int,
) -> dict[str, Any]:
    """
    Crea o obté un canal directe entre dos administradors de finca
    d'edificis del mateix GrupComparable.
    """
    try:
        source = (
            Edifici.objects
            .select_related("localitzacio", "grupComparable", "administradorFinca__profile")
            .get(pk=source_edifici_id, actiu=True)
        )
    except Edifici.DoesNotExist as exc:
        raise ValueError("No s'ha trobat l'edifici origen.") from exc

    if not _is_admin_finca_of_building(user, source):
        raise PermissionError(
            "Només l'administrador de finca d'aquest edifici pot crear el xat Twin Building."
        )

    if not source.grupComparable_id:
        raise ValueError("L'edifici origen no té cap grup comparable assignat.")

    try:
        target = (
            Edifici.objects
            .select_related("localitzacio", "grupComparable", "administradorFinca__profile")
            .get(pk=target_edifici_id, actiu=True)
        )
    except Edifici.DoesNotExist as exc:
        raise ValueError("No s'ha trobat l'edifici destí.") from exc

    if target.pk == source.pk:
        raise ValueError("No es pot crear un xat Twin Building amb el mateix edifici.")

    if target.grupComparable_id != source.grupComparable_id:
        raise ValueError("L'edifici destí no pertany al mateix grup comparable.")

    target_admin = target.administradorFinca
    if not _is_valid_target_admin(target_admin):
        raise ValueError("L'edifici destí no té un administrador de finca vàlid.")

    if target_admin.id == user.id:
        raise ValueError("No es pot crear un xat Twin Building amb un edifici gestionat pel mateix usuari.")

    client = get_stream_client()

    source_stream_uid = get_stream_user_id(user)
    target_stream_uid = get_stream_user_id(target_admin)

    sync_user_to_stream(client, user)
    sync_user_to_stream(client, target_admin)

    source_id = int(source.idEdifici)
    target_id = int(target.idEdifici)
    low_id = min(source_id, target_id)
    high_id = max(source_id, target_id)

    channel_id = f"twin_building_{low_id}_{high_id}_admins"
    channel_name = f"Twin Building: {_format_building_address(source)} ↔ {_format_building_address(target)}"

    channel = client.channel(
        "messaging",
        channel_id,
        data={
            "name": channel_name,
            "kind": "twin_building_direct",
            "source_edifici_id": source.idEdifici,
            "target_edifici_id": target.idEdifici,
            "grup_comparable_id": source.grupComparable_id,
        },
    )
    channel.create(source_stream_uid)
    channel.add_members([source_stream_uid, target_stream_uid])

    return {
        "id": channel_id,
        "type": "messaging",
        "kind": "twin_building_direct",
        "name": channel_name,
        "stream_channel_id": channel_id,
        "source_edifici": _build_twin_admin_descriptor(source),
        "target_edifici": _build_twin_admin_descriptor(target),
        "members": [
            {
                "id": user.id,
                "stream_user_id": source_stream_uid,
                "email": user.email,
                "name": _format_user_name(user),
            },
            {
                "id": target_admin.id,
                "stream_user_id": target_stream_uid,
                "email": target_admin.email,
                "name": _format_user_name(target_admin),
            },
        ],
    }
