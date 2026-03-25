import os
import threading
import unittest
from datetime import timedelta

from django.test import TransactionTestCase
from django.db import connections
from django.urls import reverse
from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
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


CONCURRENCY_TEST_MODE = os.getenv("RUN_CONCURRENCY_TESTS", "").strip().lower()
ENABLE_CONCURRENCY_DIAGNOSTIC = CONCURRENCY_TEST_MODE in {"1", "true", "diagnostic", "all", "strict"}
ENABLE_CONCURRENCY_STRICT = CONCURRENCY_TEST_MODE in {"strict", "all"}

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
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
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
        cls.admin_finca = cls._create_user("owner@example.com", RoleChoices.OWNER)
        cls.altre_admin_finca = cls._create_user("owner2@example.com", RoleChoices.OWNER)
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
        cls.admin_finca = cls._create_user("owner@example.com", RoleChoices.OWNER)
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


class QueryTests(BaseTestData):
    """Tests for building query endpoint (GET /api/me/edificis/)."""

    @classmethod
    def setUpTestData(cls):
        """Set up buildings and users with different roles."""
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.admin_finca = cls._create_user("owner@example.com", RoleChoices.OWNER)
        cls.altre_admin_finca = cls._create_user("owner2@example.com", RoleChoices.OWNER)
        cls.resident = cls._create_user("tenant@example.com", RoleChoices.TENANT)
        cls.altre_resident = cls._create_user("tenant2@example.com", RoleChoices.TENANT)

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
            usuari=cls.altre_resident,
        )

    def test_resident_me_edificis_returns_only_linked_buildings(self):
        """Resident can see only buildings where they have an apartment."""
        self.client.force_authenticate(user=self.resident)

        response = self.client.get(reverse("me-edificis"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["idEdifici"], self.edifici_1.idEdifici)
        self.assertIn("idEdifici", response.data[0])
        self.assertIn("localitzacio", response.data[0])
        self.assertNotIn("administradorFinca", response.data[0])
        self.assertNotIn("habitatges", response.data[0])
        self.assertNotIn("dadesEnergetiques", response.data[0])

    def test_admin_finca_me_edificis_returns_only_managed_buildings(self):
        """AdminFinca can see only buildings they manage."""
        self.client.force_authenticate(user=self.admin_finca)

        response = self.client.get(reverse("me-edificis"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["idEdifici"], self.edifici_1.idEdifici)

    def test_admin_sistema_me_edificis_returns_all_buildings(self):
        """AdminSistema can see all buildings in the system."""
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(reverse("me-edificis"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["idEdifici"] for item in response.data}
        self.assertEqual(returned_ids, {self.edifici_1.idEdifici, self.edifici_2.idEdifici})

    @unittest.skip("TODO(security-debt): ABAC not enforced on building detail endpoint for cross-building tenant access")
    def test_tenant_cannot_access_other_building_detail(self):
        """Security debt: tenant should not access details of unrelated buildings."""
        self.client.force_authenticate(user=self.resident)

        response = self.client.get(reverse("edifici-detail", args=[self.edifici_2.idEdifici]))

        # Expected behavior after hardening: return 403 for unrelated building details.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SecurityTests(BaseTestData):
    """Tests for security vulnerabilities (overposting, privilege escalation, etc)."""

    @classmethod
    def setUpTestData(cls):
        """Set up users for security testing."""
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.admin_finca = cls._create_user("owner@example.com", RoleChoices.OWNER)
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

    def test_register_cannot_escalate_to_admin_role(self):
        """Privilege escalation: register endpoint rejects role=admin requests."""
        response = self.client.post(
            reverse("register"),
            {
                "email": "evil-admin@example.com",
                "first_name": "Evil",
                "last_name": "User",
                "password": "Password123",
                "password_confirm": "Password123",
                "role": RoleChoices.ADMIN,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email="evil-admin@example.com").exists())


class AuthEndpointTests(APITestCase):
    """Exhaustive tests for register/login/logout/me endpoints."""

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
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

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

    @unittest.skipUnless(
        bool(settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES")),
        "Rate limit test skipped because DRF throttling is not configured.",
    )
    def test_login_rate_limit(self):
        User.objects.create_user(email="ratelimit@example.com", password="Password123")
        status_codes = []

        for _ in range(20):
            response = self.client.post(
                reverse("login"),
                {"email": "ratelimit@example.com", "password": "wrong-password"},
                format="json",
            )
            status_codes.append(response.status_code)

        self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, status_codes)

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


@unittest.skipUnless(
    ENABLE_CONCURRENCY_DIAGNOSTIC,
    "Temporary concurrency tests are disabled by default. Set RUN_CONCURRENCY_TESTS=diagnostic (or strict/all) to run.",
)
class TemporaryConcurrencyRegistrationTests(TransactionTestCase):
    """Temporary opt-in concurrency tests for registration endpoint."""

    def test_parallel_register_same_email_diagnostic(self):
        email = "temp-concurrency-register@example.com"
        password = "Gihistzzz_2026"
        workers = 6

        statuses = []
        db_race_errors = []
        unexpected_errors = []
        lock = threading.Lock()
        barrier = threading.Barrier(workers)

        def worker():
            client = APIClient()
            client.raise_request_exception = False
            payload = {
                "email": email,
                "first_name": "Temp",
                "last_name": "Concurrency",
                "password": password,
                "password_confirm": password,
            }
            try:
                barrier.wait(timeout=5)
                response = client.post(reverse("register"), payload, format="json")
                with lock:
                    statuses.append(response.status_code)
            except Exception as exc:
                with lock:
                    text = str(exc)
                    if "accounts_user_email_key" in text or "duplicate key value" in text:
                        db_race_errors.append(text)
                    else:
                        unexpected_errors.append(text)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads), "Some worker threads did not finish")
        self.assertEqual(unexpected_errors, [])
        self.assertEqual(len(statuses), workers)

        allowed_statuses = {
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        }
        self.assertTrue(set(statuses).issubset(allowed_statuses), f"Unexpected statuses: {statuses}")

        # Diagnostic baseline while concurrency handling is not yet implemented:
        # exactly one row should exist regardless of response distribution.
        self.assertEqual(User.objects.filter(email=email).count(), 1)
        self.assertEqual(Profile.objects.filter(user__email=email).count(), 1)
        self.assertEqual(TokenLoginLog.objects.filter(user__email=email).count(), 0)


@unittest.skipUnless(
    ENABLE_CONCURRENCY_STRICT,
    "Strict concurrency tests are disabled by default. Set RUN_CONCURRENCY_TESTS=strict (or all) to run.",
)
class StrictConcurrencyRegistrationTests(TransactionTestCase):
    """Strict opt-in concurrency checks for registration endpoint behavior."""

    def test_parallel_register_same_email_never_returns_500(self):
        email = "strict-concurrency-register@example.com"
        password = "Gihistzzz_2026"
        workers = 8

        statuses = []
        unexpected_errors = []
        lock = threading.Lock()
        barrier = threading.Barrier(workers)

        def worker():
            client = APIClient()
            client.raise_request_exception = False
            payload = {
                "email": email,
                "first_name": "Strict",
                "last_name": "Concurrency",
                "password": password,
                "password_confirm": password,
            }
            try:
                barrier.wait(timeout=5)
                response = client.post(reverse("register"), payload, format="json")
                with lock:
                    statuses.append(response.status_code)
            except Exception as exc:
                with lock:
                    unexpected_errors.append(str(exc))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker) for _ in range(workers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        self.assertFalse(any(thread.is_alive() for thread in threads), "Some worker threads did not finish")
        self.assertEqual(unexpected_errors, [])
        self.assertEqual(len(statuses), workers)

        # Strict behavior expected after concurrency-hardening:
        # one success + the rest controlled 400 responses, never 500.
        self.assertEqual(statuses.count(status.HTTP_201_CREATED), 1)
        self.assertEqual(statuses.count(status.HTTP_500_INTERNAL_SERVER_ERROR), 0)
        self.assertEqual(
            statuses.count(status.HTTP_400_BAD_REQUEST),
            workers - 1,
            f"Expected only 201/400 responses, got: {statuses}",
        )
        self.assertEqual(User.objects.filter(email=email).count(), 1)
        self.assertEqual(Profile.objects.filter(user__email=email).count(), 1)
        self.assertEqual(TokenLoginLog.objects.filter(user__email=email).count(), 0)
