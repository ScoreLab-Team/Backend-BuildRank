from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    build_channel_descriptors,
    create_stream_token_for_user,
    get_stream_user_id,
)


class ChatTokenView(APIView):
    """
    Retorna un token de GetStream per a l'usuari autenticat.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = create_stream_token_for_user(request.user)
        except ImproperlyConfigured as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response({
            "provider": "getstream",
            "api_key": settings.STREAM_API_KEY,
            "user_id": get_stream_user_id(request.user),
            "token": token,
            "expires_in": settings.STREAM_TOKEN_EXPIRATION_SECONDS,
        })


class ChatChannelsView(APIView):
    """
    Retorna els canals de xat accessibles per l'usuari autenticat.

    Aquesta primera versió no sincronitza encara amb GetStream.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        channels = build_channel_descriptors(request.user)

        return Response({
            "count": len(channels),
            "results": channels,
        })