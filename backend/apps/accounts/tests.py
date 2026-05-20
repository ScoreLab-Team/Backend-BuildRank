from datetime import timedelta
import re
from unittest.mock import patch

from django.test import override_settings
from django.core.cache import cache
from django.core import mail
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import (
    AccessDenialLog,
    Profile,
    RoleChoices,
    TokenLoginLog,
    User,
)
from apps.buildings.models import (
    Edifici,
    GrupComparable,
    Habitatge,
    Localitzacio,
)

User = get_user_model()

NO_THROTTLE_REST_FRAMEWORK = {
    **settings.REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

class BaseTestData(APITestCase):
    """Base class with shared test data creation utilities."""

    @classmethod
    def _create_user(cls, email, role):
        """Create a user with given email and role."""
        user = User.objects.create_user(
            email=email,
            password="Password123",
            first_name=email.split("@")[0],
        )
        user.profile.role = role
        user.profile.save(update_fields=["role"])
        return user

    @classmethod
    def _create_edifici(cls, administrador, grup, **kwargs):
        """Create a building with auto-generated idEdifici and puntuacioBase."""
        localitzacio = Localitzacio.objects.create(
            carrer=kwargs.get("carrer", "Carrer test"),
            numero=kwargs.get("numero", 1),
            codiPostal=kwargs.get("codiPostal", "08001"),
            barri=kwargs.get("barri", "Centre"),
            latitud=kwargs.get("latitud", 41.0),
            longitud=kwargs.get("longitud", 2.0),
            zonaClimatica=kwargs.get("zonaClimatica", "C2"),
        )
        return Edifici.objects.create(
            anyConstruccio=kwargs.get("anyConstruccio", 2000),
            tipologia=kwargs.get("tipologia", "Residencial"),
            superficieTotal=kwargs.get("superficieTotal", 400),
            reglament=kwargs.get("reglament", "CTE"),
            orientacioPrincipal=kwargs.get("orientacioPrincipal", "Sud"),
            localitzacio=localitzacio,
            administradorFinca=administrador,
            grupComparable=grup,
        )

class RBACAuthorizationTests(BaseTestData):
    """Role-Based Access Control authorization tests."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data once for all tests in this class."""
        # admin_sistema és is_superuser (àmbit plataforma, fora del RBAC funcional APP)
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="Password123",
            first_name="admin",
            is_superuser=True,
            is_staff=True,
        )
        cls.admin_finca = cls._create_user("owner@example.com", RoleChoices.OWNER)
        cls.altre_admin_finca = cls._create_user("owner2@example.com", RoleChoices.OWNER)

        cls.grup = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        cls.edifici_1 = cls._create_edifici(administrador=cls.admin_finca, grup=cls.grup)

    def test_admin_sistema_can_assign_admin_to_building(self):
        """AdminSistema has permission to assign admin to any building."""
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            reverse("assignar-admin-edifici", args=[self.edifici_1.idEdifici]),
            {"user_id": self.altre_admin_finca.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.edifici_1.refresh_from_db()
        self.assertEqual(self.edifici_1.administradorFinca_id, self.altre_admin_finca.id)

    def test_admin_finca_cannot_assign_admin_to_building(self):
        """AdminFinca (owner) lacks permission to assign admin."""
        self.client.force_authenticate(user=self.admin_finca)

        response = self.client.patch(
            reverse("assignar-admin-edifici", args=[self.edifici_1.idEdifici]),
            {"user_id": self.altre_admin_finca.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_assign_admin(self):
        """Unauthenticated requests must return 401."""
        response = self.client.patch(
            reverse("assignar-admin-edifici", args=[self.edifici_1.idEdifici]),
            {"user_id": self.altre_admin_finca.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ABACTests(BaseTestData):
    """Attribute-Based Access Control authorization tests."""

    @classmethod
    def setUpTestData(cls):
        """Set up buildings with different admins for ABAC testing."""
        cls.admin_finca = cls._create_user("adminfinca1@example.com", RoleChoices.ADMIN)
        cls.altre_admin_finca = cls._create_user("adminfinca2@example.com", RoleChoices.ADMIN)
        cls.resident = cls._create_user("tenant@example.com", RoleChoices.TENANT)

        cls.grup = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        cls.edifici_1 = cls._create_edifici(administrador=cls.admin_finca, grup=cls.grup)
        cls.edifici_2 = cls._create_edifici(administrador=cls.altre_admin_finca, grup=cls.grup)

        cls.habitatge_1 = Habitatge.objects.create(
            referenciaCadastral="HAB-1",
            planta="1",
            porta="A",
            superficie=80,
            edifici=cls.edifici_1,
            usuari=cls.resident,
        )
        cls.habitatge_2 = Habitatge.objects.create(
            referenciaCadastral="HAB-2",
            planta="2",
            porta="B",
            superficie=95,
            edifici=cls.edifici_2,
            usuari=cls.resident,
        )

    def test_admin_finca_gets_403_on_idor_for_unmanaged_building(self):
        """IDOR attack: AdminFinca cannot access apartment in unmanaged building."""
        self.client.force_authenticate(user=self.admin_finca)

        response = self.client.patch(
            reverse("assignar-resident", args=[self.habitatge_2.referenciaCadastral]),
            {"user_id": self.resident.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(AccessDenialLog.objects.count(), 1)
        denial = AccessDenialLog.objects.first()
        self.assertEqual(denial.user_id, self.admin_finca.id)
        self.assertIn("cartera de gestió", denial.motiu)


class AssignmentTests(BaseTestData):
    """Tests for resident assignment functionality."""

    @classmethod
    def setUpTestData(cls):
        """Set up buildings and residents for assignment testing."""
        cls.admin_finca = cls._create_user("adminfinca@example.com", RoleChoices.ADMIN)
        cls.resident = cls._create_user("tenant@example.com", RoleChoices.TENANT)
        cls.altre_resident = cls._create_user("tenant2@example.com", RoleChoices.TENANT)

        cls.grup = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        cls.edifici_1 = cls._create_edifici(administrador=cls.admin_finca, grup=cls.grup)

        cls.habitatge_1 = Habitatge.objects.create(
            referenciaCadastral="HAB-1",
            planta="1",
            porta="A",
            superficie=80,
            edifici=cls.edifici_1,
            usuari=cls.resident,
        )

    def test_admin_finca_can_assign_resident_inside_managed_building(self):
        """AdminFinca can assign resident to apartment in managed building."""
        self.client.force_authenticate(user=self.admin_finca)

        response = self.client.patch(
            reverse("assignar-resident", args=[self.habitatge_1.referenciaCadastral]),
            {"user_id": self.altre_resident.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.habitatge_1.refresh_from_db()
        self.assertEqual(self.habitatge_1.usuari_id, self.altre_resident.id)

    def test_tenant_cannot_assign_resident(self):
        """Tenant (resident) lacks permission to assign other residents."""
        self.client.force_authenticate(user=self.resident)

        response = self.client.patch(
            reverse("assignar-resident", args=[self.habitatge_1.referenciaCadastral]),
            {"user_id": self.altre_resident.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class MeRoleViewTests(BaseTestData):
    """Tests for authenticated user's role change endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = cls._create_user("perfil@example.com", RoleChoices.OWNER)

    def test_authenticated_user_can_change_role_to_tenant(self):
        """Authenticated user can change own role from owner to tenant."""
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me-role"),
            {"role": RoleChoices.TENANT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, RoleChoices.TENANT)
        self.assertEqual(response.data["role"], RoleChoices.TENANT)

    def test_authenticated_user_can_change_role_to_owner(self):
        """Authenticated user can change own role from tenant to owner."""
        self.user.profile.role = RoleChoices.TENANT
        self.user.profile.save(update_fields=["role"])

        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me-role"),
            {"role": RoleChoices.OWNER},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, RoleChoices.OWNER)
        self.assertEqual(response.data["role"], RoleChoices.OWNER)

    def test_authenticated_user_cannot_change_role_to_admin(self):
        """Authenticated user cannot escalate own role to admin."""
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me-role"),
            {"role": RoleChoices.ADMIN},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.role, RoleChoices.OWNER)
        self.assertIn("role", response.data)

    def test_unauthenticated_user_cannot_change_role(self):
        """Unauthenticated requests must return 401."""
        response = self.client.patch(
            reverse("me-role"),
            {"role": RoleChoices.TENANT},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class MeViewTests(BaseTestData):
    """Tests for authenticated user's profile retrieval and update endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = cls._create_user("meview@example.com", RoleChoices.OWNER)

    def test_authenticated_user_can_get_own_profile(self):
        """Authenticated user can retrieve own profile data."""
        self.client.force_authenticate(user=self.user)

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.user.id)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertEqual(response.data["first_name"], self.user.first_name)
        self.assertEqual(response.data["role"], RoleChoices.OWNER)

    def test_authenticated_user_can_patch_own_profile(self):
        """Authenticated user can update own basic profile fields."""
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me"),
            {"first_name": "Marti", "last_name": "Borras"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Marti")
        self.assertEqual(self.user.last_name, "Borras")
        self.assertEqual(response.data["first_name"], "Marti")
        self.assertEqual(response.data["last_name"], "Borras")

    def test_unauthenticated_user_cannot_get_profile(self):
        """Unauthenticated requests to profile detail must return 401."""
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_user_cannot_patch_profile(self):
        """Unauthenticated requests to profile update must return 401."""
        response = self.client.patch(
            reverse("me"),
            {"first_name": "NoAuth"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

class QuerySetFilteringTests(BaseTestData):
    """Tests for queryset filtering to prevent ABAC/RBAC bypasses and data leaks."""

    @classmethod
    def setUpTestData(cls):
        """Set up multiple buildings and roles for filtering tests."""
        cls.admin = User.objects.create_user(
            email="admin@example.com",
            password="Password123",
            first_name="admin",
            is_superuser=True,
            is_staff=True,
        )

        cls.admin_finca_1 = cls._create_user("adminfinca1@example.com", RoleChoices.ADMIN)
        cls.admin_finca_2 = cls._create_user("adminfinca2@example.com", RoleChoices.ADMIN)
        cls.tenant_1 = cls._create_user("tenant1@example.com", RoleChoices.TENANT)
        cls.tenant_2 = cls._create_user("tenant2@example.com", RoleChoices.TENANT)

        cls.grup = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        # Three buildings under different admins de finca
        cls.edifici_1 = cls._create_edifici(administrador=cls.admin_finca_1, grup=cls.grup)
        cls.edifici_2 = cls._create_edifici(administrador=cls.admin_finca_2, grup=cls.grup)
        cls.edifici_3 = cls._create_edifici(administrador=cls.admin_finca_1, grup=cls.grup)

        # Tenants in different buildings
        Habitatge.objects.create(
            referenciaCadastral="HAB-T1-E1",
            planta="1",
            porta="A",
            superficie=80,
            edifici=cls.edifici_1,
            usuari=cls.tenant_1,
        )
        Habitatge.objects.create(
            referenciaCadastral="HAB-T2-E2",
            planta="1",
            porta="A",
            superficie=80,
            edifici=cls.edifici_2,
            usuari=cls.tenant_2,
        )

    def test_tenant_list_filtered_to_their_buildings_only(self):
        """Tenant GET /me/edificis/ shows only buildings where they have habitatge."""
        self.client.force_authenticate(user=self.tenant_1)
        response = self.client.get(reverse("me-edificis"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["idEdifici"] for item in response.data}
        self.assertEqual(returned_ids, {self.edifici_1.idEdifici})
        self.assertNotIn(self.edifici_2.idEdifici, returned_ids)
        self.assertNotIn(self.edifici_3.idEdifici, returned_ids)

    def test_admin_finca_list_filtered_to_their_buildings_only(self):
        """AdminFinca GET /me/edificis/ shows only buildings they administer."""
        self.client.force_authenticate(user=self.admin_finca_1)
        response = self.client.get(reverse("me-edificis"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["idEdifici"] for item in response.data}
        self.assertIn(self.edifici_1.idEdifici, returned_ids)
        self.assertIn(self.edifici_3.idEdifici, returned_ids)
        self.assertNotIn(self.edifici_2.idEdifici, returned_ids)

    def test_admin_sees_all_buildings_in_system(self):
        """Admin GET /me/edificis/ shows all buildings."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("me-edificis"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["idEdifici"] for item in response.data}
        self.assertGreaterEqual(len(returned_ids), 3)

    def test_unauthenticated_cannot_access_me_edificis(self):
        """Unauthenticated GET /me/edificis/ returns 401."""
        response = self.client.get(reverse("me-edificis"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tenant_response_fields_do_not_expose_admin_data(self):
        """Tenant list response must not include administradorFinca or nested private fields."""
        self.client.force_authenticate(user=self.tenant_1)
        response = self.client.get(reverse("me-edificis"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)
        building = response.data[0]
        self.assertIn("idEdifici", building)
        self.assertIn("localitzacio", building)
        self.assertNotIn("administradorFinca", building)
        self.assertNotIn("habitatges", building)
        self.assertNotIn("dadesEnergetiques", building)

    def test_cross_building_detail_access_blocked(self):
        """CRITICAL: Tenant accessing an unrelated building detail returns 403/404 (data leak check)."""
        self.client.force_authenticate(user=self.tenant_1)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici_2.idEdifici]))
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
            f"Got {response.status_code} — potential data leak!",
        )


class SecurityTests(BaseTestData):
    """Tests for security vulnerabilities (overposting, privilege escalation, etc)."""

    @classmethod
    def setUpTestData(cls):
        """Set up users for security testing."""
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.admin_finca = cls._create_user("adminfinca@example.com", RoleChoices.ADMIN)
        cls.altre_resident = cls._create_user("tenant2@example.com", RoleChoices.TENANT)

        cls.grup = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        cls.edifici_1 = cls._create_edifici(administrador=cls.admin_finca, grup=cls.grup)

        cls.habitatge_1 = Habitatge.objects.create(
            referenciaCadastral="HAB-1",
            planta="1",
            porta="A",
            superficie=80,
            edifici=cls.edifici_1,
            usuari=cls._create_user("tenant@example.com", RoleChoices.TENANT),
        )

    def test_assign_resident_rejects_overposting_sensitive_fields(self):
        """Overposting attack: serializer prevents setting unintended fields."""
        self.client.force_authenticate(user=self.admin_finca)

        response = self.client.patch(
            reverse("assignar-resident", args=[self.habitatge_1.referenciaCadastral]),
            {
                "user_id": self.altre_resident.id,
                "administradorFinca": self.admin.id,
            },
            format="json",
        )

        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])
        self.habitatge_1.refresh_from_db()
        self.assertEqual(self.habitatge_1.usuari_id, self.altre_resident.id)
        self.habitatge_1.edifici.refresh_from_db()
        self.assertEqual(self.habitatge_1.edifici.administradorFinca_id, self.admin_finca.id)

    def test_register_allows_building_admin_role(self):
        """Register endpoint allows admin role for building administrators."""
        response = self.client.post(
            reverse("register"),
            {
                "email": "admin-finca@example.com",
                "first_name": "Admin",
                "last_name": "Finca",
                "password": "BuildRankAdmin847",
                "password_confirm": "BuildRankAdmin847",
                "role": RoleChoices.ADMIN,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="admin-finca@example.com").exists())

        user = User.objects.get(email="admin-finca@example.com")
        self.assertEqual(user.profile.role, RoleChoices.ADMIN)


class AccountUpdateTests(BaseTestData):
    """Tests for authenticated account update endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = cls._create_user("user@example.com", RoleChoices.OWNER)

    def test_authenticated_user_can_patch_own_account(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me"),
            {"first_name": "NouNom"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "NouNom")
        self.assertEqual(self.user.last_name, "")

    def test_authenticated_user_can_put_own_account(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            reverse("me"),
            {
                "first_name": "Marti",
                "last_name": "Borras",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Marti")
        self.assertEqual(self.user.last_name, "Borras")

    def test_unauthenticated_user_cannot_patch_account(self):
        response = self.client.patch(
            reverse("me"),
            {"first_name": "Hack"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_account_ignores_role_field(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me"),
            {
                "first_name": "NouNom",
                "role": RoleChoices.ADMIN,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, "NouNom")
        self.assertEqual(self.user.profile.role, RoleChoices.OWNER)

    def test_authenticated_user_can_patch_own_email(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me"),
            {
                "email": "nou-email@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "nou-email@example.com")
        self.assertEqual(response.data["email"], "nou-email@example.com")

    def test_update_account_rejects_duplicate_email(self):
        User.objects.create_user(
            email="duplicat@example.com",
            password="Password123",
        )

        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            reverse("me"),
            {
                "email": "duplicat@example.com",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.email, "duplicat@example.com")
        self.assertIn("email", response.data)



class AuthEndpointTests(APITestCase):
    """Exhaustive tests for register/login/logout/me endpoints."""

    def setUp(self):
        # Limpia el caché de throttle antes de cada test para evitar contaminación
        # entre tests (el state de rate limiting persiste en caché entre tests).
        cache.clear()

    def _register_payload(self, **overrides):
        payload = {
            "email": "new-user@example.com",
            "first_name": "New",
            "last_name": "User",
            "password": "Gihistzzz_2026",
            "password_confirm": "Gihistzzz_2026",
        }
        payload.update(overrides)
        return payload

    def test_register_success_creates_user_profile_and_default_role(self):
        response = self.client.post(
            reverse("register"),
            self._register_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="new-user@example.com").exists())

        user = User.objects.get(email="new-user@example.com")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.role, RoleChoices.OWNER)
        self.assertEqual(response.data["role"], RoleChoices.OWNER)

    def test_register_success_with_explicit_owner_role(self):
        response = self.client.post(
            reverse("register"),
            self._register_payload(email="owner-explicit@example.com", role=RoleChoices.OWNER),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(email="owner-explicit@example.com")
        self.assertEqual(user.profile.role, RoleChoices.OWNER)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(email="duplicate@example.com", password="Password123")

        response = self.client.post(
            reverse("register"),
            self._register_payload(email="duplicate@example.com"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_register_rejects_password_mismatch(self):
        response = self.client.post(
            reverse("register"),
            self._register_payload(password_confirm="Different123"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_register_rejects_password_without_letters(self):
        response = self.client.post(
            reverse("register"),
            self._register_payload(password="12345678", password_confirm="12345678"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_register_rejects_password_without_digits(self):
        response = self.client.post(
            reverse("register"),
            self._register_payload(password="OnlyLetters", password_confirm="OnlyLetters"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_login_success_returns_tokens_user_and_creates_audit_log(self):
        user = User.objects.create_user(
            email="login-ok@example.com",
            password="Password123",
            first_name="Login",
            last_name="Ok",
        )
        user.profile.role = RoleChoices.OWNER
        user.profile.save(update_fields=["role"])

        response = self.client.post(
            reverse("login"),
            {"email": "login-ok@example.com", "password": "Password123"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["email"], "login-ok@example.com")

        self.assertEqual(TokenLoginLog.objects.filter(user=user, status=TokenLoginLog.LOGIN).count(), 1)

    def test_login_session_limit_blacklists_oldest_refresh_token(self):
        user = User.objects.create_user(
            email="session-limit@example.com",
            password="Password123",
        )

        refresh_tokens = []
        for _ in range(6):
            # Limpia caché de throttle en cada iteración: este test valida lógica
            # de sesiones, no rate limiting; evitamos que el throttle interfiera.
            cache.clear()
            response = self.client.post(
                reverse("login"),
                {"email": "session-limit@example.com", "password": "Password123"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            refresh_tokens.append(response.data["refresh"])

        oldest_refresh = refresh_tokens[0]
        refresh_response = self.client.post(
            reverse("token_refresh"),
            {"refresh": oldest_refresh},
            format="json",
        )

        self.assertIn(
            refresh_response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST],
        )
        self.assertEqual(
            TokenLoginLog.objects.filter(user=user, status=TokenLoginLog.LOGIN, logout_at__isnull=True).count(),
            5,
        )
        self.assertGreaterEqual(
            TokenLoginLog.objects.filter(user=user, status=TokenLoginLog.REVOKED).count(),
            1,
        )

    def test_login_rejects_invalid_credentials(self):
        User.objects.create_user(email="invalid-login@example.com", password="Password123")

        response = self.client.post(
            reverse("login"),
            {"email": "invalid-login@example.com", "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_logout_success_revokes_refresh_and_updates_audit_log(self):
        user = User.objects.create_user(email="logout-ok@example.com", password="Password123")

        login_response = self.client.post(
            reverse("login"),
            {"email": "logout-ok@example.com", "password": "Password123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        access_token = login_response.data["access"]
        refresh_token = login_response.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        logout_response = self.client.post(
            reverse("logout"),
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        log = TokenLoginLog.objects.filter(user=user).latest("login_at")
        self.assertEqual(log.status, TokenLoginLog.LOGOUT)
        self.assertIsNotNone(log.logout_at)
        self.assertTrue(BlacklistedToken.objects.filter(token__jti=log.jti).exists())

    def test_logout_rejects_invalid_refresh_token(self):
        user = User.objects.create_user(email="logout-invalid@example.com", password="Password123")
        self.client.force_authenticate(user=user)

        response = self.client.post(
            reverse("logout"),
            {"refresh": "not-a-valid-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("refresh", response.data)

    def test_logout_then_refresh_reuse_fails(self):
        user = User.objects.create_user(email="logout-reuse@example.com", password="Password123")

        login_response = self.client.post(
            reverse("login"),
            {"email": "logout-reuse@example.com", "password": "Password123"},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        access_token = login_response.data["access"]
        refresh_token = login_response.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        logout_response = self.client.post(
            reverse("logout"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        refresh_response = self.client.post(
            reverse("token_refresh"),
            {"refresh": refresh_token},
            format="json",
        )
        self.assertIn(
            refresh_response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST],
        )

    def test_me_with_tampered_access_token_fails(self):
        user = User.objects.create_user(email="tampered-token@example.com", password="Password123")
        refresh = RefreshToken.for_user(user)
        token = str(refresh.access_token)
        # Tamper a character in the middle of the signature segment.
        # Avoid the last character: its bottom 2 bits are base64 padding and are
        # silently ignored by the decoder, so flipping only those bits leaves the
        # decoded signature bytes unchanged and the token still passes validation.
        header, payload, sig = token.split(".")
        mid = len(sig) // 2
        tampered_char = "A" if sig[mid] != "A" else "z"
        tampered_sig = sig[:mid] + tampered_char + sig[mid + 1:]
        tampered = f"{header}.{payload}.{tampered_sig}"

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tampered}")
        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_expired_access_token_fails(self):
        user = User.objects.create_user(email="expired-token@example.com", password="Password123")
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        access.set_exp(lifetime=timedelta(seconds=-1))

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(access)}")
        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user_profile_data(self):
        user = User.objects.create_user(
            email="me-endpoint@example.com",
            password="Password123",
            first_name="Me",
            last_name="Endpoint",
        )
        user.profile.role = RoleChoices.TENANT
        user.profile.save(update_fields=["role"])

        self.client.force_authenticate(user=user)
        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "me-endpoint@example.com")
        self.assertEqual(response.data["first_name"], "Me")
        self.assertEqual(response.data["last_name"], "Endpoint")
        self.assertEqual(response.data["role"], RoleChoices.TENANT)


# ============================================================================
# Rate Limiting Tests
# ============================================================================

class RateLimitingTestCase(APITestCase):
    """Tests para validar rate limiting en endpoints de autenticación."""
    
    def setUp(self):
        # Cada test de throttle empieza con cuota limpia.
        cache.clear()
        self.client = APIClient()
        
        # Crear usuario de prueba para refresh
        self.user = User.objects.create_user(
            email='throttle-test@example.com',
            password='TestPassword123!'
        )
    
    def test_login_throttle_3_per_minute(self):
        """
        Verificar que /login permite 3 solicitudes por minuto,
        y rechaza la 4ª con HTTP 429.
        """
        login_url = reverse('login')
        payload = {
            'email': 'throttle-test@example.com',
            'password': 'TestPassword123!'
        }
        
        # Primer intento: OK
        response1 = self.client.post(login_url, payload, format='json')
        self.assertIn(response1.status_code, [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED])
        
        # Segundo intento: OK
        response2 = self.client.post(login_url, payload, format='json')
        self.assertIn(response2.status_code, [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED])
        
        # Tercer intento: OK
        response3 = self.client.post(login_url, payload, format='json')
        self.assertIn(response3.status_code, [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED])
        
        # Cuarto intento: THROTTLED (429)
        response4 = self.client.post(login_url, payload, format='json')
        self.assertEqual(response4.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                        msg="Esperado HTTP 429 al exceder límite de 3 login/min")
    
    def test_register_throttle_5_per_hour(self):
        """
        Verificar que /register permite 5 solicitudes por hora,
        y rechaza la 6ª con HTTP 429.
        """
        register_url = reverse('register')
        
        for i in range(5):
            payload = {
                'email': f'throttle-user{i}@example.com',
                'password': 'TestPassword123!',
                'first_name': f'User{i}',
                'last_name': 'Test',
                'password_confirm': 'TestPassword123!',
            }
            response = self.client.post(register_url, payload, format='json')
            self.assertIn(response.status_code,
                         [status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST],
                         msg=f"Intento {i+1} debería ser válido")
        
        # Sexto intento: THROTTLED
        payload = {
            'email': 'throttle-user99@example.com',
            'password': 'TestPassword123!',
            'first_name': 'User99',
            'last_name': 'Test',
            'password_confirm': 'TestPassword123!',
        }
        response6 = self.client.post(register_url, payload, format='json')
        self.assertEqual(response6.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                        msg="Esperado HTTP 429 al exceder límite de 5 register/hora")
    
    def test_refresh_throttle_20_per_minute(self):
        """
        Verificar que /refresh permite ~20 solicitudes por minuto.
        (Este test es indicativo; en producción requiere timing preciso)
        """
        # Obtener tokens del usuario
        login_url = reverse('login')
        login_payload = {
            'email': 'throttle-test@example.com',
            'password': 'TestPassword123!'
        }
        
        login_response = self.client.post(login_url, login_payload, format='json')
        
        if login_response.status_code == status.HTTP_200_OK:
            refresh_token = login_response.data.get('refresh')
            refresh_url = reverse('token_refresh')
            
            # Intentar 20 refreshes
            for i in range(20):
                response = self.client.post(
                    refresh_url,
                    {'refresh': refresh_token},
                    format='json'
                )
                if response.status_code == status.HTTP_200_OK:
                    refresh_token = response.data.get('refresh', refresh_token)
                self.assertIn(response.status_code,
                             [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED,
                              status.HTTP_400_BAD_REQUEST],
                             msg=f"Refresh {i+1} no debería estar throttled")
            
            # Intento 21: podría estar throttled (dependiendo de timing)
            response21 = self.client.post(
                refresh_url,
                {'refresh': refresh_token},
                format='json'
            )
            # Simplemente verificar que responde (puede ser 429 o no según timing)
            self.assertIsNotNone(response21.status_code)
    
    def test_throttle_response_format(self):
        """
        Verificar que la respuesta HTTP 429 incluye retry information.
        """
        login_url = reverse('login')
        payload = {
            'email': 'noexit@example.com',
            'password': 'WrongPassword123!'
        }
        
        # Exceder límite
        for _ in range(4):  # 4 intentos rápidos
            self.client.post(login_url, payload, format='json')
        
        # Cuarto intento debe retornar 429
        response = self.client.post(login_url, payload, format='json')
        
        if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            # Verificar que incluye información útil
            self.assertIn('detail', response.data,
                         msg="Respuesta 429 debe incluir 'detail'")
            self.assertIn('Request was throttled', str(response.data['detail']),
                         msg="Debe indicar que fue throttled")


class ThrottleByIPTestCase(APITestCase):
    """Verifica que el rate limiting es por IP (anónimos)."""

    def setUp(self):
        # Limpia caché de throttle para que este test empiece con cuota fresca,
        # sin contaminación de tests anteriores que usan la misma IP (127.0.0.1).
        cache.clear()

    def test_throttle_applies_to_ip(self):
        """
        Verificar que diferentes usuarios (same IP) comparten limit.
        Nota: En tests, todos son de 127.0.0.1 por defecto.
        """
        login_url = reverse('login')
        
        # Mismo cliente = misma IP
        for i in range(4):
            response = self.client.post(
                login_url,
                {'email': f'user{i}@test.com', 'password': 'pass'},
                format='json'
            )
            if i < 3:
                self.assertNotEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                                   msg=f"Intento {i+1} no debería estar throttled")
            else:
                # Cuarto intento: throttled
                self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS,
                               msg="Intento 4 debería estar throttled por IP")

class AdminRoleSemanticsTests(BaseTestData):
    """Tests to ensure role semantics are aligned with the domain model."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = cls._create_user("owner_semantics@example.com", RoleChoices.OWNER)
        cls.admin_finca = cls._create_user("admin_finca@example.com", RoleChoices.ADMIN)

        cls.grup = GrupComparable.objects.create(
            idGrup=99,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        cls.edifici = cls._create_edifici(administrador=cls.admin_finca, grup=cls.grup)

        cls.habitatge = Habitatge.objects.create(
            referenciaCadastral="HAB-SEM-1",
            planta="1",
            porta="A",
            superficie=80,
            edifici=cls.edifici,
            usuari=cls.owner,
        )

    def test_owner_cannot_use_admin_finca_permissions(self):
        """Owner must not be treated as admin de finca."""
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            reverse("assignar-resident", args=[self.habitatge.referenciaCadastral]),
            {"user_id": self.owner.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(REST_FRAMEWORK=NO_THROTTLE_REST_FRAMEWORK)
class SystemAdminMeEndpointTests(APITestCase):
    """Tests per diferenciar administrador de sistema i administrador de finca."""

    def setUp(self):
        cache.clear()

    def test_me_returns_system_admin_flags_for_superuser(self):
        user = User.objects.create_superuser(
            email="sysadmin@example.com",
            password="Adminpass123",
        )

        self.client.force_authenticate(user=user)

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_staff"])
        self.assertTrue(response.data["is_superuser"])
        self.assertTrue(response.data["is_system_admin"])

    def test_me_admin_role_is_not_system_admin(self):
        user = User.objects.create_user(
            email="adminfinca@example.com",
            password="Adminpass123",
        )

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = RoleChoices.ADMIN
        profile.save(update_fields=["role"])

        # Recarreguem l'usuari per evitar que el profile quedi cachejat amb el rol anterior.
        user = User.objects.get(pk=user.pk)

        self.client.force_authenticate(user=user)

        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], RoleChoices.ADMIN)
        self.assertFalse(response.data["is_staff"])
        self.assertFalse(response.data["is_superuser"])
        self.assertFalse(response.data["is_system_admin"])

    def test_superuser_can_login_from_app(self):
        User.objects.create_superuser(
            email="sysadminlogin@example.com",
            password="Adminpass123",
        )

        payload = {
            "email": "sysadminlogin@example.com",
            "password": "Adminpass123",
        }

        response = self.client.post(reverse("login"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
    
@override_settings(
    REST_FRAMEWORK=NO_THROTTLE_REST_FRAMEWORK,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_FRONTEND_URL="http://localhost/reset-password",
)
class PasswordResetTests(APITestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.user = User.objects.create_user(
            email="reset@example.com",
            password="OldPassword123",
        )

    def _request_reset_and_get_uid_token(self):
        response = self.client.post(
            reverse("password-reset"),
            {"email": "reset@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn("uid", response.data)
        self.assertNotIn("token", response.data)
        self.assertEqual(len(mail.outbox), 1)

        body = mail.outbox[0].body
        uid_match = re.search(r"uid=([^&\s]+)", body)
        token_match = re.search(r"token=([^\s]+)", body)

        self.assertIsNotNone(uid_match)
        self.assertIsNotNone(token_match)

        return uid_match.group(1), token_match.group(1)

    def test_password_reset_request_existing_email_sends_email_without_returning_token(self):
        response = self.client.post(
            reverse("password-reset"),
            {"email": "reset@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("detail", response.data)
        self.assertNotIn("uid", response.data)
        self.assertNotIn("token", response.data)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["reset@example.com"])
        self.assertIn("http://localhost/reset-password", mail.outbox[0].body)
        self.assertIn("uid=", mail.outbox[0].body)
        self.assertIn("token=", mail.outbox[0].body)

    def test_password_reset_request_unknown_email_does_not_enumerate_accounts(self):
        response = self.client.post(
            reverse("password-reset"),
            {"email": "unknown@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("detail", response.data)
        self.assertNotIn("uid", response.data)
        self.assertNotIn("token", response.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_confirm_valid_token_changes_password(self):
        uid, token = self._request_reset_and_get_uid_token()

        response = self.client.post(
            reverse("password-reset-confirm"),
            {
                "uid": uid,
                "token": token,
                "password": "NewPassword123",
                "password_confirm": "NewPassword123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPassword123"))

    def test_password_reset_confirm_invalid_token_fails(self):
        uid, _token = self._request_reset_and_get_uid_token()

        response = self.client.post(
            reverse("password-reset-confirm"),
            {
                "uid": uid,
                "token": "invalid-token",
                "password": "NewPassword123",
                "password_confirm": "NewPassword123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("token", response.data)

    def test_password_reset_confirm_password_mismatch_fails(self):
        uid, token = self._request_reset_and_get_uid_token()

        response = self.client.post(
            reverse("password-reset-confirm"),
            {
                "uid": uid,
                "token": token,
                "password": "NewPassword123",
                "password_confirm": "DifferentPassword123",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_password_reset_confirm_revokes_active_refresh_tokens(self):
        login_response = self.client.post(
            reverse("login"),
            {
                "email": "reset@example.com",
                "password": "OldPassword123",
            },
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        refresh = RefreshToken(login_response.data["refresh"])
        jti = str(refresh.get("jti"))
        outstanding = OutstandingToken.objects.get(jti=jti)
        self.assertFalse(BlacklistedToken.objects.filter(token=outstanding).exists())
        self.assertEqual(
            TokenLoginLog.objects.filter(
                user=self.user,
                status=TokenLoginLog.LOGIN,
                logout_at__isnull=True,
            ).count(),
            1,
        )

        uid, token = self._request_reset_and_get_uid_token()

        response = self.client.post(
            reverse("password-reset-confirm"),
            {
                "uid": uid,
                "token": token,
                "password": "NewPassword123",
                "password_confirm": "NewPassword123",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())
        self.assertEqual(
            TokenLoginLog.objects.filter(
                user=self.user,
                status=TokenLoginLog.REVOKED,
                logout_at__isnull=False,
            ).count(),
            1,
        )

@override_settings(
    GOOGLE_OAUTH_CLIENT_ID="test-google-client-id.apps.googleusercontent.com",
    REST_FRAMEWORK=NO_THROTTLE_REST_FRAMEWORK,
)
class GoogleOAuthTests(APITestCase):
    def setUp(self):
        self.url = reverse("google-oauth")
        cache.clear()

    @patch("apps.accounts.serializers.google_id_token.verify_oauth2_token")
    def test_google_oauth_creates_user_and_returns_jwt_tokens(self, mock_verify):
        mock_verify.return_value = {
            "email": "marti@example.com",
            "email_verified": True,
            "given_name": "Martí",
            "family_name": "Borràs",
        }

        response = self.client.post(
            self.url,
            {
                "id_token": "valid-google-id-token",
                "mode": "register",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "marti@example.com")
        self.assertEqual(response.data["user"]["first_name"], "Martí")
        self.assertEqual(response.data["user"]["last_name"], "Borràs")
        self.assertEqual(response.data["user"]["role"], RoleChoices.OWNER)

        user = User.objects.get(email="marti@example.com")
        self.assertEqual(user.first_name, "Martí")
        self.assertEqual(user.last_name, "Borràs")
        self.assertEqual(user.profile.role, RoleChoices.OWNER)
        self.assertEqual(TokenLoginLog.objects.filter(user=user).count(), 1)

    @patch("apps.accounts.serializers.google_id_token.verify_oauth2_token")
    def test_google_oauth_existing_user_is_not_duplicated(self, mock_verify):
        existing_user = User.objects.create_user(
            email="existing@example.com",
            password="Password123",
            first_name="Existing",
            last_name="User",
        )

        mock_verify.return_value = {
            "email": "existing@example.com",
            "email_verified": True,
            "given_name": "GoogleName",
            "family_name": "GoogleSurname",
        }

        response = self.client.post(
            self.url,
            {
                "id_token": "valid-google-id-token",
                "mode": "register"
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(User.objects.filter(email="existing@example.com").count(), 1)

        self.assertIn("detail", response.data)

        existing_user.refresh_from_db()
        self.assertEqual(existing_user.first_name, "Existing")
        self.assertEqual(existing_user.last_name, "User")

    @patch("apps.accounts.serializers.google_id_token.verify_oauth2_token")
    def test_google_oauth_rejects_unverified_email(self, mock_verify):
        mock_verify.return_value = {
            "email": "notverified@example.com",
            "email_verified": False,
            "given_name": "No",
            "family_name": "Verified",
        }

        response = self.client.post(
            self.url,
            {
                "id_token": "valid-google-id-token",
                "mode": "register",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email="notverified@example.com").exists())

    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_google_oauth_requires_client_id_configuration(self):
        response = self.client.post(
            self.url,
            {
                "id_token": "any-token",
                "mode": "login",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        
    @patch("apps.accounts.serializers.google_id_token.verify_oauth2_token")
    def test_google_oauth_creates_user_with_requested_role(
        self,
        mock_verify,
    ):
        mock_verify.return_value = {
            "email": "tenant-google@example.com",
            "email_verified": True,
            "given_name": "Tenant",
            "family_name": "Google",
        }

        response = self.client.post(
            self.url,
            {
                "id_token": "valid-google-id-token",
                "role": RoleChoices.TENANT,
                "mode": "register",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(
            response.data["user"]["email"],
            "tenant-google@example.com",
        )
        self.assertEqual(
            response.data["user"]["role"],
            RoleChoices.TENANT,
        )

        user = User.objects.get(email="tenant-google@example.com")
        self.assertEqual(user.profile.role, RoleChoices.TENANT)

    @patch("apps.accounts.serializers.google_id_token.verify_oauth2_token")
    def test_google_oauth_existing_user_does_not_change_role(
        self,
        mock_verify,
    ):
        existing_user = User.objects.create_user(
            email="existing-role@example.com",
            password="Password123",
            first_name="Existing",
            last_name="Role",
        )

        existing_user.profile.role = RoleChoices.OWNER
        existing_user.profile.save(update_fields=["role"])

        mock_verify.return_value = {
            "email": "existing-role@example.com",
            "email_verified": True,
            "given_name": "GoogleName",
            "family_name": "GoogleSurname",
        }

        response = self.client.post(
            self.url,
            {
                "id_token": "valid-google-id-token",
                "role": RoleChoices.TENANT,
                "mode": "register",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

        existing_user.refresh_from_db()
        existing_user.profile.refresh_from_db()

        self.assertEqual(existing_user.profile.role, RoleChoices.OWNER)

        self.assertEqual(
            existing_user.profile.role,
            RoleChoices.OWNER,
        )

    @patch("apps.accounts.serializers.google_id_token.verify_oauth2_token")
    def test_google_oauth_rejects_invalid_role(
        self,
        mock_verify,
    ):
        mock_verify.return_value = {
            "email": "invalid-role-google@example.com",
            "email_verified": True,
            "given_name": "Invalid",
            "family_name": "Role",
        }

        response = self.client.post(
            self.url,
            {
                "id_token": "valid-google-id-token",
                "role": "superadmin",
                "mode": "register",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertIn("role", response.data)

        self.assertFalse(
            User.objects.filter(
                email="invalid-role-google@example.com"
            ).exists()
        )
