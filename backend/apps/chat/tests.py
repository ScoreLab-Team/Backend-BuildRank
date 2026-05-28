from unittest.mock import MagicMock, patch, call

import jwt, sys
from django.test import override_settings, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.db.models.signals import post_save
from apps.chat import signals as chat_signals
from apps.chat.models import ModerationLog
from apps.accounts.models import Profile, RoleChoices, User
from apps.buildings.models import Edifici, GrupComparable, Habitatge, Localitzacio

if 'test' in sys.argv:
    STREAM_API_KEY = ""
    STREAM_API_SECRET = ""

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


def _create_building(owner=None, grup=None, actiu=True):
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
        actiu=True,
    )


def _set_role(user, role):
    """El signal de accounts ja crea el Profile; aquí només actualitzem el rol."""
    user.profile.role = role
    user.profile.save()


def _create_grup(idGrup=1):
    return GrupComparable.objects.create(
        idGrup=idGrup,
        zonaClimatica="C2",
        tipologia="Residencial",
        rangSuperficie="200-500",
    )


# ---------------------------------------------------------------------------
# models.py — ModerationLog.__str__
# ---------------------------------------------------------------------------
 
class ModerationLogStrTest(TestCase):
    def test_str_contains_action_and_channel(self):
        moderator = User.objects.create_user(email="mod@test.com", password="pw")
        log = ModerationLog.objects.create(
            moderator=moderator,
            moderator_role="admin",
            action="hide_message",
            channel_id="building_1",
        )
        result = str(log)
        self.assertIn("hide_message", result)
        self.assertIn("building_1", result)
        self.assertIn("admin", result)


# ---------------------------------------------------------------------------
# services.py — sync_user_to_stream: camins d'error
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
class SyncUserToStreamTests(TestCase):
    def setUp(self):
        post_save.disconnect(chat_signals.sync_profile_to_stream, sender=Profile)
        self.addCleanup(post_save.connect, chat_signals.sync_profile_to_stream, sender=Profile)
        self.user = User.objects.create_user(
            email="sync@test.com", password="pw",
            first_name="Joan", last_name="Pla",
        )
 
    @patch("apps.chat.services.StreamChat")
    def test_sync_superuser_sets_stream_admin_role(self, mock_sc):
        from apps.chat.services import get_stream_client, sync_user_to_stream
        su = User.objects.create_superuser(email="su@test.com", password="pw")
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        client = get_stream_client()
        sync_user_to_stream(client, su)
        call_args = mock_client.upsert_user.call_args[0][0]
        self.assertEqual(call_args["role"], "admin")
 
    @patch("apps.chat.services.StreamChat")
    def test_sync_tenant_does_not_set_stream_admin_role(self, mock_sc):
        from apps.chat.services import get_stream_client, sync_user_to_stream
        _set_role(self.user, RoleChoices.TENANT)
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        client = get_stream_client()
        sync_user_to_stream(client, self.user)
        call_args = mock_client.upsert_user.call_args[0][0]
        self.assertNotIn("role", call_args)
 
    @patch("apps.chat.services.logger")
    @patch("apps.chat.services.StreamChat")
    def test_sync_reactivates_deleted_user(self, mock_sc, mock_logger):
        from apps.chat.services import get_stream_client, sync_user_to_stream
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        mock_client.upsert_user.side_effect = [
            Exception("User was deleted"),
            None,
        ]
        client = get_stream_client()
        sync_user_to_stream(client, self.user)
        mock_client.reactivate_user.assert_called_once()
        self.assertEqual(mock_client.upsert_user.call_count, 2)
 
    @patch("apps.chat.services.logger")
    @patch("apps.chat.services.StreamChat")
    def test_sync_logs_warning_on_hard_deleted_user(self, mock_sc, mock_logger):
        from apps.chat.services import get_stream_client, sync_user_to_stream
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        mock_client.upsert_user.side_effect = Exception("User was deleted")
        mock_client.reactivate_user.side_effect = Exception("Cannot reactivate hard-deleted")
        client = get_stream_client()
        sync_user_to_stream(client, self.user)  # no ha de llançar excepció
        mock_logger.warning.assert_called()
 
    @patch("apps.chat.services.StreamChat")
    def test_sync_raises_non_deleted_exception(self, mock_sc):
        from apps.chat.services import get_stream_client, sync_user_to_stream
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        mock_client.upsert_user.side_effect = Exception("network error")
        client = get_stream_client()
        with self.assertRaises(Exception):
            sync_user_to_stream(client, self.user)
 
 
# ---------------------------------------------------------------------------
# services.py — get_accessible_buildings
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class GetAccessibleBuildingsTests(TestCase):
    def setUp(self):
        self.grup = _create_grup(idGrup=50)
        self.owner = User.objects.create_user(email="owner_acc@test.com", password="pw")
        _set_role(self.owner, RoleChoices.OWNER)
        self.tenant = User.objects.create_user(email="tenant_acc@test.com", password="pw")
        _set_role(self.tenant, RoleChoices.TENANT)
        self.admin = User.objects.create_user(email="admin_acc@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.edifici = _create_building(owner=self.owner, grup=self.grup)
        Habitatge.objects.create(
            referenciaCadastral="ACC001", planta="1", porta="1A",
            superficie=80.0, edifici=self.edifici, usuari=self.tenant,
        )
 
    def test_unauthenticated_user_gets_no_buildings(self):
        from apps.chat.services import get_accessible_buildings
        anon = MagicMock()
        anon.is_authenticated = False
        result = get_accessible_buildings(anon)
        self.assertEqual(result.count(), 0)
 
    def test_superuser_sees_all_active_buildings(self):
        from apps.chat.services import get_accessible_buildings
        su = User.objects.create_superuser(email="su_acc@test.com", password="pw")
        result = get_accessible_buildings(su)
        self.assertIn(self.edifici, result)
 
    def test_owner_sees_only_managed_buildings(self):
        from apps.chat.services import get_accessible_buildings
        other_edifici = _create_building(grup=self.grup)
        result = get_accessible_buildings(self.owner)
        ids = list(result.values_list("idEdifici", flat=True))
        self.assertIn(self.edifici.idEdifici, ids)
        self.assertNotIn(other_edifici.idEdifici, ids)
 
    def test_tenant_sees_buildings_via_habitatge_usuari(self):
        from apps.chat.services import get_accessible_buildings
        result = get_accessible_buildings(self.tenant)
        self.assertIn(self.edifici, result)
 
    def test_tenant_sees_buildings_via_habitatge_propietari(self):
        from apps.chat.services import get_accessible_buildings
        propietari = User.objects.create_user(email="prop@test.com", password="pw")
        _set_role(propietari, RoleChoices.TENANT)
        Habitatge.objects.create(
            referenciaCadastral="ACC002", planta="2", porta="2A",
            superficie=90.0, edifici=self.edifici, propietari=propietari,
        )
        result = get_accessible_buildings(propietari)
        self.assertIn(self.edifici, result)
 
    def test_tenant_sees_buildings_via_habitatge_llogater(self):
        from apps.chat.services import get_accessible_buildings
        llogater = User.objects.create_user(email="llog@test.com", password="pw")
        _set_role(llogater, RoleChoices.TENANT)
        Habitatge.objects.create(
            referenciaCadastral="ACC003", planta="3", porta="3A",
            superficie=70.0, edifici=self.edifici, llogater=llogater,
        )
        result = get_accessible_buildings(llogater)
        self.assertIn(self.edifici, result)
 
    def test_admin_sees_all_active_buildings(self):
        from apps.chat.services import get_accessible_buildings
        result = get_accessible_buildings(self.admin)
        self.assertIn(self.edifici, result)
 
 
# ---------------------------------------------------------------------------
# services.py — _format_building_address, _format_user_name
# ---------------------------------------------------------------------------
 
class FormatHelpersTests(TestCase):
    def test_format_address_with_location(self):
        from apps.chat.services import _format_building_address
        loc = MagicMock()
        loc.carrer = "Gran Via"
        loc.numero = 42
        edifici = MagicMock()
        edifici.localitzacio = loc
        edifici.idEdifici = 1
        result = _format_building_address(edifici)
        self.assertIn("Gran Via", result)
        self.assertIn("42", result)
 
    def test_format_address_without_location(self):
        from apps.chat.services import _format_building_address
        edifici = MagicMock()
        edifici.localitzacio = None
        edifici.idEdifici = 7
        result = _format_building_address(edifici)
        self.assertIn("7", result)
 
    def test_format_address_with_location_but_no_carrer(self):
        from apps.chat.services import _format_building_address
        loc = MagicMock()
        loc.carrer = ""
        loc.numero = None
        edifici = MagicMock()
        edifici.localitzacio = loc
        edifici.idEdifici = 9
        result = _format_building_address(edifici)
        self.assertIn("9", result)
 
    def test_format_user_name_with_full_name(self):
        from apps.chat.services import _format_user_name
        user = MagicMock()
        user.first_name = "Maria"
        user.last_name = "Vila"
        user.email = "maria@test.com"
        self.assertEqual(_format_user_name(user), "Maria Vila")
 
    def test_format_user_name_falls_back_to_email(self):
        from apps.chat.services import _format_user_name
        user = MagicMock()
        user.first_name = ""
        user.last_name = ""
        user.email = "noemail@test.com"
        self.assertEqual(_format_user_name(user), "noemail@test.com")
 
 
# ---------------------------------------------------------------------------
# services.py — _is_admin_finca_of_building, _is_valid_target_admin
# ---------------------------------------------------------------------------
 
class AdminFincaHelpersTests(TestCase):
    def setUp(self):
        self.grup = _create_grup(idGrup=51)
        self.admin = User.objects.create_user(email="af_admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.tenant = User.objects.create_user(email="af_tenant@test.com", password="pw")
        _set_role(self.tenant, RoleChoices.TENANT)
        self.edifici = _create_building(owner=self.admin, grup=self.grup)
 
    def test_unauthenticated_user_is_not_admin_finca(self):
        from apps.chat.services import _is_admin_finca_of_building
        anon = MagicMock()
        anon.is_authenticated = False
        self.assertFalse(_is_admin_finca_of_building(anon, self.edifici))
 
    def test_superuser_is_always_admin_finca(self):
        from apps.chat.services import _is_admin_finca_of_building
        su = User.objects.create_superuser(email="af_su@test.com", password="pw")
        self.assertTrue(_is_admin_finca_of_building(su, self.edifici))
 
    def test_admin_matching_edifici_is_admin_finca(self):
        from apps.chat.services import _is_admin_finca_of_building
        self.assertTrue(_is_admin_finca_of_building(self.admin, self.edifici))
 
    def test_tenant_is_not_admin_finca(self):
        from apps.chat.services import _is_admin_finca_of_building
        self.assertFalse(_is_admin_finca_of_building(self.tenant, self.edifici))
 
    def test_is_valid_target_admin_none_returns_false(self):
        from apps.chat.services import _is_valid_target_admin
        self.assertFalse(_is_valid_target_admin(None))
 
    def test_is_valid_target_admin_superuser_returns_true(self):
        from apps.chat.services import _is_valid_target_admin
        su = User.objects.create_superuser(email="vta_su@test.com", password="pw")
        self.assertTrue(_is_valid_target_admin(su))
 
    def test_is_valid_target_admin_admin_role_returns_true(self):
        from apps.chat.services import _is_valid_target_admin
        admin = User.objects.create_user(email="vta_admin@test.com", password="pw")
        _set_role(admin, RoleChoices.ADMIN)
        self.assertTrue(_is_valid_target_admin(admin))
 
    def test_is_valid_target_admin_tenant_returns_false(self):
        from apps.chat.services import _is_valid_target_admin
        self.assertFalse(_is_valid_target_admin(self.tenant))
 
 
# ---------------------------------------------------------------------------
# services.py — get_twin_building_admin_candidates: errors i edge cases
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class TwinAdminCandidatesServiceTests(TestCase):
    def setUp(self):
        self.grup = _create_grup(idGrup=52)
        self.admin = User.objects.create_user(email="cand_admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.edifici = _create_building(owner=self.admin, grup=self.grup)
 
    def test_raises_value_error_for_nonexistent_edifici(self):
        from apps.chat.services import get_twin_building_admin_candidates
        with self.assertRaises(ValueError):
            get_twin_building_admin_candidates(self.admin, 999999)
 
    def test_raises_permission_error_if_not_admin_finca(self):
        from apps.chat.services import get_twin_building_admin_candidates
        other = User.objects.create_user(email="cand_other@test.com", password="pw")
        _set_role(other, RoleChoices.ADMIN)
        with self.assertRaises(PermissionError):
            get_twin_building_admin_candidates(other, self.edifici.idEdifici)
 
    def test_returns_empty_list_when_no_grup_comparable(self):
        from apps.chat.services import get_twin_building_admin_candidates
        edifici_no_grup = _create_building(owner=self.admin, grup=None)
        result = get_twin_building_admin_candidates(self.admin, edifici_no_grup.idEdifici)
        self.assertEqual(result, [])
 
    def test_excludes_own_building_and_same_admin(self):
        from apps.chat.services import get_twin_building_admin_candidates
        # Edifici del mateix grup però gestionat pel mateix admin
        _create_building(owner=self.admin, grup=self.grup)
        result = get_twin_building_admin_candidates(self.admin, self.edifici.idEdifici)
        for item in result:
            self.assertNotEqual(item["edifici_id"], self.edifici.idEdifici)
            self.assertNotEqual(item["admin"]["id"], self.admin.id)
 
    def test_returns_candidates_with_valid_admin(self):
        from apps.chat.services import get_twin_building_admin_candidates
        other_admin = User.objects.create_user(email="cand_other2@test.com", password="pw")
        _set_role(other_admin, RoleChoices.ADMIN)
        _create_building(owner=other_admin, grup=self.grup)
        result = get_twin_building_admin_candidates(self.admin, self.edifici.idEdifici)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["admin"]["email"], other_admin.email)
 
 
# ---------------------------------------------------------------------------
# services.py — get_or_create_twin_building_admin_channel: errors
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
class TwinBuildingAdminChannelServiceTests(TestCase):
    def setUp(self):
        post_save.disconnect(chat_signals.sync_profile_to_stream, sender=Profile)
        post_save.disconnect(chat_signals.add_tenant_to_building_channel, sender=Habitatge)
        self.addCleanup(post_save.connect, chat_signals.sync_profile_to_stream, sender=Profile)
        self.addCleanup(post_save.connect, chat_signals.add_tenant_to_building_channel, sender=Habitatge)
 
        self.grup = _create_grup(idGrup=53)
        self.altre_grup = _create_grup(idGrup=54)
        self.admin1 = User.objects.create_user(email="ch_admin1@test.com", password="pw")
        _set_role(self.admin1, RoleChoices.ADMIN)
        self.admin2 = User.objects.create_user(email="ch_admin2@test.com", password="pw")
        _set_role(self.admin2, RoleChoices.ADMIN)
        self.edifici1 = _create_building(owner=self.admin1, grup=self.grup)
        self.edifici2 = _create_building(owner=self.admin2, grup=self.grup)
        self.edifici_altre = _create_building(owner=self.admin2, grup=self.altre_grup)
 
    def test_raises_if_source_edifici_not_found(self):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        with self.assertRaises(ValueError, msg="No s'ha trobat l'edifici origen"):
            get_or_create_twin_building_admin_channel(self.admin1, 999999, self.edifici2.idEdifici)
 
    def test_raises_if_target_edifici_not_found(self):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        with self.assertRaises(ValueError, msg="No s'ha trobat l'edifici destí"):
            get_or_create_twin_building_admin_channel(self.admin1, self.edifici1.idEdifici, 999999)
 
    def test_raises_permission_error_if_not_admin_finca(self):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        other = User.objects.create_user(email="ch_other@test.com", password="pw")
        _set_role(other, RoleChoices.ADMIN)
        with self.assertRaises(PermissionError):
            get_or_create_twin_building_admin_channel(other, self.edifici1.idEdifici, self.edifici2.idEdifici)
 
    def test_raises_if_source_has_no_grup(self):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        edifici_no_grup = _create_building(owner=self.admin1, grup=None)
        with self.assertRaises(ValueError, msg="no té cap grup comparable"):
            get_or_create_twin_building_admin_channel(
                self.admin1, edifici_no_grup.idEdifici, self.edifici2.idEdifici
            )
 
    def test_raises_if_same_edifici(self):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        with self.assertRaises(ValueError, msg="mateix edifici"):
            get_or_create_twin_building_admin_channel(
                self.admin1, self.edifici1.idEdifici, self.edifici1.idEdifici
            )
 
    def test_raises_if_different_grup(self):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        with self.assertRaises(ValueError, msg="mateix grup comparable"):
            get_or_create_twin_building_admin_channel(
                self.admin1, self.edifici1.idEdifici, self.edifici_altre.idEdifici
            )
 
    def test_raises_if_target_admin_same_user(self):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        same_admin_edifici = _create_building(owner=self.admin1, grup=self.grup)
        with self.assertRaises(ValueError, msg="mateix usuari"):
            get_or_create_twin_building_admin_channel(
                self.admin1, self.edifici1.idEdifici, same_admin_edifici.idEdifici
            )
 
    @patch("apps.chat.services.get_stream_client")
    def test_channel_id_is_symmetric(self, mock_get_client):
        from apps.chat.services import get_or_create_twin_building_admin_channel
        mock_client, mock_channel = _make_mock_stream_client()
        mock_get_client.return_value = mock_client
 
        result = get_or_create_twin_building_admin_channel(
            self.admin1, self.edifici1.idEdifici, self.edifici2.idEdifici
        )
        low = min(self.edifici1.idEdifici, self.edifici2.idEdifici)
        high = max(self.edifici1.idEdifici, self.edifici2.idEdifici)
        self.assertEqual(result["id"], f"twin_building_{low}_{high}_admins")
        self.assertEqual(result["kind"], "twin_building_direct")
 
 
# ---------------------------------------------------------------------------
# moderation.py — _moderator_role_label
# ---------------------------------------------------------------------------
 
class ModeratorRoleLabelTests(TestCase):
    def test_superuser_returns_superuser_label(self):
        from apps.chat.moderation import _moderator_role_label
        su = User.objects.create_superuser(email="rl_su@test.com", password="pw")
        self.assertEqual(_moderator_role_label(su), "superuser")
 
    def test_admin_returns_admin_label(self):
        from apps.chat.moderation import _moderator_role_label
        admin = User.objects.create_user(email="rl_admin@test.com", password="pw")
        _set_role(admin, RoleChoices.ADMIN)
        self.assertEqual(_moderator_role_label(admin), RoleChoices.ADMIN)
 
    def test_user_without_profile_returns_empty_string(self):
        from apps.chat.moderation import _moderator_role_label
        user = MagicMock()
        user.is_superuser = False
        # del user.profile  # sense atribut profile
        # Ha de retornar "" sense excepció
        user.profile = None
        result = _moderator_role_label(user)
        self.assertIsInstance(result, str)
 
 
# ---------------------------------------------------------------------------
# moderation.py — _is_building_moderator: canal twin_group
# ---------------------------------------------------------------------------
 
class IsBuildingModeratorTwinGroupTests(TestCase):
    def setUp(self):
        self.grup = _create_grup(idGrup=55)
        self.admin = User.objects.create_user(email="tg_admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.admin.profile.save()
        self.edifici = _create_building(owner=self.admin, grup=self.grup)
 
    def test_admin_can_moderate_own_twin_group_channel(self):
        from apps.chat.moderation import _is_building_moderator
        channel_id = f"twin_group_{self.grup.id}"
        self.assertTrue(_is_building_moderator(self.admin, channel_id))
 
    def test_admin_cannot_moderate_twin_group_without_building(self):
        from apps.chat.moderation import _is_building_moderator
        other_grup = _create_grup(idGrup=56)
        channel_id = f"twin_group_{other_grup.id}"
        self.assertFalse(_is_building_moderator(self.admin, channel_id))
 
    def test_invalid_twin_group_id_returns_false(self):
        from apps.chat.moderation import _is_building_moderator
        self.assertFalse(_is_building_moderator(self.admin, "twin_group_abc"))
 
    def test_invalid_building_id_returns_false(self):
        from apps.chat.moderation import _is_building_moderator
        self.assertFalse(_is_building_moderator(self.admin, "building_abc"))
 
 
# ---------------------------------------------------------------------------
# moderation.py — ModerationLog es crea per a totes les accions
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
class ModerationLogCreationTests(TestCase):
    def setUp(self):
        self.grup = _create_grup(idGrup=57)
        self.superuser = User.objects.create_superuser(email="mlsu@test.com", password="pw")
        self.admin = User.objects.create_user(email="mladmin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.target = User.objects.create_user(email="mltarget@test.com", password="pw")
        self.edifici = _create_building(owner=self.admin, grup=self.grup)
        self.channel_id = f"building_{self.edifici.idEdifici}"
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_hide_message_creates_log(self, mock_fn):
        from apps.chat.moderation import hide_message
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        hide_message(self.admin, "msg-h1", self.channel_id, reason="spam")
        log = ModerationLog.objects.filter(action="hide_message").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "hidden")
        self.assertEqual(log.previous_state, "visible")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_delete_message_creates_log(self, mock_fn):
        from apps.chat.moderation import delete_message
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        delete_message(self.admin, "msg-d1", self.channel_id)
        log = ModerationLog.objects.filter(action="delete_message").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "deleted")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_restore_message_creates_log(self, mock_fn):
        from apps.chat.moderation import restore_message
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        restore_message(self.admin, "msg-r1", self.channel_id)
        log = ModerationLog.objects.filter(action="restore_message").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "visible")
        self.assertEqual(log.previous_state, "hidden")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_dismiss_flag_creates_log(self, mock_fn):
        from apps.chat.moderation import dismiss_flag
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        dismiss_flag(self.admin, "msg-df1", self.channel_id)
        log = ModerationLog.objects.filter(action="dismiss_flag").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "visible")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_mute_user_creates_log(self, mock_fn):
        from apps.chat.moderation import mute_user
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        mute_user(self.admin, self.target, self.channel_id, timeout=30, reason="flood")
        log = ModerationLog.objects.filter(action="mute_user").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "muted")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_unmute_user_creates_log(self, mock_fn):
        from apps.chat.moderation import unmute_user
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        unmute_user(self.admin, self.target, self.channel_id)
        log = ModerationLog.objects.filter(action="unmute_user").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "active")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_ban_from_channel_creates_log(self, mock_fn):
        from apps.chat.moderation import ban_from_channel
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        ban_from_channel(self.admin, self.target, self.channel_id, timeout=60)
        log = ModerationLog.objects.filter(action="ban_from_channel").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "channel_banned")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_unban_from_channel_creates_log(self, mock_fn):
        from apps.chat.moderation import unban_from_channel
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        unban_from_channel(self.admin, self.target, self.channel_id)
        log = ModerationLog.objects.filter(action="unban_from_channel").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "active")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_global_unban_creates_log(self, mock_fn):
        from apps.chat.moderation import global_unban
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        global_unban(self.superuser, self.target)
        log = ModerationLog.objects.filter(action="global_unban").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "active")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_shadow_ban_creates_log(self, mock_fn):
        from apps.chat.moderation import shadow_ban
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        shadow_ban(self.superuser, self.target, reason="bot")
        log = ModerationLog.objects.filter(action="shadow_ban").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "shadow_banned")
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_shadow_unban_creates_log(self, mock_fn):
        from apps.chat.moderation import shadow_unban
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        shadow_unban(self.superuser, self.target)
        log = ModerationLog.objects.filter(action="shadow_unban").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_state, "active")


# ---------------------------------------------------------------------------
# signals.py
# ---------------------------------------------------------------------------
 
class SignalsTests(TestCase):
    def test_sync_profile_skipped_when_not_configured(self):
        """Si no hi ha credencials, el signal no ha d'intentar connectar."""
        with override_settings(STREAM_API_KEY="", STREAM_API_SECRET=""):
            with patch("apps.chat.services.StreamChat") as mock_sc:
                user = User.objects.create_user(email="sig1@test.com", password="pw")
                user.profile.save()
                mock_sc.assert_not_called()
 
    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.services.StreamChat")
    def test_sync_profile_called_when_configured(self, mock_sc):
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        mock_client.upsert_user.return_value = {}
        user = User.objects.create_user(email="sig2@test.com", password="pw")
        user.profile.save()
        mock_client.upsert_user.assert_called()
 
    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.signals.logger")
    @patch("apps.chat.services.StreamChat")
    def test_sync_profile_logs_warning_on_error(self, mock_sc, mock_logger):
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        mock_client.upsert_user.side_effect = Exception("stream error")
        user = User.objects.create_user(email="sig3@test.com", password="pw")
        user.profile.save()  # no ha de llançar excepció
        mock_logger.warning.assert_called()
 
    def test_add_tenant_skipped_when_no_usuari(self):
        """Si l'habitatge no té usuari, el signal no fa res."""
        with override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s"):
            with patch("apps.chat.services.StreamChat") as mock_sc:
                grup = _create_grup(idGrup=60)
                admin = User.objects.create_user(email="sig4@test.com", password="pw")
                _set_role(admin, RoleChoices.ADMIN)
                edifici = _create_building(owner=admin, grup=grup)
                # Habitatge sense usuari — el signal no ha de cridar StreamChat
                before = mock_sc.call_count
                Habitatge.objects.create(
                    referenciaCadastral="SIG001", planta="1", porta="1A",
                    superficie=60.0, edifici=edifici,
                )
                # mock_sc no hauria d'haver-se cridat addicional
                self.assertEqual(mock_sc.call_count, before)
 
    @override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
    @patch("apps.chat.signals.logger")
    @patch("apps.chat.services.StreamChat")
    def test_add_tenant_logs_warning_on_error(self, mock_sc, mock_logger):
        mock_client = MagicMock()
        mock_sc.return_value = mock_client
        mock_client.upsert_user.side_effect = Exception("fail")
        grup = _create_grup(idGrup=61)
        admin = User.objects.create_user(email="sig5@test.com", password="pw")
        _set_role(admin, RoleChoices.ADMIN)
        edifici = _create_building(owner=admin, grup=grup)
        tenant = User.objects.create_user(email="sig5t@test.com", password="pw")
        Habitatge.objects.create(
            referenciaCadastral="SIG002", planta="2", porta="2B",
            superficie=75.0, edifici=edifici, usuari=tenant,
        )
        mock_logger.warning.assert_called()


# ---------------------------------------------------------------------------
# views.py — endpoints no coberts: restore, dismiss-flag, unmute,
#             ban/unban, global-unban, shadow-unban, errors 503/404
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
class ModerationViewsMissingTests(APITestCase):
    def setUp(self):
        post_save.disconnect(chat_signals.sync_profile_to_stream, sender=Profile)
        post_save.disconnect(chat_signals.add_tenant_to_building_channel, sender=Habitatge)
        self.addCleanup(post_save.connect, chat_signals.sync_profile_to_stream, sender=Profile)
        self.addCleanup(post_save.connect, chat_signals.add_tenant_to_building_channel, sender=Habitatge)
 
        self.grup = _create_grup(idGrup=70)
        self.admin = User.objects.create_user(email="mv_admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.tenant = User.objects.create_user(email="mv_tenant@test.com", password="pw")
        _set_role(self.tenant, RoleChoices.TENANT)
        self.superuser = User.objects.create_superuser(email="mv_su@test.com", password="pw")
        self.target = User.objects.create_user(email="mv_target@test.com", password="pw")
        self.edifici = _create_building(owner=self.admin, grup=self.grup)
        self.channel_id = f"building_{self.edifici.idEdifici}"
 
    def _post(self, url, user, data=None):
        self.client.force_authenticate(user=user)
        return self.client.post(url, data or {}, format="json")
 
    # --- restore_message ---
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_restore_message(self, mock_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        url = reverse("chat-restore-message", kwargs={"message_id": "msg-r1"})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)
 
    def test_tenant_cannot_restore_message(self):
        url = reverse("chat-restore-message", kwargs={"message_id": "msg-r2"})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)
 
    # @patch("apps.chat.views.logger")
    # @patch("apps.chat.moderation.get_stream_client")
    @patch('apps.chat.views.restore_message')
    def test_restore_message_503_on_stream_error(self, mock_restore):
        mock_restore.side_effect = Exception("Stream error")
        mock_client, mock_channel = _make_mock_stream_client()
        mock_channel.update_message.side_effect = Exception("stream down")
        mock_restore.return_value = mock_client
        url = reverse("chat-restore-message", kwargs={"message_id": "msg-r3"})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 503)
 
    # --- dismiss_flag ---
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_dismiss_flag(self, mock_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        url = reverse("chat-dismiss-flag", kwargs={"message_id": "msg-df1"})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)
 
    def test_tenant_cannot_dismiss_flag(self):
        url = reverse("chat-dismiss-flag", kwargs={"message_id": "msg-df2"})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)
 
    # --- unmute ---
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_unmute_user(self, mock_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        url = reverse("chat-unmute-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)
 
    def test_tenant_cannot_unmute_user(self):
        url = reverse("chat-unmute-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)
 
    @patch("apps.chat.views.logger")
    @patch("apps.chat.moderation.get_stream_client")
    def test_unmute_503_on_stream_error(self, mock_fn, _):
        mock_client, _ = _make_mock_stream_client()
        mock_client.unmute_user.side_effect = Exception("fail")
        mock_fn.return_value = mock_client
        url = reverse("chat-unmute-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 503)
 
    # --- ban_from_channel ---
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_ban_from_channel(self, mock_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        url = reverse("chat-ban-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)
 
    def test_ban_from_channel_returns_404_for_unknown_user(self):
        url = reverse("chat-ban-user", kwargs={"user_id": 999999})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 404)
 
    def test_tenant_cannot_ban_from_channel(self):
        url = reverse("chat-ban-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)
 
    @patch("apps.chat.views.logger")
    @patch("apps.chat.moderation.get_stream_client")
    def test_ban_503_on_stream_error(self, mock_fn, _):
        mock_client, mock_channel = _make_mock_stream_client()
        mock_channel.ban_user.side_effect = Exception("fail")
        mock_fn.return_value = mock_client
        url = reverse("chat-ban-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id, "timeout": 60})
        self.assertEqual(resp.status_code, 503)
 
    # --- unban_from_channel ---
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_admin_can_unban_from_channel(self, mock_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        url = reverse("chat-unban-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 200)
 
    def test_tenant_cannot_unban_from_channel(self):
        url = reverse("chat-unban-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 403)
 
    # --- global_unban ---
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_superuser_can_global_unban(self, mock_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        url = reverse("chat-global-unban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.superuser, {"reason": "rehabilitat"})
        self.assertEqual(resp.status_code, 200)
 
    def test_admin_cannot_global_unban(self):
        url = reverse("chat-global-unban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {})
        self.assertEqual(resp.status_code, 403)
 
    def test_global_unban_returns_404_for_unknown_user(self):
        url = reverse("chat-global-unban", kwargs={"user_id": 999999})
        resp = self._post(url, self.superuser, {})
        self.assertEqual(resp.status_code, 404)
 
    @patch("apps.chat.views.logger")
    @patch("apps.chat.moderation.get_stream_client")
    def test_global_unban_503_on_stream_error(self, mock_fn, _):
        mock_client, _ = _make_mock_stream_client()
        mock_client.unban_user.side_effect = Exception("fail")
        mock_fn.return_value = mock_client
        url = reverse("chat-global-unban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.superuser, {})
        self.assertEqual(resp.status_code, 503)
 
    # --- shadow_unban ---
 
    @patch("apps.chat.moderation.get_stream_client")
    def test_superuser_can_shadow_unban(self, mock_fn):
        mock_client, _ = _make_mock_stream_client()
        mock_fn.return_value = mock_client
        url = reverse("chat-shadow-unban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.superuser, {})
        self.assertEqual(resp.status_code, 200)
 
    def test_admin_cannot_shadow_unban(self):
        url = reverse("chat-shadow-unban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {})
        self.assertEqual(resp.status_code, 403)
 
    @patch("apps.chat.views.logger")
    @patch("apps.chat.moderation.get_stream_client")
    def test_shadow_unban_503_on_stream_error(self, mock_fn, _):
        mock_client, _ = _make_mock_stream_client()
        mock_client.unban_user.side_effect = Exception("fail")
        mock_fn.return_value = mock_client
        url = reverse("chat-shadow-unban", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.superuser, {})
        self.assertEqual(resp.status_code, 503)
 
    # --- warn_user: 404 i 503 ---
 
    def test_warn_returns_404_for_unknown_user(self):
        url = reverse("chat-warn-user", kwargs={"user_id": 999999})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 404)
 
    @patch("apps.chat.views.logger")
    @patch("apps.chat.moderation.get_stream_client")
    def test_warn_503_on_stream_error(self, mock_fn, _):
        mock_client, _ = _make_mock_stream_client()
        mock_client.upsert_user.side_effect = Exception("fail")
        mock_fn.return_value = mock_client
        url = reverse("chat-warn-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 503)
 
    # --- flag_message: 503 ---
 
    # @patch("apps.chat.views.logger")
    # @patch("apps.chat.moderation.get_stream_client")
    @patch('apps.chat.views.flag_message')
    def test_flag_message_503_on_stream_error(self, mock_flag):
        mock_flag.side_effect = Exception("Stream error")
        mock_client, _ = _make_mock_stream_client()
        mock_client.flag.side_effect = Exception("fail")
        mock_flag.return_value = mock_client
        url = reverse("chat-flag-message", kwargs={"message_id": "msg-fail"})
        resp = self._post(url, self.tenant, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 503)
 
    # --- hide_message: 503 ---
 
    # @patch("apps.chat.views.logger")
    # @patch("apps.chat.moderation.get_stream_client")
    @patch('apps.chat.views.hide_message')
    def test_hide_message_503_on_stream_error(self, mock_hide):
        mock_hide.side_effect = Exception("Stream error")
        mock_client, mock_channel = _make_mock_stream_client()
        mock_channel.update_message.side_effect = Exception("fail")
        mock_hide.return_value = mock_client
        url = reverse("chat-hide-message", kwargs={"message_id": "msg-fail2"})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 503)
 
    # --- delete_message: 503 ---
 
    # @patch("apps.chat.views.logger")
    # @patch("apps.chat.moderation.get_stream_client")
    @patch('apps.chat.views.delete_message')
    def test_delete_message_503_on_stream_error(self, mock_delete):
        mock_delete.side_effect = Exception("Stream error")
        mock_client, mock_channel = _make_mock_stream_client()
        mock_channel.delete_message.side_effect = Exception("fail")
        mock_delete.return_value = mock_client
        url = reverse("chat-delete-message", kwargs={"message_id": "msg-fail3"})
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(
            url, {"channel_id": self.channel_id, "is_own": True}, format="json"
        )
        self.assertEqual(resp.status_code, 503)
 
    # --- mute: 503 i 404 ---
 
    def test_mute_returns_404_for_unknown_user(self):
        url = reverse("chat-mute-user", kwargs={"user_id": 999999})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 404)
 
    @patch("apps.chat.views.logger")
    @patch("apps.chat.moderation.get_stream_client")
    def test_mute_503_on_stream_error(self, mock_fn, _):
        mock_client, _ = _make_mock_stream_client()
        mock_client.mute_user.side_effect = Exception("fail")
        mock_fn.return_value = mock_client
        url = reverse("chat-mute-user", kwargs={"user_id": self.target.id})
        resp = self._post(url, self.admin, {"channel_id": self.channel_id})
        self.assertEqual(resp.status_code, 503)
 
 
# ---------------------------------------------------------------------------
# views.py — TwinBuildingChannelView: camins d'error
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s")
class TwinBuildingChannelViewErrorTests(APITestCase):
    def setUp(self):
        post_save.disconnect(chat_signals.sync_profile_to_stream, sender=Profile)
        post_save.disconnect(chat_signals.add_tenant_to_building_channel, sender=Habitatge)
        self.addCleanup(post_save.connect, chat_signals.sync_profile_to_stream, sender=Profile)
        self.addCleanup(post_save.connect, chat_signals.add_tenant_to_building_channel, sender=Habitatge)
 
        self.grup = _create_grup(idGrup=80)
        self.admin = User.objects.create_user(email="tcv_admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
        self.edifici = _create_building(owner=self.admin, grup=self.grup)
 
    def test_non_integer_target_edifici_id_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            reverse("chat-twin-building-channel", kwargs={"edifici_id": self.edifici.idEdifici}),
            {"target_edifici_id": "abc"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("enter", resp.data["detail"])
 
    def test_permission_error_returns_403(self):
        other = User.objects.create_user(email="tcv_other@test.com", password="pw")
        _set_role(other, RoleChoices.ADMIN)
        self.client.force_authenticate(user=other)
        resp = self.client.post(
            reverse("chat-twin-building-channel", kwargs={"edifici_id": self.edifici.idEdifici}),
            {"target_edifici_id": 999},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
 
    @patch("apps.chat.views.logger")
    @patch("apps.chat.services.get_stream_client")
    def test_unexpected_exception_returns_503(self, mock_fn, _):
        mock_fn.side_effect = Exception("unexpected")
        altre_admin = User.objects.create_user(email="tcv_admin2@test.com", password="pw")
        _set_role(altre_admin, RoleChoices.ADMIN)
        altre_edifici = _create_building(owner=altre_admin, grup=self.grup)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            reverse("chat-twin-building-channel", kwargs={"edifici_id": self.edifici.idEdifici}),
            {"target_edifici_id": altre_edifici.idEdifici},
            format="json",
        )
        self.assertEqual(resp.status_code, 503)
 
 
# ---------------------------------------------------------------------------
# views.py — TwinBuildingAdminsView: errors
# ---------------------------------------------------------------------------
 
@override_settings(STREAM_API_KEY="", STREAM_API_SECRET="")
class TwinBuildingAdminsViewErrorTests(APITestCase):
    def setUp(self):
        post_save.disconnect(chat_signals.sync_profile_to_stream, sender=Profile)
        self.addCleanup(post_save.connect, chat_signals.sync_profile_to_stream, sender=Profile)
        self.admin = User.objects.create_user(email="tav_admin@test.com", password="pw")
        _set_role(self.admin, RoleChoices.ADMIN)
 
    def test_nonexistent_edifici_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(
            reverse("chat-twin-building-admins", kwargs={"edifici_id": 999999})
        )
        self.assertEqual(resp.status_code, 400)
 
    @patch("apps.chat.views.logger")
    @patch(
        "apps.chat.views.get_twin_building_admin_candidates",
        side_effect=Exception("unexpected"),
    )
    def test_unexpected_exception_returns_500(self, _, __):
        grup = _create_grup(idGrup=81)
        edifici = _create_building(owner=self.admin, grup=grup)
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(
            reverse("chat-twin-building-admins", kwargs={"edifici_id": edifici.idEdifici})
        )
        self.assertEqual(resp.status_code, 500)


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
        self.grup = _create_grup()
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
        stream_patcher = patch("apps.chat.services.sync_user_to_stream")
        stream_patcher.start()
        self.addCleanup(stream_patcher.stop)

        self.grup = _create_grup()
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

# ---------------------------------------------------------------------------
# US40 — Twin Building direct chat entre administradors de finca
# ---------------------------------------------------------------------------

@override_settings(STREAM_API_KEY="k", STREAM_API_SECRET="s", STREAM_TOKEN_EXPIRATION_SECONDS=3600)
class TwinBuildingDirectChatTests(APITestCase):
    def setUp(self):
        # Evitem que els signals de xat facin crides reals a GetStream
        # mentre preparem dades de test. Aquests tests validen els endpoints
        # Twin Building, no la sincronització automàtica per signals.
        post_save.disconnect(chat_signals.sync_profile_to_stream, sender=Profile)
        post_save.disconnect(chat_signals.add_tenant_to_building_channel, sender=Habitatge)

        self.addCleanup(
            post_save.connect,
            chat_signals.sync_profile_to_stream,
            sender=Profile,
        )
        self.addCleanup(
            post_save.connect,
            chat_signals.add_tenant_to_building_channel,
            sender=Habitatge,
        )

        self.grup = GrupComparable.objects.create(
            idGrup=40,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="200-500",
        )
        self.altre_grup = GrupComparable.objects.create(
            idGrup=41,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="500-1000",
        )

        self.admin_origen = User.objects.create_user(
            email="admin.origen@example.com",
            password="Pass123!",
            first_name="Admin",
            last_name="Origen",
        )
        _set_role(self.admin_origen, RoleChoices.ADMIN)

        self.admin_desti = User.objects.create_user(
            email="admin.desti@example.com",
            password="Pass123!",
            first_name="Admin",
            last_name="Desti",
        )
        _set_role(self.admin_desti, RoleChoices.ADMIN)

        self.admin_altre_grup = User.objects.create_user(
            email="admin.altre@example.com",
            password="Pass123!",
        )
        _set_role(self.admin_altre_grup, RoleChoices.ADMIN)

        self.owner = User.objects.create_user(
            email="owner.twin@example.com",
            password="Pass123!",
        )
        _set_role(self.owner, RoleChoices.OWNER)

        self.edifici_origen = _create_building(owner=self.admin_origen, grup=self.grup)
        self.edifici_desti = _create_building(owner=self.admin_desti, grup=self.grup)
        self.edifici_altre_grup = _create_building(owner=self.admin_altre_grup, grup=self.altre_grup)

        Habitatge.objects.create(
            referenciaCadastral="TWIN001",
            planta="1",
            porta="1A",
            superficie=80.0,
            edifici=self.edifici_origen,
            usuari=self.owner,
        )

    def test_admin_can_list_twin_building_admins_same_group(self):
        self.client.force_authenticate(user=self.admin_origen)

        response = self.client.get(
            reverse(
                "chat-twin-building-admins",
                kwargs={"edifici_id": self.edifici_origen.idEdifici},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

        result = response.data["results"][0]
        self.assertEqual(result["edifici_id"], self.edifici_desti.idEdifici)
        self.assertEqual(result["admin"]["email"], self.admin_desti.email)

    def test_admin_list_does_not_include_own_building_or_other_group(self):
        self.client.force_authenticate(user=self.admin_origen)

        response = self.client.get(
            reverse(
                "chat-twin-building-admins",
                kwargs={"edifici_id": self.edifici_origen.idEdifici},
            )
        )

        ids = {item["edifici_id"] for item in response.data["results"]}

        self.assertNotIn(self.edifici_origen.idEdifici, ids)
        self.assertNotIn(self.edifici_altre_grup.idEdifici, ids)

    def test_owner_cannot_list_twin_building_admins(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(
            reverse(
                "chat-twin-building-admins",
                kwargs={"edifici_id": self.edifici_origen.idEdifici},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.chat.services.get_stream_client")
    def test_admin_can_create_direct_twin_building_channel(self, mock_get_client):
        mock_client, mock_channel = _make_mock_stream_client()
        mock_get_client.return_value = mock_client

        self.client.force_authenticate(user=self.admin_origen)

        response = self.client.post(
            reverse(
                "chat-twin-building-channel",
                kwargs={"edifici_id": self.edifici_origen.idEdifici},
            ),
            {"target_edifici_id": self.edifici_desti.idEdifici},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["kind"], "twin_building_direct")
        self.assertEqual(
            response.data["id"],
            f"twin_building_{self.edifici_origen.idEdifici}_{self.edifici_desti.idEdifici}_admins",
        )

        mock_client.channel.assert_called()
        mock_channel.create.assert_called()
        mock_channel.add_members.assert_called()

    def test_cannot_create_channel_with_building_from_other_group(self):
        self.client.force_authenticate(user=self.admin_origen)

        response = self.client.post(
            reverse(
                "chat-twin-building-channel",
                kwargs={"edifici_id": self.edifici_origen.idEdifici},
            ),
            {"target_edifici_id": self.edifici_altre_grup.idEdifici},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mateix grup comparable", response.data["detail"])

    def test_missing_target_edifici_id_returns_400(self):
        self.client.force_authenticate(user=self.admin_origen)

        response = self.client.post(
            reverse(
                "chat-twin-building-channel",
                kwargs={"edifici_id": self.edifici_origen.idEdifici},
            ),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("target_edifici_id", response.data["detail"])


# ---------------------------------------------------------------------------
# services.py — get_stream_user_id (chat_stream_id_version branch)
# ---------------------------------------------------------------------------

class GetStreamUserIdVersionTests(TestCase):
    """Cobreix la lògica de versionat de user_id introduïda perquè usuaris
    amb el seu user_id antic tombstoned a GetStream puguin reconnectar amb
    un identificador nou."""

    def setUp(self):
        from apps.chat.services import get_stream_user_id
        self._get = get_stream_user_id
        self.user = User.objects.create_user(
            email="versioned@test.com",
            password="StrongPass123!",
        )

    def test_default_version_returns_plain_user_id(self):
        # Version per defecte (1) → format "user_{id}" tradicional.
        self.assertEqual(self.user.chat_stream_id_version, 1)
        self.assertEqual(self._get(self.user), f"user_{self.user.id}")

    def test_bumped_version_returns_versioned_user_id(self):
        # En bumpar la versió, l'id passa a "user_{id}_v{N}".
        self.user.chat_stream_id_version = 2
        self.user.save(update_fields=["chat_stream_id_version"])
        self.assertEqual(self._get(self.user), f"user_{self.user.id}_v2")

        self.user.chat_stream_id_version = 5
        self.user.save(update_fields=["chat_stream_id_version"])
        self.assertEqual(self._get(self.user), f"user_{self.user.id}_v5")

    def test_zero_or_none_version_falls_back_to_default(self):
        # Defensiu: si algú força el camp a 0 (o None per objectes en memòria),
        # el helper ha de retornar el format per defecte sense petar.
        self.user.chat_stream_id_version = 0
        self.user.save(update_fields=["chat_stream_id_version"])
        self.assertEqual(self._get(self.user), f"user_{self.user.id}")


# ---------------------------------------------------------------------------
# management/commands/bump_stream_user_id
# ---------------------------------------------------------------------------

class BumpStreamUserIdCommandTests(TestCase):
    """Cobreix el command que bumpa chat_stream_id_version per a usuaris
    afectats per un hard-delete a GetStream."""

    def setUp(self):
        from io import StringIO
        self._StringIO = StringIO
        self.user_a = User.objects.create_user(
            email="bump_a@test.com",
            password="StrongPass123!",
        )
        self.user_b = User.objects.create_user(
            email="bump_b@test.com",
            password="StrongPass123!",
        )

    def _call(self, *args):
        from django.core.management import call_command
        out = self._StringIO()
        call_command("bump_stream_user_id", *args, stdout=out)
        return out.getvalue()

    def test_bump_by_ids_increments_versions(self):
        output = self._call("--ids", str(self.user_a.id), str(self.user_b.id))
        self.user_a.refresh_from_db()
        self.user_b.refresh_from_db()
        self.assertEqual(self.user_a.chat_stream_id_version, 2)
        self.assertEqual(self.user_b.chat_stream_id_version, 2)
        # El missatge final inclou el nou user_id format versionat.
        self.assertIn(f"user_{self.user_a.id}_v2", output)
        self.assertIn(f"user_{self.user_b.id}_v2", output)

    def test_bump_by_emails_increments_versions(self):
        self._call("--emails", self.user_a.email)
        self.user_a.refresh_from_db()
        self.user_b.refresh_from_db()
        self.assertEqual(self.user_a.chat_stream_id_version, 2)
        # L'altre usuari no s'ha tocat.
        self.assertEqual(self.user_b.chat_stream_id_version, 1)

    def test_bump_with_missing_id_warns_and_skips(self):
        missing_id = 999999
        output = self._call("--ids", str(self.user_a.id), str(missing_id))
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.chat_stream_id_version, 2)
        self.assertIn("no trobats", output)
        self.assertIn(str(missing_id), output)

    def test_bump_with_missing_email_warns_and_skips(self):
        output = self._call("--emails", self.user_a.email, "ghost@test.com")
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.chat_stream_id_version, 2)
        self.assertIn("no trobats", output)
        self.assertIn("ghost@test.com", output)

    def test_bump_with_no_matching_users_prints_nothing_to_process(self):
        output = self._call("--ids", "999998", "999999")
        self.user_a.refresh_from_db()
        self.user_b.refresh_from_db()
        # No s'ha tocat ningú.
        self.assertEqual(self.user_a.chat_stream_id_version, 1)
        self.assertEqual(self.user_b.chat_stream_id_version, 1)
        self.assertIn("Cap usuari per processar", output)

    def test_bump_twice_keeps_incrementing(self):
        self._call("--ids", str(self.user_a.id))
        self._call("--ids", str(self.user_a.id))
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.chat_stream_id_version, 3)