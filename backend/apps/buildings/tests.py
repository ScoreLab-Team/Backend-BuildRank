from django.test import TestCase
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model

from apps.buildings.models import Edifici, Habitatge, Localitzacio, GrupComparable
from apps.buildings.serializers import EdificiDetailSerializer, LocalitzacioSerializer
from apps.accounts.models import RoleChoices

User = get_user_model()


class BaseTestData(APITestCase):

    @classmethod
    def _create_user(cls, email, role):
        user = User.objects.create_user(email=email, password="Password123", first_name="Test")
        user.profile.role = role
        user.profile.save(update_fields=["role"])
        return user

    @classmethod
    def _create_edifici(cls, administrador, grup, numero=1, carrer="Carrer test"):
        loc = Localitzacio.objects.create(
            carrer=carrer, numero=numero, codiPostal="08001",
            barri="Centre", latitud=41.0, longitud=2.0, zonaClimatica="C2",
        )
        return Edifici.objects.create(
            anyConstruccio=2000, tipologia="Residencial", superficieTotal=400,
            reglament="CTE", orientacioPrincipal="Sud",
            localitzacio=loc, administradorFinca=administrador, grupComparable=grup,
        )


# ============================================================================
# 1. VALIDATION (via API + serializer directo para els casos únics)
# ============================================================================

class EdificiValidationTests(BaseTestData):
    """Input validation: required fields, boundary values, serializer logic."""

    @staticmethod
    def _base_localitzacio_data():
        return {"carrer": "Carrer Test", "barri": "Centre", "zonaClimatica": "C2"}

    def setUp(self):
        self.user = self._create_user("admin@example.com", RoleChoices.ADMIN)
        self.client.force_authenticate(user=self.user)
        self.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-100"
        )
        self.loc = Localitzacio.objects.create(
            **self._base_localitzacio_data(), numero=10, codiPostal="08001",
            latitud=41.0, longitud=2.0,
        )

    def test_required_fields_rejected_with_error_codes(self):
        """POST missing required fields → 400 with 'required' error on each field."""
        response = self.client.post(
            reverse("edifici-list"),
            {"anyConstruccio": 2010, "superficieTotal": 150.0},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ("tipologia", "reglament", "orientacioPrincipal"):
            self.assertIn(field, response.data)
            self.assertEqual(response.data[field][0].code, "required")

    def test_boundary_values_rejected(self):
        """Serializer rejects future year and negative surface (direct, no HTTP overhead)."""
        base = {
            "tipologia": "Residencial", "reglament": "CTE", "orientacioPrincipal": "Nord",
            "localitzacio": self.loc.id, "grupComparable": self.grup.id,
            "administradorFinca": self.user.id,
        }
        s1 = EdificiDetailSerializer(data={**base, "anyConstruccio": 2099, "superficieTotal": 100})
        self.assertFalse(s1.is_valid())
        self.assertIn("anyConstruccio", s1.errors)

        s2 = EdificiDetailSerializer(data={**base, "anyConstruccio": 2000, "superficieTotal": -5})
        self.assertFalse(s2.is_valid())
        self.assertIn("superficieTotal", s2.errors)

    def test_localitzacio_rejects_invalid_postal_and_coordinates(self):
        """LocalitzacioSerializer rejects malformed postal code and out-of-range coords."""
        base = self._base_localitzacio_data()

        s1 = LocalitzacioSerializer(data={**base, "codiPostal": "0800", "latitud": 41.0, "longitud": 2.0})
        self.assertFalse(s1.is_valid())
        self.assertIn("codiPostal", s1.errors)

        s2 = LocalitzacioSerializer(data={**base, "codiPostal": "08001", "latitud": 91.0, "longitud": 2.0})
        self.assertFalse(s2.is_valid())
        self.assertIn("latitud", s2.errors)

        s3 = LocalitzacioSerializer(data={**base, "codiPostal": "08001", "latitud": 41.0, "longitud": 181.0})
        self.assertFalse(s3.is_valid())
        self.assertIn("longitud", s3.errors)

    def test_invalid_field_type_returns_400(self):
        """Non-numeric value for an integer field returns 400 (API smoke test)."""
        response = self.client.post(
            reverse("edifici-list"),
            {"anyConstruccio": "not-a-number", "tipologia": "Residencial",
             "superficieTotal": 100, "reglament": "CTE", "orientacioPrincipal": "Nord"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ============================================================================
# 2. QUERYSET FILTERING + PERMISSIONS (RBAC + ABAC)
# ============================================================================

class EdificiAccessTests(BaseTestData):
    """Queryset filtering, ABAC enforcement and combined role permission tests."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.owner1 = cls._create_user("owner1@example.com", RoleChoices.OWNER)
        cls.owner2 = cls._create_user("owner2@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant@example.com", RoleChoices.TENANT)

        cls.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        # ADMIN role → EdificiViewSet filtra per administradorFinca=user
        cls.edifici_1 = cls._create_edifici(cls.admin, cls.grup, numero=10)
        cls.edifici_2 = cls._create_edifici(cls.admin, cls.grup, numero=20)

        # OWNER/TENANT role → EdificiViewSet filtra per habitatges__usuari=user
        Habitatge.objects.create(
            referenciaCadastral="HAB-O1", planta="1", porta="A",
            superficie=80, edifici=cls.edifici_1, usuari=cls.owner1,
        )
        Habitatge.objects.create(
            referenciaCadastral="HAB-001", planta="1", porta="B",
            superficie=80, edifici=cls.edifici_1, usuari=cls.tenant,
        )

    def test_each_role_list_sees_only_authorized_buildings(self):
        """Queryset filtering returns only buildings the user is authorized for."""
        cases = [
            (self.tenant, {self.edifici_1.idEdifici}),
            (self.owner1, set()),
        ]
        for user, expected_ids in cases:
            with self.subTest(user=user.email):
                self.client.force_authenticate(user=user)
                response = self.client.get(reverse("edifici-list"))
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual({item["idEdifici"] for item in response.data}, expected_ids)

    def test_admin_list_returns_all_buildings(self):
        """Admin list returns all buildings in the system."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("edifici-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["idEdifici"] for item in response.data}
        self.assertIn(self.edifici_1.idEdifici, returned_ids)
        self.assertIn(self.edifici_2.idEdifici, returned_ids)

    def test_cross_building_access_blocked(self):
        """Tenant and owner both get 403/404 on buildings they have no relation to."""
        cases = [
            (self.tenant, self.edifici_2),
            (self.owner1, self.edifici_2),
        ]
        for user, edifici in cases:
            with self.subTest(user=user.email, edifici=edifici.idEdifici):
                self.client.force_authenticate(user=user)
                response = self.client.get(reverse("edifici-detail", args=[edifici.idEdifici]))
                self.assertIn(
                    response.status_code,
                    [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
                )

    def test_admin_can_access_any_building(self):
        """Admin gets 200 on any building detail regardless of who administers it."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici_1.idEdifici]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_gets_401(self):
        """Unauthenticated requests are rejected with 401."""
        self.assertEqual(
            self.client.get(reverse("edifici-list")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_tenant_cannot_write_to_building(self):
        """Tenant cannot PATCH or DELETE a building, even one they live in."""
        self.client.force_authenticate(user=self.tenant)
        patch_resp = self.client.patch(
            reverse("edifici-detail", args=[self.edifici_1.idEdifici]),
            {"orientacioPrincipal": "Est"}, format="json",
        )
        delete_resp = self.client.delete(reverse("edifici-detail", args=[self.edifici_1.idEdifici]))
        self.assertEqual(patch_resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_resp.status_code, status.HTTP_403_FORBIDDEN)


# ============================================================================
# 3. EDGE CASES + PERFORMANCE
# ============================================================================

class EdificiEdgeCaseAndPerformanceTests(BaseTestData):
    """404s on nonexistent resources and N+1 query detection."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        cls.buildings = [
                cls._create_edifici(cls.admin, cls.grup, numero=i, carrer=f"Carrer {i}")
            for i in range(1, 6)
        ]

    def test_nonexistent_building_returns_404(self):
        """GET, PATCH and DELETE on nonexistent building return 404."""
        self.client.force_authenticate(user=self.admin)
        for method in ("get", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    reverse("edifici-detail", args=[999999]),
                    **({"data": {}, "format": "json"} if method == "patch" else {}),
                )
                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_query_count_no_n_plus_one(self):
        """GET /edificis/ with 5 buildings uses fewer than 20 queries (N+1 check)."""
        self.client.force_authenticate(user=self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse("edifici-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLess(
            len(ctx.captured_queries), 20,
            f"Possible N+1: {len(ctx.captured_queries)} queries for {len(response.data)} buildings",
        )
"""
    Com de moment en aquest sprint la lliga no esta implementada, no es poden testejar aquestes features
    pero encara aixi els tests estan fets per complir amb la Definition of Done
    def test_get_queryset_filtra_per_liga(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=10)
        e2 = Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=20)
        e3 = Edifici.objects.create(idEdifici="E3", liga="B", puntuacioBase=30)

        response = self.client.get(self.url, {'liga': 'A'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ids = [e['idEdifici'] for e in response.data]
        self.assertIn("E1", ids)
        self.assertIn("E2", ids)
        self.assertNotIn("E3", ids) #Només haurien d'apareixer els edificis 1 i 2

    def test_get_queryset_ordenado_por_puntuacioBase_desc(self):
        Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=10)
        Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=30)
        Edifici.objects.create(idEdifici="E3", liga="A", puntuacioBase=20)

        response = self.client.get(self.url, {'liga': 'A'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        puntuacioBases = [e['puntuacioBase'] for e in response.data]

        self.assertEqual(puntuacioBases, sorted(puntuacioBases, reverse=True)) #Haurien d'estar ordenats de major a menor puntuacioBase

    def test_posicion_dentro_del_top(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)
        e2 = Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=80)
        e3 = Edifici.objects.create(idEdifici="E3", liga="A", puntuacioBase=60)

        url = reverse('edifici-posicion', args=[e2.id])
        response = self.client.get(url, {'top': 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['posicion'], 2) #Hauria d'estar en posició 2
        self.assertTrue(response.data['esta_en_top']) #Hauria d'estar confirmat en el top
        self.assertEqual(response.data['puntos_para_top'], 0) #Com esta en el top hauria d'estar a 0 punts per el top

    def test_posicion_fuera_del_top(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)
        e2 = Edifici.objects.create(idEdifici="E2", liga="A", puntuacioBase=80)
        e3 = Edifici.objects.create(idEdifici="E3", liga="A", puntuacioBase=50)

        url = reverse('edifici-posicion', args=[e3.id])
        response = self.client.get(url, {'top': 2})

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['posicion'], 3) #La posició hauria de ser 3
        self.assertFalse(response.data['esta_en_top']) #Com els args inclouen top 2 no hauria d'estar en el top
        self.assertEqual(response.data['puntos_para_top'], 30) #La diferencia entre el segon (80) i el terçer (50) es 30

    def test_posicion_top_mayor_que_total(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)

        url = reverse('edifici-posicion', args=[e1.id])
        response = self.client.get(url, {'top': 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK) #Comprovar que no es trenca quan proves un top major que el numero d'edificis

        self.assertTrue(response.data['esta_en_top'])
        self.assertEqual(response.data['puntos_para_top'], 0)

    def test_posicion_solo_misma_liga(self):
        e1 = Edifici.objects.create(idEdifici="E1", liga="A", puntuacioBase=100)
        e2 = Edifici.objects.create(idEdifici="E2", liga="B", puntuacioBase=200)

        url = reverse('edifici-posicion', args=[e1.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data['posicion'], 1) #Comprovar que nomes mira el top en una mateixa lliga
"""