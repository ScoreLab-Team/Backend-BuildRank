import logging

from apps.accounts.models import RoleChoices
from apps.buildings.models import Edifici

from .models import ModerationLog
from .services import get_stream_client, get_stream_user_id, validate_twin_channel_access

logger = logging.getLogger(__name__)


def _moderator_role_label(user) -> str:
    if user.is_superuser:
        return "superuser"
    return getattr(getattr(user, "profile", None), "role", "") or ""


def _is_building_moderator(user, channel_id: str) -> bool:
    """
    Validates that user has moderation rights over the given channel (ABAC).
    Superuser: always. ADMIN: only for buildings they administer.
    """
    if user.is_superuser:
        return True
    role = getattr(getattr(user, "profile", None), "role", None)
    if role != RoleChoices.ADMIN:
        return False

    if channel_id.startswith("building_"):
        try:
            building_id = int(channel_id.split("_")[1])
        except (IndexError, ValueError):
            return False
        return Edifici.objects.filter(
            idEdifici=building_id, administradorFinca=user, actiu=True
        ).exists()

    if channel_id.startswith("twin_group_"):
        try:
            group_id = int(channel_id.split("_")[2])
        except (IndexError, ValueError):
            return False
        return validate_twin_channel_access(user, group_id)

    return False


def _log(moderator, action, channel_id, *, target_user=None, target_message_id="",
         reason="", previous_state="", new_state=""):
    ModerationLog.objects.create(
        moderator=moderator,
        moderator_role=_moderator_role_label(moderator),
        target_user=target_user,
        target_message_id=target_message_id,
        channel_id=channel_id,
        action=action,
        reason=reason,
        previous_state=previous_state,
        new_state=new_state,
    )


# ---------------------------------------------------------------------------
# Message moderation
# ---------------------------------------------------------------------------

def flag_message(actor, message_id: str, channel_id: str, reason: str = "") -> None:
    """Any channel member can flag a message. visible → flagged."""
    client = get_stream_client()
    actor_uid = get_stream_user_id(actor)
    client.flag_message(message_id, user_id=actor_uid)
    _log(actor, "flag_message", channel_id, target_message_id=message_id,
         reason=reason, previous_state="visible", new_state="flagged")


def hide_message(moderator, message_id: str, channel_id: str, reason: str = "") -> None:
    """Moderator hides a message: replaces content with a placeholder. visible → hidden."""
    client = get_stream_client()
    # update_message omits user_id and GetStream rejects it; update_message_partial
    # includes the user context required by the API and only patches specified fields.
    client.update_message_partial(
        message_id,
        {"set": {"text": "[Missatge ocult per moderació]", "moderated": True}},
        get_stream_user_id(moderator),
    )
    _log(moderator, "hide_message", channel_id, target_message_id=message_id,
         reason=reason, previous_state="visible", new_state="hidden")


def delete_message(actor, message_id: str, channel_id: str, reason: str = "") -> None:
    """Delete a message permanently (soft-delete in GetStream timeline)."""
    client = get_stream_client()
    # SDK v4: delete_message exists on the client, not on the channel object.
    client.delete_message(message_id)
    _log(actor, "delete_message", channel_id, target_message_id=message_id,
         reason=reason, previous_state="visible", new_state="deleted")


def restore_message(moderator, message_id: str, channel_id: str, reason: str = "") -> None:
    """Clear moderation flag on a hidden message. hidden → visible.

    Note: the original message text is not recoverable once overwritten by hide_message.
    This call only clears the moderated:True custom field.
    """
    client = get_stream_client()
    client.update_message_partial(
        message_id,
        {"set": {"moderated": False}},
        get_stream_user_id(moderator),
    )
    _log(moderator, "restore_message", channel_id, target_message_id=message_id,
         reason=reason, previous_state="hidden", new_state="visible")


def dismiss_flag(moderator, message_id: str, channel_id: str, reason: str = "") -> None:
    """Dismiss a flag on a message, returning it to visible."""
    client = get_stream_client()
    moderator_uid = get_stream_user_id(moderator)
    client.unflag_message(message_id, user_id=moderator_uid)
    _log(moderator, "dismiss_flag", channel_id, target_message_id=message_id,
         reason=reason, previous_state="flagged", new_state="visible")


# ---------------------------------------------------------------------------
# User moderation
# ---------------------------------------------------------------------------

def warn_user(moderator, target_user, channel_id: str, reason: str = "") -> None:
    """Warn a user (metadata stored in GetStream). active → warned."""
    client = get_stream_client()
    target_uid = get_stream_user_id(target_user)
    client.upsert_user({"id": target_uid, "moderation_state": "warned"})
    _log(moderator, "warn_user", channel_id, target_user=target_user,
         reason=reason, previous_state="active", new_state="warned")


def mute_user(moderator, target_user, channel_id: str,
              timeout: int = 60, reason: str = "") -> None:
    """Mute a user in the channel. active/warned → muted."""
    client = get_stream_client()
    moderator_uid = get_stream_user_id(moderator)
    target_uid = get_stream_user_id(target_user)
    client.mute_user(target_uid, moderator_uid, timeout=timeout)
    _log(moderator, "mute_user", channel_id, target_user=target_user,
         reason=reason, previous_state="active", new_state="muted")


def unmute_user(moderator, target_user, channel_id: str, reason: str = "") -> None:
    """Unmute a user. muted → active."""
    client = get_stream_client()
    moderator_uid = get_stream_user_id(moderator)
    target_uid = get_stream_user_id(target_user)
    client.unmute_user(target_uid, moderator_uid)
    _log(moderator, "unmute_user", channel_id, target_user=target_user,
         reason=reason, previous_state="muted", new_state="active")


def ban_from_channel(moderator, target_user, channel_id: str,
                     reason: str = "", timeout: int = None) -> None:
    """Ban a user from a specific channel. * → channel_banned."""
    client = get_stream_client()
    channel_type, _, channel_name = _parse_channel(channel_id)
    channel = client.channel(channel_type, channel_name)
    ban_kwargs = {"reason": reason or "Expulsat per moderador"}
    if timeout:
        ban_kwargs["timeout"] = timeout
    channel.ban_user(get_stream_user_id(target_user), **ban_kwargs)
    _log(moderator, "ban_from_channel", channel_id, target_user=target_user,
         reason=reason, previous_state="active", new_state="channel_banned")


def unban_from_channel(moderator, target_user, channel_id: str, reason: str = "") -> None:
    """Readmit a user to a channel. channel_banned → active."""
    client = get_stream_client()
    channel_type, _, channel_name = _parse_channel(channel_id)
    channel = client.channel(channel_type, channel_name)
    channel.unban_user(get_stream_user_id(target_user))
    _log(moderator, "unban_from_channel", channel_id, target_user=target_user,
         reason=reason, previous_state="channel_banned", new_state="active")


def global_ban(moderator, target_user, reason: str = "", timeout: int = None) -> None:
    """Global ban — superuser only. * → global_banned."""
    client = get_stream_client()
    ban_kwargs = {"reason": reason or "Expulsió global"}
    if timeout:
        ban_kwargs["timeout"] = timeout
    client.ban_user(get_stream_user_id(target_user), **ban_kwargs)
    _log(moderator, "global_ban", "", target_user=target_user,
         reason=reason, previous_state="active", new_state="global_banned")


def global_unban(moderator, target_user, reason: str = "") -> None:
    """Lift global ban — superuser only."""
    client = get_stream_client()
    client.unban_user(get_stream_user_id(target_user))
    _log(moderator, "global_unban", "", target_user=target_user,
         reason=reason, previous_state="global_banned", new_state="active")


def shadow_ban(moderator, target_user, reason: str = "") -> None:
    """Shadow ban — superuser only. * → shadow_banned."""
    client = get_stream_client()
    client.ban_user(get_stream_user_id(target_user), shadow=True,
                    reason=reason or "Shadow ban")
    _log(moderator, "shadow_ban", "", target_user=target_user,
         reason=reason, previous_state="active", new_state="shadow_banned")


def shadow_unban(moderator, target_user, reason: str = "") -> None:
    """Lift shadow ban — superuser only."""
    client = get_stream_client()
    client.unban_user(get_stream_user_id(target_user))
    _log(moderator, "shadow_unban", "", target_user=target_user,
         reason=reason, previous_state="shadow_banned", new_state="active")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_channel(channel_id: str) -> tuple[str, str, str]:
    """Returns (channel_type, separator, channel_name) for GetStream SDK."""
    return "messaging", ":", channel_id
