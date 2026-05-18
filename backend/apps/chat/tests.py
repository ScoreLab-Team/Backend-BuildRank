from unittest.mock import MagicMock, patch

import jwt
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Profile, RoleChoices, User
from apps.buildings.models import Edifici, GrupComparable, Habitatge, Localitzacio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_stream_client():
    """Returns (mock_client, mock_channel) with sensible defaults."""
    mock_client = MagicMock()
    mock_channel = MagicMock()
    mock_client.channel.return_value = mock_channel
    mock_channel.create.return_value = {"channel": {"id": "test"}}
    mock_channel.add_members.return_value = {"members": []}
    mock_client.upsert_user.return_value = {"users": {}}
    mock_client.create_token.return_value = "mock.jwt.token"
    return mock_client, mock_channel


def _create_building(owner=None, grup=None):
    loc = Localitzacio.objects.create(
        carrer="Carrer Major",
        numero=1,
        codiPostal="08001",
        barri="Barri Gòtic",
    )
    return Edifici.objects.create(
        anyConstruccio=2000,
        tipologia="Residencial",
        superficieTotal=500.0,
        reglament="CTE",
        orientacioPrincipal="Sud",
        localitzacio=loc,
        administradorFinca=owner,
        grupComparable=grup,
    )


def _set_role(user, role):
    """El signal de accounts ja crea el Profile; aquí només actualitzem el rol."""
    user.profile.role = role
    user.profile.save()


def _create_grup():
    return GrupComparable.objects.create(
        idGrup=1,
        zonaClimatica="C2",
        tipologia="Residencial",
        rangSuperficie="200-500",
    )


# ---------------------------------------------------------------------------
# Token endpoint tests
# ---------------------------------------------------------------------------

@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class ChatTokenTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="chatuser@example.com",
            password="StrongPass123!",
        )

    @override_settings(
        STREAM_API_KEY="test_key",
        STREAM_API_SECRET="test_secret_for_buildrank_tests_32_chars",
        STREAM_TOKEN_EXPIRATION_SECONDS=3600,
    )
    @patch("apps.chat.services.sync_user_to_stream")
    @patch("apps.chat.services.StreamChat")
    def test_authenticated_user_can_get_stream_token(self, mock_stream_class, mock_sync):
        secret = "test_secret_for_buildrank_tests_32_chars"
        mock_client = MagicMock()
        mock_client.create_token.return_value = jwt.encode(
            {"user_id": f"user_{self.user.id}", "exp": 9999999999},
            secret,
            algorithm="HS256",
        )
        mock_stream_class.return_value = mock_client

        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("chat-token"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["provider"], "getstream")
        self.assertEqual(response.data["api_key"], "test_key")
        self.assertEqual(response.data["user_id"], f"user_{self.user.id}")
        self.assertIn("token", response.data)

        decoded = jwt.decode(response.data["token"], secret, algorithms=["HS256"])
        self.assertEqual(decoded["user_id"], f"user_{self.user.id}")

    def test_anonymous_user_cannot_get_stream_token(self):
        response = self.client.post(reverse("chat-token"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(STREAM_API_KEY="", STREAM_API_SECRET="", STREAM_TOKEN_EXPIRATION_SECONDS=3600)
    def test_missing_stream_credentials_returns_503(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("chat-token"))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("STREAM_API_KEY", response.data["detail"])

    @override_settings(
        STREAM_API_KEY="k", STREAM_API_SECRET="s", STREAM_TOKEN_EXPIRATION_SECONDS=3600
    )
    @patch("apps.chat.views.logger")
    @patch("apps.chat.services.StreamChat", side_effect=Exception("network error"))
    def test_stream_sdk_error_on_token_returns_503(self, _, __):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("chat-token"))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @override_settings(
        STREAM_API_KEY="k", STREAM_API_SECRET="s", STREAM_TOKEN_EXPIRATION_SECONDS=3600
    )
    @patch("apps.chat.views.get_or_create_channels_for_user")
    @patch("apps.chat.services.logger")
    @patch("apps.chat.services.sync_user_to_stream", side_effect=Exception("stream down"))
    @patch("apps.chat.services.StreamChat")
    def test_sync_failure_does_not_block_token_generation(self, mock_stream_class, _, __, ___):
        mock_client = MagicMock()
        mock_client.create_token.return_value = "valid.token"
        mock_stream_class.return_value = mock_client

        self.client.force_authenticate(user=self.user)
        response = self.client.post(reverse("chat-token"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], "valid.token")


# ---------------------------------------------------------------------------
# GET /api/chat/channels/ — lectura pura (sense GetStream)
# ---------------------------------------------------------------------------

@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class ChatChannelsViewTests(APITestCase):
    def setUp(self):
        self.grup = _create_grup()
        self.owner = User.objects.create_user(email="view_owner@example.com", password="Pass123!")
        _set_role(self.owner, RoleChoices.OWNER)
        self.edifici = _create_building(owner=self.owner, grup=self.grup)

    def test_anonymous_cannot_list_channels(self):
        response = self.client.get(reverse("chat-channels"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_returns_channel_list_without_getstream_calls(self):
        self.client.force_authenticate(user=self.owner)
        # No mock needed — GET no ha de fer cap crida a GetStream
        response = self.client.get(reverse("chat-channels"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)

    def test_owner_sees_building_and_twin_channels(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("chat-channels"))

        kinds = {ch["kind"] for ch in response.data["results"]}
        self.assertIn("building", kinds)
        self.assertIn("twin_building", kinds)

    def test_tenant_sees_only_building_channel(self):
        tenant = User.objects.create_user(email="view_tenant@example.com", password="Pass123!")
        _set_role(tenant, RoleChoices.TENANT)
        Habitatge.objects.create(
            referenciaCadastral="VIEW001",
            planta="1", porta="1A", superficie=80.0,
            edifici=self.edifici, usuari=tenant,
        )
        self.client.force_authenticate(user=tenant)
        response = self.client.get(reverse("chat-channels"))

        kinds = {ch["kind"] for ch in response.data["results"]}
        self.assertIn("building", kinds)
        self.assertNotIn("twin_building", kinds)


# ---------------------------------------------------------------------------
# POST /api/chat/channels/provision/ — provisiona a GetStream
# ---------------------------------------------------------------------------

@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class ChatChannelsProvisionViewTests(APITestCase):
    def test_anonymous_cannot_provision(self):
        response = self.client.post(reverse("chat-channels-provision"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("apps.chat.views.get_or_create_channels_for_user")
    def test_provision_calls_getstream_and_returns_channels(self, mock_get):
        user = User.objects.create_user(email="prov@example.com", password="Pass123!")
        mock_get.return_value = [
            {"id": "building_1", "kind": "building", "type": "messaging"},
        ]
        self.client.force_authenticate(user=user)
        response = self.client.post(reverse("chat-channels-provision"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        mock_get.assert_called_once_with(user)

    @override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
    def test_missing_credentials_returns_503(self):
        user = User.objects.create_user(email="nocred_p@example.com", password="Pass123!")
        self.client.force_authenticate(user=user)
        response = self.client.post(reverse("chat-channels-provision"))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch("apps.chat.views.logger")
    @patch("apps.chat.services.get_stream_client")
    @patch(
        "apps.chat.views.get_or_create_channels_for_user",
        side_effect=Exception("stream error"),
    )
    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    def test_stream_error_returns_503(self, _, __, ___):
        user = User.objects.create_user(email="err_p@example.com", password="Pass123!")
        self.client.force_authenticate(user=user)
        response = self.client.post(reverse("chat-channels-provision"))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)


# ---------------------------------------------------------------------------
# Channel provisioning — service layer
# ---------------------------------------------------------------------------

@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class ChannelProvisioningTests(APITestCase):
    def setUp(self):
        self.grup = _create_grup()

        self.owner = User.objects.create_user(email="owner@example.com", password="Pass123!")
        _set_role(self.owner, RoleChoices.OWNER)

        self.tenant = User.objects.create_user(email="tenant@example.com", password="Pass123!")
        _set_role(self.tenant, RoleChoices.TENANT)

        self.admin = User.objects.create_user(email="admin@example.com", password="Pass123!")
        _set_role(self.admin, RoleChoices.ADMIN)

        self.edifici = _create_building(owner=self.owner, grup=self.grup)

        Habitatge.objects.create(
            referenciaCadastral="TEST001",
            planta="1",
            porta="1A",
            superficie=80.0,
            edifici=self.edifici,
            usuari=self.tenant,
        )

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_owner_gets_building_and_twin_channels(self, mock_get_client):
        mock_client, _ = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        channels = get_or_create_channels_for_user(self.owner)
        channel_ids = {ch["id"] for ch in channels}

        self.assertIn(f"building_{self.edifici.idEdifici}", channel_ids)
        self.assertIn(f"twin_group_{self.grup.id}_admins", channel_ids)

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_tenant_gets_only_building_channel(self, mock_get_client):
        mock_client, _ = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        channels = get_or_create_channels_for_user(self.tenant)
        channel_ids = {ch["id"] for ch in channels}

        self.assertIn(f"building_{self.edifici.idEdifici}", channel_ids)
        self.assertFalse(any(ch["kind"] == "twin_building" for ch in channels))

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_admin_gets_building_and_twin_channels_for_all_buildings(self, mock_get_client):
        mock_client, _ = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        channels = get_or_create_channels_for_user(self.admin)
        kinds = {ch["kind"] for ch in channels}

        self.assertIn("building", kinds)
        self.assertIn("twin_building", kinds)

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_twin_group_deduplicated_across_multiple_buildings(self, mock_get_client):
        # Afegim un segon edifici al mateix grup comparable
        _create_building(owner=self.owner, grup=self.grup)

        mock_client, _ = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        channels = get_or_create_channels_for_user(self.owner)
        twin_channels = [ch for ch in channels if ch["kind"] == "twin_building"]

        self.assertEqual(len(twin_channels), 1, "El canal twin ha d'aparèixer una sola vegada")

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_channel_create_and_add_members_called(self, mock_get_client):
        mock_client, mock_channel = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        get_or_create_channels_for_user(self.owner)

        owner_stream_id = f"user_{self.owner.id}"
        mock_channel.create.assert_called()
        mock_channel.add_members.assert_any_call(
            [{"user_id": owner_stream_id, "channel_role": "channel_moderator"}]
        )

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_user_synced_before_channel_provisioning(self, mock_get_client):
        mock_client, _ = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        get_or_create_channels_for_user(self.owner)

        mock_client.upsert_user.assert_called_once()
        call_args = mock_client.upsert_user.call_args[0][0]
        self.assertEqual(call_args["id"], f"user_{self.owner.id}")
        self.assertNotIn("buildrank_role", call_args)

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_admin_user_synced_with_stream_admin_role(self, mock_get_client):
        mock_client, _ = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        get_or_create_channels_for_user(self.admin)

        call_args = mock_client.upsert_user.call_args[0][0]
        self.assertEqual(call_args.get("role"), "admin")

    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.get_stream_client")
    def test_building_without_comparable_group_has_no_twin_channel(self, mock_get_client):
        owner2 = User.objects.create_user(email="owner2@example.com", password="Pass123!")
        _set_role(owner2, RoleChoices.OWNER)
        _create_building(owner=owner2, grup=None)

        mock_client, _ = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        from apps.chat.services import get_or_create_channels_for_user

        channels = get_or_create_channels_for_user(owner2)

        self.assertFalse(any(ch["kind"] == "twin_building" for ch in channels))


# ---------------------------------------------------------------------------
# Permission validation — service layer
# ---------------------------------------------------------------------------

@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class ChannelPermissionTests(APITestCase):
    def setUp(self):
        self.grup = GrupComparable.objects.create(
            idGrup=2,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="200-500",
        )

        self.owner = User.objects.create_user(email="owner_p@example.com", password="Pass123!")
        _set_role(self.owner, RoleChoices.OWNER)

        self.tenant = User.objects.create_user(email="tenant_p@example.com", password="Pass123!")
        _set_role(self.tenant, RoleChoices.TENANT)

        self.outsider = User.objects.create_user(email="outsider@example.com", password="Pass123!")
        _set_role(self.outsider, RoleChoices.TENANT)

        self.edifici = _create_building(owner=self.owner, grup=self.grup)

        Habitatge.objects.create(
            referenciaCadastral="PERM001",
            planta="1",
            porta="1A",
            superficie=80.0,
            edifici=self.edifici,
            usuari=self.tenant,
        )

    def test_owner_can_access_their_building_channel(self):
        from apps.chat.services import validate_building_channel_access

        self.assertTrue(validate_building_channel_access(self.owner, self.edifici.idEdifici))

    def test_tenant_can_access_their_building_channel(self):
        from apps.chat.services import validate_building_channel_access

        self.assertTrue(validate_building_channel_access(self.tenant, self.edifici.idEdifici))

    def test_outsider_cannot_access_building_channel(self):
        from apps.chat.services import validate_building_channel_access

        self.assertFalse(validate_building_channel_access(self.outsider, self.edifici.idEdifici))

    def test_tenant_cannot_access_twin_channel(self):
        from apps.chat.services import validate_twin_channel_access

        self.assertFalse(validate_twin_channel_access(self.tenant, self.grup.id))

    def test_owner_can_access_twin_channel(self):
        from apps.chat.services import validate_twin_channel_access

        self.assertTrue(validate_twin_channel_access(self.owner, self.grup.id))

    def test_outsider_cannot_access_twin_channel(self):
        from apps.chat.services import validate_twin_channel_access

        self.assertFalse(validate_twin_channel_access(self.outsider, self.grup.id))

    def test_unknown_building_id_returns_false(self):
        from apps.chat.services import validate_building_channel_access

        self.assertFalse(validate_building_channel_access(self.owner, 999999))

    def test_unknown_group_id_returns_false(self):
        from apps.chat.services import validate_twin_channel_access

        self.assertFalse(validate_twin_channel_access(self.owner, 999999))


# ---------------------------------------------------------------------------
# Moderation: _is_building_moderator
# ---------------------------------------------------------------------------

class IsBuildingModeratorTests(APITestCase):
    def setUp(self):
        self.grup = GrupComparable.objects.create(nom="G1", criteris="c")
        self.admin = User.objects.create_user(email="admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.admin.profile.save()

        self.other_admin = User.objects.create_user(email="other@test.com", password="pw")
        _set_role(self.other_admin, RoleChoices.ADMIN)
        self.other_admin.profile.save()

        self.tenant = User.objects.create_user(email="tenant@test.com", password="pw")
        _set_role(self.tenant, RoleChoices.TENANT)
        self.tenant.profile.save()

        self.superuser = User.objects.create_superuser(email="su@test.com", password="pw")

        self.edifici = _create_building(owner=self.admin, grup=self.grup)

    def test_superuser_always_can_moderate(self):
        from apps.chat.moderation import _is_building_moderator
        self.assertTrue(_is_building_moderator(self.superuser, f"building_{self.edifici.idEdifici}"))

    def test_admin_can_moderate_own_building(self):
        from apps.chat.moderation import _is_building_moderator
        self.assertTrue(_is_building_moderator(self.admin, f"building_{self.edifici.idEdifici}"))

    def test_admin_cannot_moderate_other_building(self):
        from apps.chat.moderation import _is_building_moderator
        self.assertFalse(_is_building_moderator(self.other_admin, f"building_{self.edifici.idEdifici}"))

    def test_tenant_cannot_moderate(self):
        from apps.chat.moderation import _is_building_moderator
        self.assertFalse(_is_building_moderator(self.tenant, f"building_{self.edifici.idEdifici}"))

    def test_invalid_channel_returns_false(self):
        from apps.chat.moderation import _is_building_moderator
        self.assertFalse(_is_building_moderator(self.admin, "unknown_channel_format"))


# ---------------------------------------------------------------------------
# Moderation endpoints — permission checks
# ---------------------------------------------------------------------------

@override_settings(
    STREAM_API_KEY="test-key",
    STREAM_API_SECRET="test-secret",
    STREAM_TOKEN_EXPIRATION_SECONDS=3600,
)
class ModerationPermissionTests(APITestCase):
    def setUp(self):
        self.grup = GrupComparable.objects.create(nom="G2", criteris="c")
        self.admin = User.objects.create_user(email="mod_admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.admin.profile.save()

        self.tenant = User.objects.create_user(email="mod_tenant@test.com", password="pw")
        _set_role(self.tenant, RoleChoices.TENANT)
        self.tenant.profile.save()

        self.superuser = User.objects.create_superuser(email="mod_su@test.com", password="pw")
        self.target = User.objects.create_user(email="mod_target@test.com", password="pw")
        _set_role(self.target, RoleChoices.TENANT)
        self.target.profile.save()

        self.edifici = _create_building(owner=self.admin, grup=self.grup)
        self.channel_id = f"building_{self.edifici.idEdifici}"

    def _post(self, url, user, data=None):
        self.client.force_authenticate(user=user)
        return self.client.post(url, data or {}, format="json")

    def _delete(self, url, user, data=None):
        self.client.force_authenticate(user=user)
        return self.client.delete(url, data or {}, format="json")

    # --- flag_message: any authenticated user ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_tenant_can_flag_message(self, mock_client_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-flag-message", kwargs={"message_id": "msg-1"})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)

    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_flag_message(self, mock_client_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-flag-message", kwargs={"message_id": "msg-2"})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_cannot_flag(self):
        url = reverse("chat-flag-message", kwargs={"message_id": "msg-3"})
        resp = self.client.post(url, {}, format="json")
        self.assertEqual(resp.status_code, 401)

    # --- hide_message: only ADMIN of building or superuser ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_hide_message_in_own_building(self, mock_client_fn):
        mock_client, mock_channel = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-hide-message", kwargs={"message_id": "msg-4"})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)

    def test_tenant_cannot_hide_message(self):
        url = reverse("chat-hide-message", kwargs={"message_id": "msg-5"})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)

    @patch("apps.chat.moderation.get_stream_client")
    def test_superuser_can_hide_message(self, mock_client_fn):
        mock_client, mock_channel = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-hide-message", kwargs={"message_id": "msg-6"})
        resp = self._post(url, self.superuser, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)

    # --- delete_message: author (is_own=True) or moderator ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_tenant_can_delete_own_message(self, mock_client_fn):
        mock_client, mock_channel = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-delete-message", kwargs={"message_id": "msg-7"})
        resp = self._delete(url, self.tenant, {"channel_id": self.channel_id, "is_own": True})
        self.assertEqual(resp.status_code, 200)

    def test_tenant_cannot_delete_others_message(self):
        url = reverse("chat-delete-message", kwargs={"message_id": "msg-8"})
        resp = self._delete(url, self.tenant, {"channel_id": self.channel_id, "is_own": False})
        self.assertEqual(resp.status_code, 403)

    # --- warn_user: only ADMIN/superuser ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_warn_user(self, mock_client_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-warn-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)

    def test_tenant_cannot_warn_user(self):
        url = reverse("chat-warn-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)

    # --- mute_user ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_mute_user(self, mock_client_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-mute-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id, "timeout": 30})
        self.assertEqual(resp.status_code, 200)

    def test_tenant_cannot_mute_user(self):
        url = reverse("chat-mute-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)

    # --- global_ban: superuser only ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_superuser_can_global_ban(self, mock_client_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-global-ban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.superuser, {"reason": "spam"})
        self.assertEqual(resp.status_code, 200)

    def test_admin_cannot_global_ban(self):
        url = reverse("chat-global-ban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"reason": "spam"})
        self.assertEqual(resp.status_code, 403)

    def test_tenant_cannot_global_ban(self):
        url = reverse("chat-global-ban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.tenant, {"reason": "spam"})
        self.assertEqual(resp.status_code, 403)

    # --- shadow_ban: superuser only ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_superuser_can_shadow_ban(self, mock_client_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-shadow-ban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.superuser, {})
        self.assertEqual(resp.status_code, 200)

    def test_admin_cannot_shadow_ban(self):
        url = reverse("chat-shadow-ban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {})
        self.assertEqual(resp.status_code, 403)

    # --- ModerationLog is created ---

    @patch("apps.chat.moderation.get_stream_client")
    def test_warn_creates_moderation_log(self, mock_client_fn):
        from apps.chat.models import ModerationLog
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-warn-user", kwargs={"user_id": self.target.id})
        self._post(url, self.admin, {"channel_id": self.channel_id, "reason": "test"})
        log = ModerationLog.objects.filter(action="warn_user", target_user=self.target).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.channel_id, self.channel_id)
        self.assertEqual(log.reason, "test")
        self.assertEqual(log.new_state, "warned")

    @patch("apps.chat.moderation.get_stream_client")
    def test_global_ban_creates_moderation_log(self, mock_client_fn):
        from apps.chat.models import ModerationLog
        mock_client, _ = _make_mock_stream_client()
        mock_client_fn.return_value = mock_client
        url = reverse("chat-global-ban", kwargs={"user_id": self.target.id})
        self._post(url, self.superuser, {"reason": "abuse"})
        log = ModerationLog.objects.filter(action="global_ban", target_user=self.target).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.moderator_role, "superuser")
        self.assertEqual(log.new_state, "global_banned")
