import logging
import threading

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import RoleChoices

from .moderation import (
    _is_building_moderator,
    ban_from_channel,
    delete_message,
    dismiss_flag,
    flag_message,
    global_ban,
    global_unban,
    hide_message,
    mute_user,
    restore_message,
    shadow_ban,
    shadow_unban,
    unban_from_channel,
    unmute_user,
    warn_user,
)
from .services import (
    build_channel_descriptors,
    create_stream_token_for_user,
    get_or_create_channels_for_user,
    get_stream_user_id,
)

User = get_user_model()
logger = logging.getLogger(__name__)

def _provision_channels_bg(user):
    try:
        get_or_create_channels_for_user(user)
    except Exception:
        logger.warning("Background provision failed for user %s.", user.id, exc_info=True)


class ChatTokenView(APIView):
    """
    Retorna un token de GetStream per a l'usuari autenticat.

    Sincronitza les dades de l'usuari a GetStream abans d'emetre el token.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = create_stream_token_for_user(request.user)
        except ImproperlyConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception:
            logger.exception(
                "Error generant el token de GetStream per l'usuari %s.", request.user.id
            )
            return Response(
                {"detail": "Error de connexió amb el servei de xat."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        threading.Thread(
            target=_provision_channels_bg,
            args=(request.user,),
            daemon=True,
        ).start()

        return Response({
            "provider": "getstream",
            "api_key": settings.STREAM_API_KEY,
            "user_id": get_stream_user_id(request.user),
            "token": token,
            "expires_in": settings.STREAM_TOKEN_EXPIRATION_SECONDS,
        })


class ChatChannelsView(APIView):
    """
    GET: retorna els canals accessibles per l'usuari basant-se únicament
    en les dades de Django. Cap crida a l'API de GetStream.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        channels = build_channel_descriptors(request.user)
        return Response({"count": len(channels), "results": channels})


class ChatChannelsProvisionView(APIView):
    """
    POST: crea els canals a GetStream si no existeixen i afegeix l'usuari
    com a membre. Retorna la mateixa llista que GET /channels/ però amb
    la garantia que els canals ja existeixen a GetStream.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            channels = get_or_create_channels_for_user(request.user)
        except ImproperlyConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception:
            logger.exception(
                "Error provisionant canals de GetStream per l'usuari %s.", request.user.id
            )
            return Response(
                {"detail": "Error de connexió amb el servei de xat."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({"count": len(channels), "results": channels})


# ---------------------------------------------------------------------------
# Moderation helpers
# ---------------------------------------------------------------------------

def _require_channel_moderator(user, channel_id):
    """Returns None if authorized, else a 403 Response."""
    if not _is_building_moderator(user, channel_id):
        return Response(
            {"detail": "No tens permisos de moderació en aquest canal."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _require_superuser(user):
    if not user.is_superuser:
        return Response(
            {"detail": "Acció reservada a l'administrador de sistema."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _get_target_user(user_id):
    """Returns (user, error_response)."""
    try:
        return User.objects.get(pk=user_id), None
    except User.DoesNotExist:
        return None, Response(
            {"detail": "Usuari no trobat."}, status=status.HTTP_404_NOT_FOUND
        )


# ---------------------------------------------------------------------------
# Message moderation views
# ---------------------------------------------------------------------------

class FlagMessageView(APIView):
    """POST /chat/moderation/messages/{message_id}/flag/  — any member."""
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        try:
            flag_message(request.user, message_id, channel_id, reason=reason)
        except Exception:
            logger.exception("Error flagging message %s", message_id)
            return Response(
                {"detail": "Error en reportar el missatge."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Missatge reportat."}, status=status.HTTP_200_OK)


class HideMessageView(APIView):
    """POST /chat/moderation/messages/{message_id}/hide/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        try:
            hide_message(request.user, message_id, channel_id, reason=reason)
        except Exception:
            logger.exception("Error hiding message %s", message_id)
            return Response(
                {"detail": "Error en ocultar el missatge."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Missatge ocult."}, status=status.HTTP_200_OK)


class DeleteMessageView(APIView):
    """DELETE /chat/moderation/messages/{message_id}/  — author or ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, message_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        is_own = request.data.get("is_own", False)
        if not is_own and not _is_building_moderator(request.user, channel_id):
            return Response(
                {"detail": "No tens permisos per eliminar aquest missatge."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            delete_message(request.user, message_id, channel_id, reason=reason)
        except Exception:
            logger.exception("Error deleting message %s", message_id)
            return Response(
                {"detail": "Error en eliminar el missatge."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Missatge eliminat."}, status=status.HTTP_200_OK)


class RestoreMessageView(APIView):
    """POST /chat/moderation/messages/{message_id}/restore/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        try:
            restore_message(request.user, message_id, channel_id, reason=reason)
        except Exception:
            logger.exception("Error restoring message %s", message_id)
            return Response(
                {"detail": "Error en restaurar el missatge."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Missatge restaurat."}, status=status.HTTP_200_OK)


class DismissFlagView(APIView):
    """POST /chat/moderation/messages/{message_id}/dismiss-flag/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        try:
            dismiss_flag(request.user, message_id, channel_id, reason=reason)
        except Exception:
            logger.exception("Error dismissing flag on message %s", message_id)
            return Response(
                {"detail": "Error en desestimar el report."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Report desestimado."}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# User moderation views
# ---------------------------------------------------------------------------

class WarnUserView(APIView):
    """POST /chat/moderation/users/{user_id}/warn/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            warn_user(request.user, target, channel_id, reason=reason)
        except Exception:
            logger.exception("Error warning user %s", user_id)
            return Response(
                {"detail": "Error en advertir l'usuari."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Usuari advertit."}, status=status.HTTP_200_OK)


class MuteUserView(APIView):
    """POST /chat/moderation/users/{user_id}/mute/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        timeout = int(request.data.get("timeout", 60))
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            mute_user(request.user, target, channel_id, timeout=timeout, reason=reason)
        except Exception:
            logger.exception("Error muting user %s", user_id)
            return Response(
                {"detail": "Error en silenciar l'usuari."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Usuari silenciat."}, status=status.HTTP_200_OK)


class UnmuteUserView(APIView):
    """POST /chat/moderation/users/{user_id}/unmute/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            unmute_user(request.user, target, channel_id, reason=reason)
        except Exception:
            logger.exception("Error unmuting user %s", user_id)
            return Response(
                {"detail": "Error en dessilenciar l'usuari."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Usuari dessilenciat."}, status=status.HTTP_200_OK)


class BanFromChannelView(APIView):
    """POST /chat/moderation/users/{user_id}/ban/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        timeout = request.data.get("timeout")
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            ban_from_channel(
                request.user, target, channel_id, reason=reason,
                timeout=int(timeout) if timeout else None,
            )
        except Exception:
            logger.exception("Error banning user %s from channel", user_id)
            return Response(
                {"detail": "Error en expulsar l'usuari del canal."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Usuari expulsat del canal."}, status=status.HTTP_200_OK)


class UnbanFromChannelView(APIView):
    """POST /chat/moderation/users/{user_id}/unban/  — ADMIN/superuser."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        channel_id = request.data.get("channel_id", "")
        reason = request.data.get("reason", "")
        if err := _require_channel_moderator(request.user, channel_id):
            return err
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            unban_from_channel(request.user, target, channel_id, reason=reason)
        except Exception:
            logger.exception("Error unbanning user %s from channel", user_id)
            return Response(
                {"detail": "Error en readmetre l'usuari al canal."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Usuari readmès al canal."}, status=status.HTTP_200_OK)


class GlobalBanView(APIView):
    """POST /chat/moderation/users/{user_id}/global-ban/  — superuser only."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if err := _require_superuser(request.user):
            return err
        reason = request.data.get("reason", "")
        timeout = request.data.get("timeout")
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            global_ban(
                request.user, target, reason=reason,
                timeout=int(timeout) if timeout else None,
            )
        except Exception:
            logger.exception("Error global-banning user %s", user_id)
            return Response(
                {"detail": "Error en l'expulsió global."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Usuari expulsat globalment."}, status=status.HTTP_200_OK)


class GlobalUnbanView(APIView):
    """POST /chat/moderation/users/{user_id}/global-unban/  — superuser only."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if err := _require_superuser(request.user):
            return err
        reason = request.data.get("reason", "")
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            global_unban(request.user, target, reason=reason)
        except Exception:
            logger.exception("Error global-unbanning user %s", user_id)
            return Response(
                {"detail": "Error en aixecar l'expulsió global."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Expulsió global aixecada."}, status=status.HTTP_200_OK)


class ShadowBanView(APIView):
    """POST /chat/moderation/users/{user_id}/shadow-ban/  — superuser only."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if err := _require_superuser(request.user):
            return err
        reason = request.data.get("reason", "")
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            shadow_ban(request.user, target, reason=reason)
        except Exception:
            logger.exception("Error shadow-banning user %s", user_id)
            return Response(
                {"detail": "Error en el shadow ban."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Shadow ban aplicat."}, status=status.HTTP_200_OK)


class ShadowUnbanView(APIView):
    """POST /chat/moderation/users/{user_id}/shadow-unban/  — superuser only."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if err := _require_superuser(request.user):
            return err
        reason = request.data.get("reason", "")
        target, err = _get_target_user(user_id)
        if err:
            return err
        try:
            shadow_unban(request.user, target, reason=reason)
        except Exception:
            logger.exception("Error shadow-unbanning user %s", user_id)
            return Response(
                {"detail": "Error en aixecar el shadow ban."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"detail": "Shadow ban aixecat."}, status=status.HTTP_200_OK)
