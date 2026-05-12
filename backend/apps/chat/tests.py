from unittest.mock import patch

import jwt
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User


class ChatTokenTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="chatuser@example.com",
            password="StrongPass123!",
        )

    @override_settings(
        STREAM_API_KEY="test_stream_key",
        STREAM_API_SECRET="test_stream_secret_for_buildrank_tests_32_chars",
        STREAM_TOKEN_EXPIRATION_SECONDS=3600,
    )
    def test_authenticated_user_can_get_stream_token(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(reverse("chat-token"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["provider"], "getstream")
        self.assertEqual(response.data["api_key"], "test_stream_key")
        self.assertEqual(response.data["user_id"], f"user_{self.user.id}")
        self.assertIn("token", response.data)

        decoded = jwt.decode(
            response.data["token"],
            "test_stream_secret_for_buildrank_tests_32_chars",
            algorithms=["HS256"],
        )
        self.assertEqual(decoded["user_id"], f"user_{self.user.id}")

    def test_anonymous_user_cannot_get_stream_token(self):
        response = self.client.post(reverse("chat-token"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(
        STREAM_API_KEY="test_stream_key",
        STREAM_API_SECRET="",
        STREAM_TOKEN_EXPIRATION_SECONDS=3600,
    )
    def test_missing_stream_secret_returns_503(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(reverse("chat-token"))

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("STREAM_API_SECRET", response.data["detail"])


class ChatChannelsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="channels@example.com",
            password="StrongPass123!",
        )

    def test_anonymous_user_cannot_list_channels(self):
        response = self.client.get(reverse("chat-channels"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("apps.chat.views.build_channel_descriptors")
    def test_authenticated_user_can_list_channels(self, mocked_builder):
        mocked_builder.return_value = [
            {
                "id": "building_1",
                "type": "messaging",
                "kind": "building",
                "name": "Comunitat edifici 1",
                "building_id": 1,
                "stream_channel_id": "building_1",
                "description": "Xat comunitari intern de l'edifici.",
            }
        ]

        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("chat-channels"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], "building_1")
        mocked_builder.assert_called_once_with(self.user)