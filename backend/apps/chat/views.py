import logging
import threading

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    build_channel_descriptors,
    create_stream_token_for_user,
    get_or_create_channels_for_user,
    get_or_create_twin_building_admin_channel,
    get_stream_user_id,
    get_twin_building_admin_candidates,
)

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


class TwinBuildingAdminsView(APIView):
    """
    GET: retorna administradors de finca d'edificis del mateix GrupComparable.

    Només pot consultar-ho l'administrador de finca de l'edifici origen.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, edifici_id):
        try:
            admins = get_twin_building_admin_candidates(request.user, edifici_id)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception(
                "Error consultant admins Twin Building per l'edifici %s i usuari %s.",
                edifici_id,
                request.user.id,
            )
            return Response(
                {"detail": "Error consultant administradors d'edificis comparables."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            "count": len(admins),
            "results": admins,
        })


class TwinBuildingChannelView(APIView):
    """
    POST: crea o obté un canal directe entre dos administradors de finca
    d'edificis del mateix GrupComparable.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, edifici_id):
        target_edifici_id = request.data.get("target_edifici_id")

        if target_edifici_id is None:
            return Response(
                {"detail": "Cal informar 'target_edifici_id'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target_edifici_id = int(target_edifici_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "'target_edifici_id' ha de ser un enter."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            channel = get_or_create_twin_building_admin_channel(
                request.user,
                edifici_id,
                target_edifici_id,
            )
        except ImproperlyConfigured as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception(
                "Error creant canal Twin Building entre edifici %s i edifici %s per usuari %s.",
                edifici_id,
                target_edifici_id,
                request.user.id,
            )
            return Response(
                {"detail": "Error de connexió amb el servei de xat."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(channel, status=status.HTTP_200_OK)
