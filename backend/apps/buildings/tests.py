from django.test import TestCase
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.buildings.models import CatalegMillora, Edifici, EdificiAuditLog, EstatValidacio, Habitatge, Localitzacio, GrupComparable, MilloraImplementada, SimulacioMillora
from apps.buildings.serializers import EdificiDetailSerializer, LocalitzacioSerializer
from apps.accounts.models import RoleChoices
from .simulation.engine import simular_millores, clamp, UnitatBaseMillora

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
            (self.owner1, {self.edifici_1.idEdifici}),  # ← tiene habitatge en edifici_1
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

# ============================================================================
# 4. DESACTIVACIÓ LÒGICA per al AdminSistema
# ============================================================================

class EdificiDesactivacioLogicaTests(BaseTestData):
    """
    Comprova que la desactivació lògica funciona correctament:
    camps, manager actius, visibilitat i reactivació.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="super1@example.com", password="Password123"
        )
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=10)

    def test_edifici_actiu_per_defecte(self):
        """Un edifici nou té actiu=True i dataDesactivacio=None."""
        self.assertTrue(self.edifici.actiu)
        self.assertIsNone(self.edifici.dataDesactivacio)
        self.assertEqual(self.edifici.motivDesactivacio, "")

    def test_manager_actius_exclou_desactivats(self):
        """Edifici.actius no retorna edificis amb actiu=False."""
        self.edifici.actiu = False
        self.edifici.save(update_fields=["actiu"])

        ids_actius = list(Edifici.actius.values_list("idEdifici", flat=True))
        self.assertNotIn(self.edifici.idEdifici, ids_actius)

        # Restaurar per no afectar altres tests
        self.edifici.actiu = True
        self.edifici.save(update_fields=["actiu"])

    def test_manager_objects_inclou_tots(self):
        """Edifici.objects retorna tots els edificis, inclosos els desactivats."""
        self.edifici.actiu = False
        self.edifici.save(update_fields=["actiu"])

        ids_tots = list(Edifici.objects.values_list("idEdifici", flat=True))
        self.assertIn(self.edifici.idEdifici, ids_tots)

        self.edifici.actiu = True
        self.edifici.save(update_fields=["actiu"])

    def test_desactivar_endpoint_posa_actiu_false(self):
        """POST /desactivar/?confirmat=true → actiu=False i dataDesactivacio assignada."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            {"motiu": "Test desactivació"},
            format="json",
            QUERY_STRING="confirmat=true",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.edifici.refresh_from_db()
        self.assertFalse(self.edifici.actiu)
        self.assertIsNotNone(self.edifici.dataDesactivacio)
        self.assertEqual(self.edifici.motivDesactivacio, "Test desactivació")

    def test_reactivar_endpoint_restaura_estat(self):
        """POST /reactivar/ → actiu=True i dataDesactivacio=None."""
        self.edifici.actiu = False
        self.edifici.dataDesactivacio = timezone.now()
        self.edifici.save(update_fields=["actiu", "dataDesactivacio"])

        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            reverse("edifici-reactivar", args=[self.edifici.idEdifici]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.edifici.refresh_from_db()
        self.assertTrue(self.edifici.actiu)
        self.assertIsNone(self.edifici.dataDesactivacio)

    def test_desactivar_edifici_ja_desactivat_retorna_400(self):
        self.edifici.actiu = False
        self.edifici.save(update_fields=["actiu"])

        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            QUERY_STRING="confirmat=true&inclou_desactivats=true",  # para que lo encuentre
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.edifici.actiu = True
        self.edifici.save(update_fields=["actiu"])

    def test_edifici_desactivat_no_apareix_al_list(self):
        """Un edifici desactivat no apareix a GET /edificis/ per cap rol."""
        self.edifici.actiu = False
        self.edifici.save(update_fields=["actiu"])

        for user in [self.admin]:
            with self.subTest(user=user.email):
                self.client.force_authenticate(user=user)
                response = self.client.get(reverse("edifici-list"))
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                ids = [item["idEdifici"] for item in response.data]
                self.assertNotIn(self.edifici.idEdifici, ids)

        self.edifici.actiu = True
        self.edifici.save(update_fields=["actiu"])

    def test_inclou_desactivats_nomes_per_superuser(self):
        """?inclou_desactivats=true retorna desactivats només per superuser, no per ADMIN."""
        self.edifici.actiu = False
        self.edifici.save(update_fields=["actiu"])

        # Superuser sí veu desactivats
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(reverse("edifici-list"), {"inclou_desactivats": "true"})
        ids = [item["idEdifici"] for item in response.data]
        self.assertIn(self.edifici.idEdifici, ids)

# ============================================================================
# DRY-RUN I VALIDACIÓ DE CONSISTÈNCIA (Task #170)
# ============================================================================

class EdificiDesactivacioDryRunTests(BaseTestData):
    """
    Comprova el comportament del dry-run (sense ?confirmat=true)
    i les advertències de consistència.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="super2@example.com", password="Password123"
        )
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner@example.com", RoleChoices.OWNER)
        cls.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=10)

    def test_dryrun_sense_confirmat_no_modifica_edifici(self):
        """POST /desactivar/ sense ?confirmat no canvia l'estat de l'edifici."""
        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            {"motiu": "Prova"},
            format="json",
        )
        self.edifici.refresh_from_db()
        self.assertTrue(self.edifici.actiu)  # No ha canviat

    def test_dryrun_retorna_estructura_correcta(self):
        """La resposta dry-run conté 'advertencies' i 'pot_desactivar'."""
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("advertencies", response.data)
        self.assertIn("pot_desactivar", response.data)
        self.assertIn("edifici_id", response.data)

    def test_advertencia_habitatges_amb_usuaris(self):
        """Dry-run detecta habitatges amb usuaris assignats."""
        Habitatge.objects.create(
            referenciaCadastral="HAB-DRY1", planta="1", porta="A",
            superficie=80, edifici=self.edifici, usuari=self.owner,
        )
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        advertencies_text = " ".join(response.data["advertencies"])
        self.assertIn("habitatge", advertencies_text.lower())

    def test_advertencia_millores_en_proces(self):
        """Dry-run detecta millores implementades en procés de validació."""
        millora = CatalegMillora.objects.create(
            nom="Millora test",
            categoria="Energia",
            descripcio="Millora de prova per validar advertències de desactivació.",
            costMinim=1000.0,
            costMaxim=1500.0,
            estalviEnergeticEstimat=5.0,
            impactePunts=5.0,
        )
        MilloraImplementada.objects.create(
            dataExecucio="2025-01-01",
            costReal=1000.0,
            estatValidacio=EstatValidacio.EN_REVISIO,
            millora=millora,
            edifici=self.edifici,
        )
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        advertencies_text = " ".join(response.data["advertencies"])
        self.assertIn("millora", advertencies_text.lower())

 # ============================================================================
# 6. US20 — PERMISOS DE DESACTIVACIÓ (Tasks #169 + #170)
# ============================================================================

class EdificiDesactivacioPermisosTests(BaseTestData):
    """
    Comprova que només el superuser pot desactivar/reactivar.
    Tots els altres rols han de rebre 403.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="super3@example.com", password="Password123"
        )
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant@example.com", RoleChoices.TENANT)
        cls.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=10)

    def test_rols_no_autoritzats_no_poden_desactivar(self):
        for user in [self.admin, self.owner, self.tenant]:
            with self.subTest(user=user.email):
                self.client.force_authenticate(user=user)
                response = self.client.post(
                    reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
                    QUERY_STRING="confirmat=true",
                )
                # OWNER/TENANT → 404 (no ven el edificio en su queryset)
                # ADMIN → 403 (lo ve pero no tiene permiso de sistema)
                self.assertIn(
                    response.status_code,
                    [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
                )

    def test_no_autenticat_no_pot_desactivar(self):
        """Usuari no autenticat rep 401 en intentar desactivar."""
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            QUERY_STRING="confirmat=true",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

# ============================================================================
# 7. US20 — REGISTRE D'AUDITORIA (Task #171)
# ============================================================================

class EdificiAuditLogTests(BaseTestData):
    """
    Comprova que EdificiAuditLog es crea correctament
    en desactivar, reactivar i que els camps són correctes.
    """

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="super4@example.com", password="Password123"
        )
        cls.admin = cls._create_user("admin@example.com", RoleChoices.ADMIN)
        cls.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=10)

    def test_desactivar_crea_audit_log(self):
        """Desactivar un edifici crea un registre EdificiAuditLog amb accio=DESACTIVAR."""
        logs_abans = EdificiAuditLog.objects.filter(
            edifici=self.edifici, accio="DESACTIVAR"
        ).count()

        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            {"motiu": "Auditoria test"},
            format="json",
            QUERY_STRING="confirmat=true",
        )

        logs_despres = EdificiAuditLog.objects.filter(
            edifici=self.edifici, accio="DESACTIVAR"
        ).count()
        self.assertEqual(logs_despres, logs_abans + 1)

    def test_audit_log_conte_camps_correctes(self):
        """El log de desactivació conté edifici_id_snapshot, usuari, motiu i camps_modificats."""
        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            {"motiu": "Verificació camps"},
            format="json",
            QUERY_STRING="confirmat=true",
        )

        log = EdificiAuditLog.objects.filter(
            edifici=self.edifici, accio="DESACTIVAR"
        ).latest("timestamp")

        self.assertEqual(log.edifici_id_snapshot, self.edifici.idEdifici)
        self.assertEqual(log.usuari, self.superuser)
        self.assertEqual(log.motiu, "Verificació camps")
        self.assertIn("actiu", log.camps_modificats)
        self.assertEqual(log.camps_modificats["actiu"], [True, False])

    def test_reactivar_crea_audit_log(self):
        """Reactivar un edifici crea un registre EdificiAuditLog amb accio=REACTIVAR."""
        self.edifici.actiu = False
        self.edifici.save(update_fields=["actiu"])

        logs_abans = EdificiAuditLog.objects.filter(
            edifici=self.edifici, accio="REACTIVAR"
        ).count()

        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            reverse("edifici-reactivar", args=[self.edifici.idEdifici]),
            format="json",
        )

        logs_despres = EdificiAuditLog.objects.filter(
            edifici=self.edifici, accio="REACTIVAR"
        ).count()
        self.assertEqual(logs_despres, logs_abans + 1)

    def test_dryrun_no_crea_audit_log(self):
        """El dry-run (sense ?confirmat=true) NO crea cap registre d'auditoria."""
        logs_abans = EdificiAuditLog.objects.filter(edifici=self.edifici).count()

        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            format="json",
            # sense QUERY_STRING confirmat=true
        )

        logs_despres = EdificiAuditLog.objects.filter(edifici=self.edifici).count()
        self.assertEqual(logs_despres, logs_abans)

    def test_audit_log_preserva_edifici_id_snapshot(self):
        """edifici_id_snapshot es guarda correctament per preservar-lo si l'edifici s'elimina."""
        self.client.force_authenticate(user=self.superuser)
        self.client.post(
            reverse("edifici-desactivar", args=[self.edifici.idEdifici]),
            format="json",
            QUERY_STRING="confirmat=true",
        )

        log = EdificiAuditLog.objects.filter(
            edifici=self.edifici, accio="DESACTIVAR"
        ).latest("timestamp")

        self.assertEqual(log.edifici_id_snapshot, self.edifici.idEdifici)

        # Restaurar
        self.edifici.actiu = True
        self.edifici.save(update_fields=["actiu"])

# ============================================================================
# 8. US15 — CLASSIFICACIÓ ENERGÈTICA ESTIMADA (Tasks #148, #149, #150, #151)
# ============================================================================

from apps.buildings.models import DadesEnergetiques, FontClassificacio, LletraEnergetica
from apps.buildings.scoring import calcular_classificacio_estimada, _score_a_lletra


class ClassificacioEstimadaUnitatTests(TestCase):
    """
    Tests unitaris purs sobre les funcions de scoring.
    No toquen la base de dades ni HTTP — molt ràpids.
    """

    # --- _score_a_lletra: tots els rangs ---

    def test_score_a_lletra_cobreix_tots_els_rangs(self):
        """Cada rang del mapeig retorna la lletra correcta."""
        casos = [
            (100,  LletraEnergetica.A),
            (85,   LletraEnergetica.A),  # llindar exacte A
            (84,   LletraEnergetica.B),
            (70,   LletraEnergetica.B),  # llindar exacte B
            (69,   LletraEnergetica.C),
            (55,   LletraEnergetica.C),  # llindar exacte C
            (54,   LletraEnergetica.D),
            (40,   LletraEnergetica.D),  # llindar exacte D
            (39,   LletraEnergetica.E),
            (25,   LletraEnergetica.E),  # llindar exacte E
            (24,   LletraEnergetica.F),
            (10,   LletraEnergetica.F),  # llindar exacte F
            (9,    LletraEnergetica.G),
            (0,    LletraEnergetica.G),  # llindar exacte G
        ]
        for score, lletra_esperada in casos:
            with self.subTest(score=score):
                self.assertEqual(_score_a_lletra(score), lletra_esperada)

    def test_score_negatiu_retorna_g(self):
        """Un score negatiu (dades molt dolentes) retorna G sense petar."""
        self.assertEqual(_score_a_lletra(-10), LletraEnergetica.G)


class ClassificacioEstimadaServeiTests(BaseTestData):
    """
    Tests d'integració sobre calcular_classificacio_estimada.
    Comproven els tres camins: oficial, estimada, insuficient.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_cls15@example.com", RoleChoices.ADMIN)
        cls.grup = GrupComparable.objects.create(
            idGrup=15, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=15)

    def _crea_habitatge(self, ref, dades=None):
        """Helper: crea un habitatge opcionalment amb DadesEnergetiques."""
        h = Habitatge.objects.create(
            referenciaCadastral=ref, planta="1", porta=ref[-1],
            superficie=80, edifici=self.edifici,
        )
        if dades:
            d = DadesEnergetiques.objects.create(**dades)
            h.dadesEnergetiques = d
            h.save(update_fields=["dadesEnergetiques"])
        return h

    def _dades_completes(self, consum=20.0, emissions=10.0, aillament=80.0, rehab=False, qualificacio=None):
        """Helper: retorna un dict vàlid per crear DadesEnergetiques."""
        return {
             "qualificacioGlobal": qualificacio,  # ← None per defecte, sense fallback a B
            "consumEnergiaPrimaria": consum,
            "consumEnergiaFinal": 15.0,
            "emissionsCO2": emissions,
            "costAnualEnergia": 500.0,
            "energiaCalefaccio": 5.0, "energiaRefrigeracio": 5.0,
            "energiaACS": 5.0, "energiaEnllumenament": 5.0,
            "emissionsCalefaccio": 2.0, "emissionsRefrigeracio": 2.0,
            "emissionsACS": 2.0, "emissionsEnllumenament": 2.0,
            "aillamentTermic": aillament,
            "valorFinestres": 1.5,
            "normativa": "CTE", "einaCertificacio": "CE3X",
            "motiuCertificacio": "Venda",
            "rehabilitacioEnergetica": rehab,
            "dataEntrada": "2024-01-01",
        }

    # --- Cas: sense habitatges ---

    def test_edifici_sense_habitatges_retorna_insuficient(self):
        """Un edifici sense habitatges retorna font=insuficient i classificacio=None."""
        # Usem un edifici nou buit per aïllar el test
        loc = Localitzacio.objects.create(
            carrer="Carrer buit", numero=99, codiPostal="08001",
            barri="Centre", latitud=41.0, longitud=2.0, zonaClimatica="C2",
        )
        edifici_buit = Edifici.objects.create(
            anyConstruccio=2000, tipologia="Residencial", superficieTotal=100,
            reglament="CTE", orientacioPrincipal="Sud",
            localitzacio=loc, administradorFinca=self.admin, grupComparable=self.grup,
        )
        resultat = calcular_classificacio_estimada(edifici_buit)
        self.assertIsNone(resultat["classificacio"])
        self.assertEqual(resultat["font"], FontClassificacio.INSUFICIENT)
        self.assertIn("habitatges", resultat["dades_insuficients"])

    # --- Cas: tots els habitatges amb qualificació oficial ---

    def test_tots_oficials_retorna_font_oficial(self):
        """Si tots els habitatges tenen qualificacioGlobal → font='oficial'."""
        self._crea_habitatge("REF-OF1", self._dades_completes(qualificacio=LletraEnergetica.B))
        self._crea_habitatge("REF-OF2", self._dades_completes(qualificacio=LletraEnergetica.D))

        resultat = calcular_classificacio_estimada(self.edifici)
        self.assertEqual(resultat["font"], FontClassificacio.OFICIAL)
        # Ha de retornar la pitjor lletra (D > B en l'escala)
        self.assertEqual(resultat["classificacio"], LletraEnergetica.D)

    def test_oficial_retorna_la_pitjor_lletra(self):
        """Amb lletres A, C, F → retorna F (la més desfavorable)."""
        loc = Localitzacio.objects.create(
            carrer="Carrer pitjor", numero=77, codiPostal="08001",
            barri="Centre", latitud=41.0, longitud=2.0, zonaClimatica="C2",
        )
        edifici = Edifici.objects.create(
            anyConstruccio=2005, tipologia="Residencial", superficieTotal=200,
            reglament="CTE", orientacioPrincipal="Nord",
            localitzacio=loc, administradorFinca=self.admin, grupComparable=self.grup,
        )
        for ref, lletra in [("REF-PIT1", LletraEnergetica.A),
                             ("REF-PIT2", LletraEnergetica.C),
                             ("REF-PIT3", LletraEnergetica.F)]:
            h = Habitatge.objects.create(
                referenciaCadastral=ref, planta="1", porta=ref[-1],
                superficie=80, edifici=edifici,
            )
            d = DadesEnergetiques.objects.create(**self._dades_completes(qualificacio=lletra))
            h.dadesEnergetiques = d
            h.save(update_fields=["dadesEnergetiques"])

        resultat = calcular_classificacio_estimada(edifici)
        self.assertEqual(resultat["classificacio"], LletraEnergetica.F)

    # --- Cas: estimació a partir del BHS ---

    def test_dades_suficients_retorna_font_estimada(self):
        """Habitatge amb dades crítiques cobertes → font='estimada' i lletra no nula."""
        self._crea_habitatge("REF-EST1", self._dades_completes(consum=20.0, emissions=10.0, aillament=80.0))

        resultat = calcular_classificacio_estimada(self.edifici)
        self.assertEqual(resultat["font"], FontClassificacio.ESTIMADA)
        self.assertIsNotNone(resultat["classificacio"])
        self.assertIn(resultat["classificacio"], LletraEnergetica.values)

    def test_rehabilitacio_millora_la_classificacio(self):
        """Edifici amb rehabilitacioEnergetica=True obté millor score que sense."""
        loc1 = Localitzacio.objects.create(
            carrer="Carrer rehab", numero=11, codiPostal="08001",
            barri="Centre", latitud=41.0, longitud=2.0, zonaClimatica="C2",
        )
        loc2 = Localitzacio.objects.create(
            carrer="Carrer sense rehab", numero=12, codiPostal="08001",
            barri="Centre", latitud=41.0, longitud=2.0, zonaClimatica="C2",
        )
        edifici_rehab = Edifici.objects.create(
            anyConstruccio=2000, tipologia="Residencial", superficieTotal=100,
            reglament="CTE", orientacioPrincipal="Sud",
            localitzacio=loc1, administradorFinca=self.admin, grupComparable=self.grup,
        )
        edifici_sense = Edifici.objects.create(
            anyConstruccio=2000, tipologia="Residencial", superficieTotal=100,
            reglament="CTE", orientacioPrincipal="Sud",
            localitzacio=loc2, administradorFinca=self.admin, grupComparable=self.grup,
        )
        for edifici, rehab, ref in [
            (edifici_rehab, True,  "REF-REHAB1"),
            (edifici_sense, False, "REF-SENSE1"),
        ]:
            h = Habitatge.objects.create(
                referenciaCadastral=ref, planta="1", porta="A",
                superficie=80, edifici=edifici,
            )
            d = DadesEnergetiques.objects.create(
                **self._dades_completes(consum=20.0, emissions=10.0, aillament=50.0, rehab=rehab)
            )
            h.dadesEnergetiques = d
            h.save(update_fields=["dadesEnergetiques"])

        ordre = list(LletraEnergetica.values)  # [A, B, C, D, E, F, G]
        res_rehab = calcular_classificacio_estimada(edifici_rehab)
        res_sense = calcular_classificacio_estimada(edifici_sense)

        idx_rehab = ordre.index(res_rehab["classificacio"])
        idx_sense = ordre.index(res_sense["classificacio"])
        # índex més baix = lletra millor (A=0, G=6)
        self.assertLessEqual(idx_rehab, idx_sense)

    # --- Cas: dades insuficients ---

    def test_habitatge_sense_dades_energetiques_retorna_insuficient(self):
        """Habitatge sense DadesEnergetiques → font='insuficient'."""
        self._crea_habitatge("REF-NDE1")  # sense dades

        resultat = calcular_classificacio_estimada(self.edifici)
        self.assertEqual(resultat["font"], FontClassificacio.INSUFICIENT)
        self.assertIsNone(resultat["classificacio"])
        self.assertIn("dades_insuficients", resultat)

    def test_camp_critic_a_zero_retorna_insuficient(self):
        """consumEnergiaPrimaria=0 es considera dada insuficient."""
        self._crea_habitatge(
            "REF-ZERO1",
            self._dades_completes(consum=0.0, emissions=10.0)  # consum a zero = insuficient
        )
        resultat = calcular_classificacio_estimada(self.edifici)
        self.assertEqual(resultat["font"], FontClassificacio.INSUFICIENT)
        self.assertIn("consumEnergiaPrimaria", resultat["dades_insuficients"])

    def test_informa_quins_camps_falten(self):
        """El resultat indica explícitament quins camps crítics falten."""
        self._crea_habitatge(
            "REF-MISS1",
            self._dades_completes(consum=0.0, emissions=0.0)
        )
        resultat = calcular_classificacio_estimada(self.edifici)
        self.assertIn("consumEnergiaPrimaria", resultat["dades_insuficients"])
        self.assertIn("emissionsCO2", resultat["dades_insuficients"])

    # --- Cas: cobertura parcial (alguns habitatges amb dades, altres sense) ---

    def test_cobertura_parcial_estima_amb_els_que_tenen_dades(self):
        """
        Si alguns habitatges no tenen dades però d'altres sí,
        el sistema estima a partir dels que en tenen i ho indica al detall.
        """
        self._crea_habitatge("REF-PAR1", self._dades_completes(consum=20.0, emissions=10.0))
        self._crea_habitatge("REF-PAR2")  # sense dades

        resultat = calcular_classificacio_estimada(self.edifici)
        self.assertEqual(resultat["font"], FontClassificacio.ESTIMADA)
        self.assertIsNotNone(resultat["classificacio"])
        self.assertIn("Atenció", resultat["detall"])

    # --- Comprovació del camp 'detall' ---

    def test_detall_sempre_present_i_no_buit(self):
        """El camp 'detall' sempre és present i no és una cadena buida."""
        casos = [
            {},                                                         # sense habitatges
            {"REF-DET1": None},                                         # sense dades
            {"REF-DET2": self._dades_completes(consum=20.0, emissions=10.0)},  # amb dades
        ]
        for habitatges in casos:
            with self.subTest(habitatges=list(habitatges.keys())):
                # Edifici fresc per cada subtest
                loc = Localitzacio.objects.create(
                    carrer=f"Carrer detall {len(habitatges)}", numero=50 + len(habitatges),
                    codiPostal="08001", barri="Centre",
                    latitud=41.0, longitud=2.0, zonaClimatica="C2",
                )
                e = Edifici.objects.create(
                    anyConstruccio=2000, tipologia="Residencial", superficieTotal=100,
                    reglament="CTE", orientacioPrincipal="Sud",
                    localitzacio=loc, administradorFinca=self.admin, grupComparable=self.grup,
                )
                for ref, dades in habitatges.items():
                    h = Habitatge.objects.create(
                        referenciaCadastral=ref, planta="1", porta="A",
                        superficie=80, edifici=e,
                    )
                    if dades:
                        d = DadesEnergetiques.objects.create(**dades)
                        h.dadesEnergetiques = d
                        h.save(update_fields=["dadesEnergetiques"])

                resultat = calcular_classificacio_estimada(e)
                self.assertIn("detall", resultat)
                self.assertTrue(resultat["detall"])  # no buit


class ClassificacioEstimadaSerializerTests(BaseTestData):
    """
    US15 — Task #150: comprova que el serializer exposa correctament
    el camp classificacio_energetica a la fitxa de l'edifici.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_ser15@example.com", RoleChoices.ADMIN)
        cls.grup = GrupComparable.objects.create(
            idGrup=16, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=16)

    def test_detail_endpoint_inclou_classificacio_energetica(self):
        """GET /edificis/{id}/ inclou el camp classificacio_energetica."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici.idEdifici]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("classificacio_energetica", response.data)

    def test_classificacio_energetica_te_estructura_correcta(self):
        """El camp classificacio_energetica té les claus: lletra, font, etiqueta, detall."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici.idEdifici]))
        camp = response.data["classificacio_energetica"]
        for clau in ("lletra", "font", "etiqueta", "detall"):
            with self.subTest(clau=clau):
                self.assertIn(clau, camp)

    def test_etiqueta_marcada_com_estimada_o_insuficient(self):
        """
        Sense certificats oficials, l'etiqueta ha de ser 'estimada' o 'insuficient',
        mai 'oficial'. Garanteix que la UI no enganya l'usuari.
        """
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici.idEdifici]))
        font = response.data["classificacio_energetica"]["font"]
        self.assertIn(font, [FontClassificacio.ESTIMADA, FontClassificacio.INSUFICIENT])
        self.assertNotEqual(font, FontClassificacio.OFICIAL)

# ============================================================================
# US13 — Importació open data CEE
# ============================================================================
import csv, io, tempfile, os
from unittest.mock import patch
from apps.buildings.models import (
    ImportacioLog, ImportacioIncidencia,
    DadesEnergetiquesOpenData, TipusEdificiOpenData, FontClassificacio,
)
from apps.buildings.management.commands.importar_cee import (
    _clau_adreca, _construir_edifici, _construir_dades_energetiques,
    _llegir_chunk, _f, _bool_si,
)
from apps.buildings.services.open_data_tipologia import map_tipus_edifici


def _csv_amb_files(files: list[dict]) -> str:
    """Genera un fitxer CSV temporal amb les files donades i retorna la seva ruta."""
    if not files:
        return ''
    fieldnames = list(files[0].keys())
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.csv', delete=False,
        encoding='utf-8-sig', newline=''
    )
    writer = csv.DictWriter(tmp, fieldnames=fieldnames, delimiter=',')
    writer.writeheader()
    writer.writerows(files)
    tmp.close()
    return tmp.name


def _fila_base(**kwargs) -> dict:
    """Fila mínima vàlida del CSV CEE. Sobreescriu camps amb kwargs."""
    base = {
        'NUM_CAS': 'TEST001',
        'ADREÇA': 'Carrer Test',
        'NUMERO': '10',
        'ESCALA': '',
        'PIS': '1',
        'PORTA': 'A',
        'CODI_POSTAL': '08001',
        'POBLACIO': 'Barcelona',
        'COMARCA': 'Barcelonès',
        'NOM_PROVINCIA': 'Barcelona',
        'CODI_POBLACIO': '08019',
        'CODI_COMARCA': '13',
        'CODI_PROVINCIA': '08',
        'REFERENCIA CADASTRAL': '1234567AA1234A0001AA',
        'ZONA CLIMATICA': 'C2',
        'METRES_CADASTRE': '80,5',
        'ANY_CONSTRUCCIO': '1990',
        'US_EDIFICI': "Bloc d'habitatges plurifamiliar",
        "Qualificació de consum d'energia primaria no renovable": 'D',
        'Energia primària no renovable': '150,5',
        'Qualificacio d\'emissions de CO2': 'D',
        'Emissions de CO2': '30,2',
        'Consum d\'energia final': '100,0',
        'Cost anual aproximat d\'energia per habitatge': '800,0',
        'VEHICLE ELECTRIC': 'NO',
        'SOLAR TERMICA': 'NO',
        'SOLAR FOTOVOLTAICA': 'NO',
        'SISTEMA BIOMASSA': 'NO',
        'XARXA DISTRICTE': 'NO',
        'ENERGIA GEOTERMICA': 'NO',
        'INFORME_INS_TECNICA_EDIFICI': '',
        'Eina de certificacio': 'CE3X',
        'VALOR AILLAMENTS': '0,5',
        'VALOR FINESTRES': '2,5',
        'Motiu de la certificacio': 'Lloguer',
        'VALOR AILLAMENTS CTE': '0,49',
        'VALOR FINESTRES CTE': '2,1',
        'UTM_X': '',
        'UTM_Y': '',
        'Normativa construcció': 'NBE-CT-79',
        'Tipus Tramit': 'Edificis existents',
        'TIPUS_TERCIARI': '',
        'Qualificació emissions calefacció': 'D',
        'Emissions calefacció': '25,0',
        'Qualificació emissions refrigeració': 'A',
        'Emissions refrigeració': '1,5',
        'Qualificació emissions ACS': 'E',
        'Emissions ACS': '3,7',
        'Qualificació emissions enllumenament': '',
        'Emissions enllumenament': '0',
        'Qualificació energia calefacció': 'D',
        'Energia calefacció': '110,0',
        'Qualificació energia refrigeració': 'A',
        'Energia refrigeració': '5,0',
        'Qualificació energia ACS': 'E',
        'Energia ACS': '35,5',
        'Qualificació energia enllumenament': '',
        'Energia enllumenament': '0',
        'Qualificació energia calefacció demanda': 'E',
        'Energia calefacció demanda': '90,0',
        'Qualificació energia refrigeració demanda': 'B',
        'Energia refrigeració demanda': '8,0',
        'VENTILACIO US RESIDENCIAL': '0,63',
        'LONGITUD': '2,15899',
        'LATITUD': '41,38879',
        'GEOREFERÈNCIA': '',
        'REHABILITACIO_ENERGETICA': 'No',
        'ACTUACIONS_REHABILITACIO': '',
        'DATA_ENTRADA': '15/03/2020',
    }
    base.update(kwargs)
    return base


class OpenDataTipologiaTests(TestCase):
    """US13 #138 — map_tipus_edifici: mapatge de valors del CSV a TipusEdificiOpenData."""

    def test_bloc_pisos_catala(self):
        self.assertEqual(
            map_tipus_edifici("Bloc d'habitatges plurifamiliar"),
            TipusEdificiOpenData.BLOC_PISOS
        )

    def test_bloc_pisos_castella(self):
        self.assertEqual(
            map_tipus_edifici("Bloque de viviendas"),
            TipusEdificiOpenData.BLOC_PISOS
        )

    def test_unifamiliar_catala(self):
        self.assertEqual(
            map_tipus_edifici("Habitatge unifamiliar"),
            TipusEdificiOpenData.UNIFAMILIAR
        )

    def test_habitatge_bloc(self):
        self.assertEqual(
            map_tipus_edifici("Habitatge individual en bloc d'habitatges"),
            TipusEdificiOpenData.HABITATGE_BLOC
        )

    def test_terciari(self):
        self.assertEqual(
            map_tipus_edifici("Terciari"),
            TipusEdificiOpenData.TERCIARI
        )

    def test_valor_desconegut_retorna_desconegut(self):
        self.assertEqual(
            map_tipus_edifici("Valor que no existeix"),
            TipusEdificiOpenData.DESCONEGUT
        )

    def test_string_buit_retorna_desconegut(self):
        self.assertEqual(map_tipus_edifici(""), TipusEdificiOpenData.DESCONEGUT)

    def test_none_retorna_desconegut(self):
        self.assertEqual(map_tipus_edifici(None), TipusEdificiOpenData.DESCONEGUT)

    def test_espais_extra_no_trenquen(self):
        """Valors amb espais al voltant es mapegen correctament."""
        self.assertEqual(
            map_tipus_edifici("  Terciari  "),
            TipusEdificiOpenData.TERCIARI
        )


class OpenDataHelpersTests(TestCase):
    """US13 — Funcions helpers del command: _f, _bool_si, _clau_adreca."""

    def test_f_converteix_coma_decimal(self):
        fila = {'METRES_CADASTRE': '80,5'}
        self.assertAlmostEqual(_f(fila, 'METRES_CADASTRE'), 80.5)

    def test_f_camp_buit_retorna_zero(self):
        fila = {'METRES_CADASTRE': ''}
        self.assertEqual(_f(fila, 'METRES_CADASTRE'), 0.0)

    def test_f_camp_absent_retorna_zero(self):
        self.assertEqual(_f({}, 'CAMP_INEXISTENT'), 0.0)

    def test_bool_si_positiu(self):
        self.assertTrue(_bool_si({'SOLAR TERMICA': 'SI'}, 'SOLAR TERMICA'))
        self.assertTrue(_bool_si({'SOLAR TERMICA': 'si'}, 'SOLAR TERMICA'))

    def test_bool_si_negatiu(self):
        self.assertFalse(_bool_si({'SOLAR TERMICA': 'NO'}, 'SOLAR TERMICA'))
        self.assertFalse(_bool_si({'SOLAR TERMICA': ''}, 'SOLAR TERMICA'))

    def test_clau_adreca_normalitza_majuscules(self):
        fila = {'ADREÇA': 'carrer test', 'NUMERO': '10', 'CODI_POSTAL': '08001'}
        clau = _clau_adreca(fila)
        self.assertEqual(clau[0], 'CARRER TEST')

    def test_clau_adreca_camps_buits(self):
        """Files sense adreça no llancen excepció."""
        clau = _clau_adreca({})
        self.assertEqual(clau, ('', '', ''))


class ConstruirEdificiTests(TestCase):
    """US13 #139 — _construir_edifici: mapatge de camps CSV a model Edifici."""

    def test_tipologia_open_data_assignada(self):
        grup = [_fila_base()]
        edifici = _construir_edifici(grup)
        self.assertEqual(edifici.tipologia_open_data, TipusEdificiOpenData.BLOC_PISOS)

    def test_terciari_mapeja_a_comercial(self):
        grup = [_fila_base(**{'US_EDIFICI': 'Terciari'})]
        edifici = _construir_edifici(grup)
        self.assertEqual(edifici.tipologia, 'Comercial')

    def test_residencial_mapeja_a_residencial(self):
        grup = [_fila_base()]
        edifici = _construir_edifici(grup)
        self.assertEqual(edifici.tipologia, 'Residencial')

    def test_any_construccio_assignat(self):
        grup = [_fila_base(**{'ANY_CONSTRUCCIO': '1975'})]
        edifici = _construir_edifici(grup)
        self.assertEqual(edifici.anyConstruccio, 1975)

    def test_any_construccio_invalid_posa_zero(self):
        grup = [_fila_base(**{'ANY_CONSTRUCCIO': 'desconegut'})]
        edifici = _construir_edifici(grup)
        self.assertEqual(edifici.anyConstruccio, 0)

    def test_superficie_converteix_coma(self):
        grup = [_fila_base(**{'METRES_CADASTRE': '120,75'})]
        edifici = _construir_edifici(grup)
        self.assertAlmostEqual(edifici.superficieTotal, 120.75)

    def test_font_open_data_sempre_true(self):
        edifici = _construir_edifici([_fila_base()])
        self.assertTrue(edifici.font_open_data)

    def test_num_cas_origen_assignat(self):
        grup = [_fila_base(**{'NUM_CAS': 'ABC123'})]
        edifici = _construir_edifici(grup)
        self.assertEqual(edifici.num_cas_origen, 'ABC123')


class ConstruirDadesEnergetiquesTests(TestCase):
    """US13 #139 — _construir_dades_energetiques: mapatge de camps energètics."""

    def test_qualificacio_global_assignada(self):
        grup = [_fila_base()]
        dades = _construir_dades_energetiques(grup)
        self.assertEqual(dades.qualificacioGlobal, 'D')

    def test_consum_energia_primaria_convertit(self):
        grup = [_fila_base(**{'Energia primària no renovable': '200,5'})]
        dades = _construir_dades_energetiques(grup)
        self.assertAlmostEqual(dades.consumEnergiaPrimaria, 200.5)

    def test_solar_termica_si(self):
        grup = [_fila_base(**{'SOLAR TERMICA': 'SI'})]
        dades = _construir_dades_energetiques(grup)
        self.assertTrue(dades.teSolarTermica)

    def test_solar_termica_no(self):
        grup = [_fila_base(**{'SOLAR TERMICA': 'NO'})]
        dades = _construir_dades_energetiques(grup)
        self.assertFalse(dades.teSolarTermica)

    def test_rehabilitacio_energetica_si(self):
        grup = [_fila_base(**{'REHABILITACIO_ENERGETICA': 'Sí'})]
        dades = _construir_dades_energetiques(grup)
        self.assertTrue(dades.rehabilitacioEnergetica)

    def test_data_entrada_parsejada(self):
        grup = [_fila_base(**{'DATA_ENTRADA': '15/03/2020'})]
        dades = _construir_dades_energetiques(grup)
        # Agafem els primers 10 chars — el command guarda com a string YYYY-MM-DD o DD/MM/YYYY
        self.assertIsNotNone(dades.dataEntrada)


class LlegirChunkTests(TestCase):
    """US13 — _llegir_chunk: lectura parcial del CSV per offset i limit."""

    def setUp(self):
        self.files = [
            _fila_base(**{'ADREÇA': f'Carrer {i}', 'NUMERO': str(i), 'NUM_CAS': f'C{i:03d}'})
            for i in range(1, 21)  # 20 adreces úniques
        ]
        self.csv_path = _csv_amb_files(self.files)

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.unlink(self.csv_path)

    def test_limit_retorna_nombre_correcte_dedifici(self):
        files = _llegir_chunk(self.csv_path, offset_edificis=0, limit_edificis=5)
        adreces = {_clau_adreca(f) for f in files}
        self.assertEqual(len(adreces), 5)

    def test_offset_salta_primers_edificis(self):
        chunk_a = _llegir_chunk(self.csv_path, offset_edificis=0, limit_edificis=5)
        chunk_b = _llegir_chunk(self.csv_path, offset_edificis=5, limit_edificis=5)
        adreces_a = {_clau_adreca(f) for f in chunk_a}
        adreces_b = {_clau_adreca(f) for f in chunk_b}
        self.assertTrue(adreces_a.isdisjoint(adreces_b), "Els chunks no haurien de solapar-se")

    def test_limit_none_retorna_tot(self):
        files = _llegir_chunk(self.csv_path, offset_edificis=0, limit_edificis=None)
        adreces = {_clau_adreca(f) for f in files}
        self.assertEqual(len(adreces), 20)

    def test_offset_major_que_total_retorna_buit(self):
        files = _llegir_chunk(self.csv_path, offset_edificis=999, limit_edificis=10)
        self.assertEqual(files, [])


class ImportarCeeCommandTests(TestCase):
    """US13 #138 #139 #140 — Command complet: integració amb BD."""

    def setUp(self):
        self.files_csv = [
            _fila_base(**{
                'ADREÇA': 'Carrer Integració', 'NUMERO': '1',
                'NUM_CAS': 'INT001', 'US_EDIFICI': "Bloc d'habitatges plurifamiliar",
            }),
            _fila_base(**{
                'ADREÇA': 'Carrer Integració', 'NUMERO': '2',
                'NUM_CAS': 'INT002', 'US_EDIFICI': 'Habitatge unifamiliar',
            }),
        ]
        self.csv_path = _csv_amb_files(self.files_csv)

    def tearDown(self):
        if os.path.exists(self.csv_path):
            os.unlink(self.csv_path)

    def _run_command(self, **kwargs):
        from django.core.management import call_command
        call_command('importar_cee', self.csv_path, **kwargs)

    def test_crea_edificis_i_localitzacions(self):
        """Sense --dry-run es creen Edifici i Localitzacio a la BD."""
        self._run_command(limit=2)
        self.assertEqual(Edifici.objects.filter(font_open_data=True).count(), 2)

    def test_crea_dades_energetiques_opendata(self):
        """Cada edifici importat té DadesEnergetiquesOpenData associades."""
        self._run_command(limit=2)
        edificis = Edifici.objects.filter(font_open_data=True)
        for e in edificis:
            self.assertTrue(
                hasattr(e, 'dades_energetiques_opendata'),
                f"Edifici {e.idEdifici} no té DadesEnergetiquesOpenData"
            )

    def test_dry_run_no_escriu_a_bd(self):
        """--dry-run no crea cap Edifici a la BD."""
        self._run_command(limit=2, dry_run=True)
        self.assertEqual(Edifici.objects.filter(font_open_data=True).count(), 0)

    def test_log_creat_amb_resum_correcte(self):
        """ImportacioLog registra edificis_creats i completada=True."""
        self._run_command(limit=2)
        log = ImportacioLog.objects.latest('data_inici')
        self.assertTrue(log.completada)
        self.assertEqual(log.edificis_creats, 2)
        self.assertEqual(log.files_error, 0)

    def test_limit_respectat(self):
        """--limit 1 crea exactament 1 edifici."""
        self._run_command(limit=1)
        self.assertEqual(Edifici.objects.filter(font_open_data=True).count(), 1)

    def test_classificacio_font_oficial_per_opendata(self):
        """
        Edificis importats de l'open data (CEE oficial) tenen
        classificacioFont='oficial', no 'estimada'.
        """
        self._run_command(limit=2)
        for e in Edifici.objects.filter(font_open_data=True):
            self.assertEqual(
                e.classificacioFont, FontClassificacio.OFICIAL,
                f"Edifici {e.idEdifici}: esperava 'oficial', obtingut '{e.classificacioFont}'"
            )

    def test_incidencia_registrada_per_fila_invalida(self):
        """
        Una fila amb LATITUD invàlida genera una ImportacioIncidencia
        i no trenca la importació de la resta.
        """
        files_amb_error = self.files_csv + [
            _fila_base(**{
                'ADREÇA': 'Carrer Error', 'NUMERO': '99',
                'NUM_CAS': 'ERR001', 'LATITUD': 'no-es-un-numero',
            })
        ]
        csv_path_error = _csv_amb_files(files_amb_error)
        try:
            from django.core.management import call_command
            call_command('importar_cee', csv_path_error, limit=3)
            log = ImportacioLog.objects.latest('data_inici')
            self.assertGreater(log.files_error, 0)
            self.assertTrue(
                ImportacioIncidencia.objects.filter(importacio=log).exists()
            )
        finally:
            os.unlink(csv_path_error)


class OpenDataClassificacioFontTests(TestCase):
    """
    US13 — Verifica que la lògica de font és correcta:
    open data → oficial, habitatges usuari → estimada.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.accounts.models import RoleChoices
        cls.admin = User.objects.create_user(
            email='admin_od@example.com', password='Password123', first_name='Admin'
        )
        cls.admin.profile.role = RoleChoices.ADMIN
        cls.admin.profile.save()

        cls.grup = GrupComparable.objects.create(
            idGrup=99, zonaClimatica='C2', tipologia='Residencial', rangSuperficie='0-500'
        )
        loc = Localitzacio.objects.create(
            carrer='Carrer Font', numero=1, codiPostal='08001',
            barri='', latitud=41.0, longitud=2.0, zonaClimatica='C2',
        )
        cls.edifici_od = Edifici.objects.create(
            anyConstruccio=1990, tipologia='Residencial', superficieTotal=200,
            reglament='CTE', orientacioPrincipal='Sud',
            localitzacio=loc, administradorFinca=cls.admin, grupComparable=cls.grup,
            font_open_data=True,
            classificacioFont=FontClassificacio.OFICIAL,
            classificacioEstimada='D',
        )
        DadesEnergetiquesOpenData.objects.create(
            edifici=cls.edifici_od,
            qualificacioGlobal='D',
            consumEnergiaPrimaria=150.0,
            emissionsCO2=30.0,
        )

    def test_edifici_opendata_te_font_oficial(self):
        """Edifici seeded des del CEE oficial té classificacioFont='oficial'."""
        self.assertEqual(self.edifici_od.classificacioFont, FontClassificacio.OFICIAL)

    def test_edifici_sense_opendata_ni_habitatges_es_insuficient(self):
        """Edifici buit sense dades té font='insuficient'."""
        from apps.buildings.scoring import calcular_classificacio_estimada
        loc = Localitzacio.objects.create(
            carrer='Carrer Buit', numero=2, codiPostal='08001',
            barri='', latitud=41.0, longitud=2.0, zonaClimatica='C2',
        )
        e = Edifici.objects.create(
            anyConstruccio=2000, tipologia='Residencial', superficieTotal=100,
            reglament='CTE', orientacioPrincipal='Sud',
            localitzacio=loc, administradorFinca=self.admin, grupComparable=self.grup,
        )
        resultat = calcular_classificacio_estimada(e)
        self.assertEqual(resultat['font'], FontClassificacio.INSUFICIENT)

# ============================================================================
# EPIC 4 — PROVES UNITÀRIES DEL MOTOR DE SIMULACIÓ
# ============================================================================
class MotorSimulacioUnitTests(BaseTestData):
    """
    Proves unitàries per validar la matemàtica del motor de simulació.
    """

    def setUp(self):
        super().setUp()

        self.admin = self._create_user("admin_motor@example.com", RoleChoices.ADMIN)
        self.grup = GrupComparable.objects.create(
            idGrup=99, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-100"
        )
        self.edifici = self._create_edifici(self.admin, self.grup, numero=1)

        self.edifici.superficieTotal = 1000.0
        self.edifici.puntuacioBase = 50.0
        self.edifici.save()
        
        self.millora_sate = CatalegMillora.objects.create(
            nom="Aïllament SATE",
            categoria="Envolupant",
            costMinim=40.0,
            costMaxim=60.0,
            estalviEnergeticEstimat=20.0,
            impactePunts=15.0, 
            nivellConfianca="alt",
            unitatBase="m2",
            parametresBase={
                "impactes": {
                    "reduccio_demanda_calefaccio": 0.30,
                    "reduccio_consum_electric_total_tipica": 0.10
                }
            }
        )

    def test_clamp_function_respecta_els_limits(self):
        """Prova unitària d'una funció matemàtica aïllada de l'engine."""
        self.assertEqual(clamp(150, 0, 100), 100)
        self.assertEqual(clamp(-10, 0, 100), 0)
        self.assertEqual(clamp(50, 0, 100), 50)

    def test_simular_millores_calcula_be_el_delta(self):
        """
        Validem que el motor rep l'input, fa les matemàtiques i retorna
        l'arbre de dades correcte (abans, despres, delta).
        """
        input_motor = [{
            "millora": self.millora_sate,
            "quantitat": 100,
            "coberturaPercent": 100
        }]

        resultat = simular_millores(self.edifici, input_motor)

        self.assertIn("abans", resultat)
        self.assertIn("despres", resultat)
        self.assertIn("delta", resultat)
        self.assertIn("items", resultat)
        
        self.assertEqual(resultat["delta"]["incrementScore"], 15.0)
        
        self.assertEqual(resultat["despres"]["score"], 65.0)
        
        self.assertGreater(resultat["delta"]["reduccioConsumKwhAny"], 0)
        self.assertGreater(resultat["delta"]["estalviAnualEstimatiu"], 0)

    def test_simular_plaques_solars_calcula_produccio(self):
        """Cobreix les branques de l'engine dedicades a la fotovoltaica (KWp)."""
        millora_fv = CatalegMillora.objects.create(
            nom="Plaques FV",
            categoria="Energia",
            costMinim=4000.0,
            costMaxim=6000.0,
            estalviEnergeticEstimat=40.0,
            impactePunts=20.0,
            unitatBase="KWp",
            parametresBase={
                "impactes": {
                    "produccio_kwh_per_kwp_any": 1500,
                    "factor_perdues_sistema": 0.1,
                    "autoconsum_directe_base": 0.6
                }
            }
        )
        
        resultat = simular_millores(self.edifici, [{"millora": millora_fv, "quantitat": 3, "coberturaPercent": 100}])
        
        self.assertGreater(resultat["items"][0]["produccioFotovoltaicaKwhAny"], 0)
        self.assertGreater(resultat["delta"]["reduccioConsumKwhAny"], 0)

    def test_simular_aerotermia_calcula_emissions(self):
        """Cobreix les branques de l'engine dedicades a la climatització i reducció directa d'emissions."""
        millora_clima = CatalegMillora.objects.create(
            nom="Aerotèrmia Alta Eficiència",
            categoria="Climatització",
            costMinim=8000.0,
            costMaxim=12000.0,
            estalviEnergeticEstimat=60.0,
            impactePunts=25.0,
            unitatBase="habitatge",
            parametresBase={
                "impactes": {
                    "reduccio_emissions_calefaccio": 0.60,
                    "reduccio_demanda_calefaccio": 0.20
                }
            }
        )
        
        resultat = simular_millores(self.edifici, [{"millora": millora_clima, "quantitat": 2, "coberturaPercent": 100}])
        
        self.assertGreater(resultat["delta"]["reduccioEmissionsKgCO2Any"], 0)
        self.assertEqual(resultat["despres"]["score"], 75.0)

    def test_simular_edge_cases_i_altres_categories(self):
        """
        Test 'escombra' per netejar les línies de codi (coverage) 
        d'altres tipologies i casos extrems de l'engine.
        """

        resultat_buit = simular_millores(self.edifici, [])
        self.assertEqual(resultat_buit["delta"]["incrementScore"], 0.0)
        self.assertEqual(resultat_buit["delta"]["reduccioConsumKwhAny"], 0.0)
        
        millora_led = CatalegMillora.objects.create(
            nom="Llums LED", categoria="Il·luminació", 
            costMinim=10, costMaxim=20, estalviEnergeticEstimat=5, 
            impactePunts=2, unitatBase="m2",
            parametresBase={"impactes": {"reduccio_consum_electric_total_tipica": 0.15}}
        )
        
        millora_finestres = CatalegMillora.objects.create(
            nom="Finestres PVC", categoria="Envolupant", 
            costMinim=200, costMaxim=300, estalviEnergeticEstimat=15, 
            impactePunts=10, unitatBase="m2",
            parametresBase={
                "impactes": {
                    "reduccio_demanda_calefaccio": 0.15, 
                    "reduccio_demanda_refrigeracio": 0.10
                }
            }
        )
        
        input_motor = [
            {"millora": millora_led, "quantitat": 100, "coberturaPercent": 50},
            {"millora": millora_finestres, "quantitat": 20, "coberturaPercent": 100}
        ]
        
        resultat = simular_millores(self.edifici, input_motor)
        
        self.assertGreater(resultat["delta"]["costTotalEstimat"], 0)
        self.assertGreater(resultat["delta"]["estalviAnualEstimatiu"], 0)
        self.assertGreater(resultat["despres"]["score"], self.edifici.puntuacioBase)
        self.assertEqual(len(resultat["items"]), 2)


class MotorSimulacioEspecificUnitTests(BaseTestData):
    def setUp(self):
        super().setUp()
        
        self.admin = self._create_user("admin_sim_especific@example.com", RoleChoices.ADMIN)
        self.grup = GrupComparable.objects.create(
            idGrup=888, # Un ID diferent per evitar xocs
            zonaClimatica="C2", 
            tipologia="Residencial", 
            rangSuperficie="0-100"
        )
        
        self.edifici = self._create_edifici(self.admin, self.grup, numero=88)

        self.edifici.superficieTotal = 1000.0
        self.edifici.puntuacioBase = 50.0
        self.edifici.save()

    def test_simulacio_fotovoltaica_activa_produccio(self):
        """Prova que la clau 'produccio_kwh_per_kwp_any' activa la lògica de renovables"""
        millora_fv = CatalegMillora.objects.create(
            idMillora=9001,
            nom="Plaques Solars al Terrat",
            categoria="renovables",
            unitatBase=UnitatBaseMillora.KWP,
            parametresBase={
                "impactes": {
                    "produccio_kwh_per_kwp_any": 1500,
                    "factor_perdues_sistema": 0.15,
                    "factor_ombra_base": 1.0,
                    "autoconsum_directe_base": 0.50
                }
            }
        )
        
        items = [{"millora": millora_fv, "quantitat": 10, "coberturaPercent": 100}]
        resultat = simular_millores(self.edifici, items)
        
        self.assertGreater(resultat["delta"]["reduccioConsumKwhAny"], 0)
        self.assertEqual(resultat["items"][0]["produccioFotovoltaicaKwhAny"], 1500 * 10 * 0.85)

    def test_simulacio_aerotermia_activa_reduccio_emissions(self):
        """Prova que la clau 'reduccio_emissions_calefaccio' activa la lògica de climatització"""
        millora_aero = CatalegMillora.objects.create(
            idMillora=9002,
            nom="Aerotèrmia Centralitzada",
            categoria="climatitzacio",
            unitatBase=UnitatBaseMillora.EDIFICI,
            parametresBase={
                "impactes": {
                    "reduccio_emissions_calefaccio": 0.75,
                    "co2_factor_kg_per_kwh_estalviat": 0.10 # Per forçar un factor diferent
                }
            }
        )
        
        items = [{"millora": millora_aero, "quantitat": 1, "coberturaPercent": 100}]
        resultat = simular_millores(self.edifici, items)
        
        self.assertGreater(resultat["delta"]["reduccioEmissionsKgCO2Any"], 0)

    def test_simulacio_envolupant_i_infiltracions(self):
        """Prova el repartiment de reducció sobre calefacció/refrigeració i infiltracions"""
        millora_sate = CatalegMillora.objects.create(
            idMillora=9003,
            nom="Aïllament SATE",
            categoria="envolupant",
            unitatBase=UnitatBaseMillora.M2,
            parametresBase={
                "impactes": {
                    "reduccio_demanda_calefaccio": 0.40,
                    "reduccio_demanda_refrigeracio": 0.20,
                    "reduccio_infiltracions": 0.10
                }
            }
        )
        
        items = [{"millora": millora_sate, "quantitat": None, "coberturaPercent": 50}]
        resultat = simular_millores(self.edifici, items)
        
        parcial = resultat["items"][0]
        self.assertGreater(parcial["reduccioConsumKwhAny"], 0)
        self.assertEqual(parcial["quantitatAplicada"], 500)

    def test_simulacio_sense_dades_base_usa_fallbacks(self):
        """Prova que si l'edifici no té consums/emissions calculats, usa els FALLBACKS definits al motor"""
        # Creem un edifici 'buit' sense consums
        edifici_buit = self._create_edifici(self.admin, self.grup, numero=101)
        edifici_buit.superficieTotal = 100
        # Forcem que no tingui dades prèvies per forçar els fallbacks de l'engine
        edifici_buit.consumFinalKwhAny = None 
        edifici_buit.emissionsKgCO2Any = None
        edifici_buit.save()

        # Simulem amb una llista buida només per veure com calcula la base
        resultat = simular_millores(edifici_buit, [])
        
        # Comprovem que ha usat el CONSUM_KWH_M2_ANY_FALLBACK (110.0 * 100m2 = 11000)
        self.assertEqual(resultat["abans"]["consumFinalKwhAny"], 11000)
        # Comprovem que el score base està "clampat" o calculat sense petar
        self.assertIsNotNone(resultat["abans"]["score"])

    def test_simulacio_quantitat_zero_o_invalida(self):
        """Prova com reacciona el motor quan se li passa una quantitat de 0 o cobertura 0"""
        millora_buda = CatalegMillora.objects.create(
            idMillora=9004,
            nom="Millora sense efecte",
            categoria="envolupant",
            unitatBase=UnitatBaseMillora.M2,
            parametresBase={"impactes": {"reduccio_demanda_calefaccio": 0.50}}
        )
        
        # Li passem quantitat 0 i cobertura 0
        items = [{"millora": millora_buda, "quantitat": 0, "coberturaPercent": 0}]
        resultat = simular_millores(self.edifici, items)
        
        # No hauria d'haver-hi cap estalvi
        self.assertEqual(resultat["delta"]["reduccioConsumKwhAny"], 0)
        self.assertEqual(resultat["delta"]["reduccioEmissionsKgCO2Any"], 0)

    def test_funcions_auxiliars_clamp_i_limits(self):
        """Força valors extrems per comprovar que les funcions clamp i _round funcionen correctament"""
        millora_extrema = CatalegMillora.objects.create(
            idMillora=9005,
            nom="Millora Extrema",
            categoria="climatitzacio",
            unitatBase=UnitatBaseMillora.EDIFICI,
            parametresBase={"impactes": {"reduccio_emissions_calefaccio": 5.0}} # 500% de reducció per forçar límits
        )
        
        items = [{"millora": millora_extrema, "quantitat": 1, "coberturaPercent": 100}]
        resultat = simular_millores(self.edifici, items)
        
        # El percentatge de reducció no hauria de passar mai del 100% ni ser negatiu gràcies al clamp
        self.assertLessEqual(resultat["delta"]["reduccioConsumPercent"], 100.0)
        self.assertGreaterEqual(resultat["despres"]["consumFinalKwhAny"], 0.0)

# ============================================================================
# EPIC 4 — PROVES D'INTEGRACIÓ DEL MOTOR DE SIMULACIÓ
# ============================================================================

class MotorSimulacioIntegrationTests(BaseTestData):
    """
    Proves d'integració per validar que l'API respon correctament
    quan el Frontend (Flutter) demana una previsualització de millores.
    """

    def setUp(self):
        super().setUp()
        
        self.admin = self._create_user("admin_simulacio@example.com", RoleChoices.ADMIN)
        self.grup = GrupComparable.objects.create(
            idGrup=98, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-100"
        )
        self.edifici = self._create_edifici(self.admin, self.grup, numero=2)
        
        self.edifici.puntuacioBase = 50.0
        self.edifici.save()
        
        self.millora_sate = CatalegMillora.objects.create(
            nom="Aïllament SATE",
            categoria="Envolupant",
            costMinim=40.0,
            costMaxim=60.0,
            estalviEnergeticEstimat=20.0,
            impactePunts=15.0, 
            nivellConfianca="alt",
            unitatBase="m2",
            parametresBase={
                "impactes": {
                    "reduccio_demanda_calefaccio": 0.30,
                    "reduccio_consum_electric_total_tipica": 0.10
                }
            }
        )

    def test_api_simulacio_preview_retorna_200_i_dades_correctes(self):
        """
        Validem que cridant a l'endpoint (POST) amb DRF obtenim 
        el JSON sencer de la simulació per poder-lo mostrar a Flutter.
        """
        self.client.force_authenticate(user=self.admin)
        
        url = reverse('edifici-simulacions-preview', args=[self.edifici.idEdifici])
        
        payload = {
            "millores": [
                {
                    "milloraId": self.millora_sate.idMillora,
                    "quantitat": 100,
                    "coberturaPercent": 100
                }
            ]
        }
        
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertIn("abans", response.data)
        self.assertIn("despres", response.data)
        self.assertIn("delta", response.data)
        
        self.assertEqual(response.data["delta"]["incrementScore"], 15.0)

    def test_api_simulacio_get_historial(self):
        """Cobreix el mètode GET per llistar l'historial de simulacions d'un edifici."""
        self.client.force_authenticate(user=self.admin)
        url = reverse('edifici-simulacions', args=[self.edifici.idEdifici])
        
        sim = SimulacioMillora.objects.create(
            edifici=self.edifici,
            descripcio="Simulació antiga",
            reduccioConsumPrevista=100.0,
            reduccioEmissionsPrevista=50.0,
            costEstimat=5000.0,
            estalviAnual=200.0,
            hipotesiBase={"score": 50},
            resultat={"fake": "data"},
            versioMotor="SIM-1.0"
        )
        
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], sim.id)

    def test_api_simulacio_post_errors_400_i_404(self):
        """Cobreix el control d'errors del views.py (Exceptions i dades invàlides)."""
        self.client.force_authenticate(user=self.admin)
        url = reverse('edifici-simulacions', args=[self.edifici.idEdifici])
        
        resp_400 = self.client.post(url, {"un_camp_erroni": 123}, format='json')
        self.assertEqual(resp_400.status_code, status.HTTP_400_BAD_REQUEST)
        
        payload_invalid = {"millores": [{"milloraId": 99999, "quantitat": 1}]}
        resp_invalid = self.client.post(url, payload_invalid, format='json')
        self.assertEqual(resp_invalid.status_code, status.HTTP_400_BAD_REQUEST)