from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import (
    AccessDenialLog,
    Profile,
    RoleChoices,
    User,
)
from apps.buildings.models import (
    Edifici,
    GrupComparable,
    Habitatge,
    Localitzacio,
)

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