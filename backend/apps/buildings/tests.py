from django.test import TestCase
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import IntegrityError, transaction
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.buildings.models import BadgeDefinition, BuildingBadge, BadgeScope, BadgeCategory, CatalegMillora, Edifici, EdificiAuditLog, EstatValidacio, Habitatge, Localitzacio, GrupComparable, MilloraImplementada, SimulacioMillora, SimulacioMilloraItem, EstatAplicacioSimulacio, RolVinculacioHabitatge, TipusEdifici
from apps.buildings.serializers import EdificiDetailSerializer, LocalitzacioSerializer
from apps.accounts.models import RoleChoices, ValidacioAdmin
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

# Nous tests per augmentar cobertura a:
#   - apps/buildings/permissions.py  (35% → objectiu 75%+)
#   - apps/buildings/serializers.py  (69% → objectiu 85%+)
#   - apps/buildings/views.py        (48% → objectiu 70%+)
#
# Afegir a la suite existent: python manage.py test apps.buildings -v 2
#
# Estructura:
#   1. PermissionsTests          → cobreix les 5 classes de permissions.py
#   2. SerializerTests           → cobreix serializers no exercitats
#   3. HabitatgeViewTests        → CRUD + permisos per rol
#   4. MilloresImplementadesTests→ llistar per edifici
#   5. DadesEnergetiquesViewTests→ CRUD + permisos
#   6. AutocompleteCarrersTests  → endpoint autocomplete
 
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
 
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch, MagicMock
 
from django.contrib.auth import get_user_model
 
from apps.accounts.models import RoleChoices
from apps.buildings.models import (
    Edifici, Habitatge, Localitzacio, GrupComparable,
    DadesEnergetiques, CatalegMillora, SimulacioMillora,
    SimulacioMilloraItem, MilloraImplementada, EstatValidacio,
    carrersBarcelona,
)
from apps.buildings.serializers import (
    HabitatgeDetailSerializer,
    DadesEnergetiquesSerializer,
    MilloraImplementadaSerializer,
)
from apps.buildings.permissions import (
    EsAdminEdifici,
    EsAdminOPropietariEdifici,
    EsAdminOPropietariHabitatge,
    EsOwnerOAdminHabitatge,
    EsOwnerOAdminDadesEnergetiques,
)
 
User = get_user_model()
 
 
# ============================================================================
# Base compartida
# ============================================================================
 
class BaseTestData(APITestCase):
 
    @classmethod
    def _create_user(cls, email, role, is_superuser=False):
        if is_superuser:
            return User.objects.create_superuser(email=email, password="Password123")
        user = User.objects.create_user(email=email, password="Password123", first_name="Test")
        user.profile.role = role
        user.profile.save(update_fields=["role"])
        return user
 
    @classmethod
    def _create_grup(cls, id=1):
        return GrupComparable.objects.create(
            idGrup=id, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="100-200"
        )
 
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
 
    @classmethod
    def _create_habitatge(cls, edifici, ref="REF001", usuari=None):
        return Habitatge.objects.create(
            referenciaCadastral=ref, planta="1", porta="A",
            superficie=80, edifici=edifici, usuari=usuari,
        )
 
 
# ============================================================================
# 1. PERMISSIONS — cobreix les 5 classes directament
# ============================================================================
 
class EsAdminEdificiPermissionTests(BaseTestData):
    """
    Cobreix EsAdminEdifici:
    - has_permission: rol admin ✅, owner ❌, no autenticat ❌
    - has_object_permission: admin del edifici ✅, admin d'un altre edifici ❌
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_perm@example.com", RoleChoices.ADMIN)
        cls.admin2 = cls._create_user("admin2_perm@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner_perm@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant_perm@example.com", RoleChoices.TENANT)
        cls.grup = cls._create_grup(id=20)
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=20)
 
    def test_admin_pot_crear_edifici(self):
        """RBAC: rol admin → has_permission=True."""
        self.client.force_authenticate(user=self.admin)
        # POST a edifici-list sense cos vàlid, però el 400 confirma que el permís passa
        response = self.client.post(reverse("edifici-list"), {}, format="json")
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)
 
    def test_owner_no_pot_crear_edifici(self):
        """RBAC: rol owner → has_permission=False → 403."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(reverse("edifici-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
 
    def test_tenant_no_pot_crear_edifici(self):
        """RBAC: rol tenant → has_permission=False → 403."""
        self.client.force_authenticate(user=self.tenant)
        response = self.client.post(reverse("edifici-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
 
    def test_no_autenticat_no_pot_crear_edifici(self):
        """Sense token → 401."""
        response = self.client.post(reverse("edifici-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
 
    def test_admin_propi_pot_esborrar_edifici(self):
        """ABAC: admin de l'edifici → DELETE retorna 204."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(
            reverse("edifici-detail", args=[self.edifici.idEdifici])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
 
    def test_admin_aliè_no_pot_esborrar_edifici(self):
        """ABAC: admin2 no és l'administrador d'aquest edifici → 403."""
        self.client.force_authenticate(user=self.admin2)
        response = self.client.delete(
            reverse("edifici-detail", args=[self.edifici.idEdifici])
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )
 
 
class EsAdminOPropietariEdificiPermissionTests(BaseTestData):
    """
    Cobreix EsAdminOPropietariEdifici:
    - Tenant amb habitatge → GET 200
    - Tenant sense habitatge → 403/404
    - Tenant → PATCH 403
    - Owner amb habitatge → GET 200
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_abac@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner_abac@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant_abac@example.com", RoleChoices.TENANT)
        cls.tenant2 = cls._create_user("tenant2_abac@example.com", RoleChoices.TENANT)
        cls.grup = cls._create_grup(id=21)
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=21)
        cls._create_habitatge(cls.edifici, ref="REF-ABAC1", usuari=cls.tenant)
        cls._create_habitatge(cls.edifici, ref="REF-ABAC2", usuari=cls.owner)
 
    def test_tenant_amb_habitatge_pot_veure_edifici(self):
        """ABAC: tenant vinculat → GET /edificis/{id}/ → 200."""
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici.idEdifici]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
 
    def test_tenant_sense_habitatge_no_veu_edifici(self):
        """ABAC: tenant sense vinculació → 403 o 404."""
        self.client.force_authenticate(user=self.tenant2)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici.idEdifici]))
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )
 
    def test_tenant_no_pot_patch_edifici(self):
        """Matriu RBAC: tenant → PATCH → 403."""
        self.client.force_authenticate(user=self.tenant)
        response = self.client.patch(
            reverse("edifici-detail", args=[self.edifici.idEdifici]),
            {"orientacioPrincipal": "Nord"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
 
    def test_owner_amb_habitatge_pot_veure_edifici(self):
        """ABAC: owner vinculat → GET → 200."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("edifici-detail", args=[self.edifici.idEdifici]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
 
 
class EsAdminOPropietariHabitatgePermissionTests(BaseTestData):
    """
    Cobreix EsAdminOPropietariHabitatge:
    - Admin de l'edifici → GET 200
    - Owner del habitatge → GET 200
    - Tenant del habitatge → GET 200
    - Usuari sense relació → 403/404
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_hab@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner_hab@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant_hab@example.com", RoleChoices.TENANT)
        cls.other = cls._create_user("other_hab@example.com", RoleChoices.TENANT)
        cls.grup = cls._create_grup(id=22)
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=22)
        cls.habitatge = cls._create_habitatge(cls.edifici, ref="REF-HAB1", usuari=cls.owner)
 
    def test_admin_pot_veure_habitatge(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("habitatge-detail", args=[self.habitatge.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
 
    def test_owner_pot_veure_el_seu_habitatge(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("habitatge-detail", args=[self.habitatge.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
 
    def test_usuari_sense_relacio_no_pot_veure_habitatge(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(reverse("habitatge-detail", args=[self.habitatge.pk]))
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )
 
 
class EsOwnerOAdminHabitatgePermissionTests(BaseTestData):
    """
    Cobreix EsOwnerOAdminHabitatge:
    - Tenant → no pot escriure (403)
    - Owner del habitatge → pot esborrar (204)
    - Owner aliè → no pot esborrar (403/404)
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_owadm@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner_owadm@example.com", RoleChoices.OWNER)
        cls.owner2 = cls._create_user("owner2_owadm@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant_owadm@example.com", RoleChoices.TENANT)
        cls.grup = cls._create_grup(id=23)
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=23)
        cls.habitatge = cls._create_habitatge(cls.edifici, ref="REF-OWA1", usuari=cls.owner)
 
    def test_tenant_no_pot_esborrar_habitatge(self):
        """Tenant no té permís d'escriptura sobre habitatges."""
        self.client.force_authenticate(user=self.tenant)
        response = self.client.delete(reverse("habitatge-detail", args=[self.habitatge.pk]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
 
    def test_owner_aliè_no_pot_esborrar_habitatge(self):
        """Owner sense relació amb l'habitatge → 403/404."""
        self.client.force_authenticate(user=self.owner2)
        response = self.client.delete(reverse("habitatge-detail", args=[self.habitatge.pk]))
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )
 
    def test_no_autenticat_no_pot_esborrar_habitatge(self):
        """Sense token → 401."""
        response = self.client.delete(reverse("habitatge-detail", args=[self.habitatge.pk]))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
 
 
# ============================================================================
# 2. SERIALIZERS — casos no coberts
# ============================================================================
 
class HabitatgeDetailSerializerTests(TestCase):
    """
    Cobreix HabitatgeDetailSerializer:
    - superficie <= 0 → error
    - anyReforma futur → error
    - anyReforma anterior a la construcció → error
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="admin_ser@example.com", password="Password123", first_name="Admin"
        )
        cls.admin.profile.role = RoleChoices.ADMIN
        cls.admin.profile.save(update_fields=["role"])
        cls.grup = GrupComparable.objects.create(
            idGrup=31, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-100"
        )
        loc = Localitzacio.objects.create(
            carrer="Carrer Serializer", numero=1, codiPostal="08001",
            barri="Centre", latitud=41.0, longitud=2.0, zonaClimatica="C2",
        )
        cls.edifici = Edifici.objects.create(
            anyConstruccio=2000, tipologia="Residencial", superficieTotal=400,
            reglament="CTE", orientacioPrincipal="Sud",
            localitzacio=loc, administradorFinca=cls.admin, grupComparable=cls.grup,
        )
 
    def _base_data(self, **kwargs):
        base = {
            "referenciaCadastral": "REF-SER1",
            "planta": "1",
            "porta": "A",
            "superficie": 80.0,
            "edifici": self.edifici.pk,
        }
        base.update(kwargs)
        return base
 
    def test_superficie_zero_invalida(self):
        s = HabitatgeDetailSerializer(data=self._base_data(superficie=0))
        self.assertFalse(s.is_valid())
        self.assertIn("superficie", s.errors)
 
    def test_superficie_negativa_invalida(self):
        s = HabitatgeDetailSerializer(data=self._base_data(superficie=-10))
        self.assertFalse(s.is_valid())
        self.assertIn("superficie", s.errors)
 
    def test_any_reforma_futur_invalid(self):
        any_futur = timezone.now().year + 1
        s = HabitatgeDetailSerializer(data=self._base_data(anyReforma=any_futur))
        self.assertFalse(s.is_valid())
        self.assertIn("anyReforma", s.errors)
 
    def test_any_reforma_anterior_a_construccio_invalid(self):
        s = HabitatgeDetailSerializer(data=self._base_data(anyReforma=1999))
        self.assertFalse(s.is_valid())
        self.assertIn("anyReforma", s.errors)
 
    def test_any_reforma_valid(self):
        s = HabitatgeDetailSerializer(data=self._base_data(anyReforma=2010))
        self.assertTrue(s.is_valid(), msg=s.errors)
 
 
# ============================================================================
# 3. HabitatgeViewSet — CRUD + permisos
# ============================================================================
 
class HabitatgeViewTests(BaseTestData):
    """
    Cobreix HabitatgeViewSet:
    - Admin: list/detail/create/update/delete en edificis propis
    - Owner: list/detail del seu habitatge
    - Tenant: list/detail, no escriptura
    - Sense token → 401
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_hv@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner_hv@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant_hv@example.com", RoleChoices.TENANT)
        cls.grup = cls._create_grup(id=40)
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=40)
        cls.habitatge_owner = cls._create_habitatge(
            cls.edifici, ref="REF-HV1", usuari=cls.owner
        )
        cls.habitatge_tenant = cls._create_habitatge(
            cls.edifici, ref="REF-HV2", usuari=cls.tenant
        )
 
    def test_admin_list_habitatges(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(reverse("habitatge-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 2)
 
    def test_owner_veu_nomes_el_seu_habitatge(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("habitatge-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refs = [h["referenciaCadastral"] for h in response.data]
        self.assertIn("REF-HV1", refs)
        self.assertNotIn("REF-HV2", refs)
 
    def test_tenant_veu_nomes_el_seu_habitatge(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.get(reverse("habitatge-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refs = [h["referenciaCadastral"] for h in response.data]
        self.assertIn("REF-HV2", refs)
        self.assertNotIn("REF-HV1", refs)
 
    def test_tenant_no_pot_patch_habitatge(self):
        self.client.force_authenticate(user=self.tenant)
        response = self.client.patch(
            reverse("habitatge-detail", args=[self.habitatge_tenant.pk]),
            {"superficie": 90}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
 
    def test_owner_pot_veure_el_seu_habitatge_detail(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(
            reverse("habitatge-detail", args=[self.habitatge_owner.pk])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
 
    def test_sense_token_retorna_401(self):
        response = self.client.get(reverse("habitatge-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
 
 
# ============================================================================
# 4. MilloresImplementadesViewTests
# ============================================================================
 
class MilloresImplementadesViewTests(BaseTestData):
    """
    Cobreix l'action millores_implementades a EdificiViewSet:
    - Admin → 200 + llista les millores
    - Edifici sense millores → 200 + llista buida
    - Usuari sense accés → 403/404
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_mi@example.com", RoleChoices.ADMIN)
        cls.other = cls._create_user("other_mi@example.com", RoleChoices.ADMIN)
        cls.grup = cls._create_grup(id=60)
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=60)
        cls.millora = CatalegMillora.objects.create(
            nom="Climatització", categoria="envolupant",
            descripcio="Millora de prova", costMinim=1000.0, costMaxim=5000.0,
            estalviEnergeticEstimat=10.0, impactePunts=5.0,
            activa=True, costEstimatBase=2000.0, vidaUtil=20,
        )
        MilloraImplementada.objects.create(
            dataExecucio="2024-01-01",
            costReal=2000.0,
            estatValidacio=EstatValidacio.VALIDADA,
            millora=cls.millora,
            edifici=cls.edifici,
        )
 
    def _url(self):
        return reverse("edifici-millores-implementades", args=[self.edifici.idEdifici])
 
    def test_admin_veu_millores_implementades(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
 
    def test_edifici_sense_millores_retorna_llista_buida(self):
        """Un edifici sense millores retorna 200 amb llista buida."""
        loc = Localitzacio.objects.create(
            carrer="Carrer Buit", numero=99, codiPostal="08001",
            barri="Centre", latitud=41.0, longitud=2.0, zonaClimatica="C2",
        )
        edifici_buit = Edifici.objects.create(
            anyConstruccio=2000, tipologia="Residencial", superficieTotal=100,
            reglament="CTE", orientacioPrincipal="Sud",
            localitzacio=loc, administradorFinca=self.admin, grupComparable=self.grup,
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            reverse("edifici-millores-implementades", args=[edifici_buit.idEdifici])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
 
    def test_usuari_sense_acces_no_veu_millores(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(self._url())
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )
 
    def test_sense_token_retorna_401(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
 
 
# ============================================================================
# 5. DadesEnergetiquesViewTests
# ============================================================================
 
class DadesEnergetiquesViewTests(BaseTestData):
    """
    Cobreix DadesEnergetiquesViewSet i l'action dades_energetiques de EdificiViewSet:
    - Admin veu dades del seu edifici → 200
    - Owner veu les seves pròpies → 200
    - Usuari sense relació → 403/404
    - Sense token → 401
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_de@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner_de@example.com", RoleChoices.OWNER)
        cls.other = cls._create_user("other_de@example.com", RoleChoices.OWNER)
        cls.grup = cls._create_grup(id=70)
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=70)
        cls.habitatge = cls._create_habitatge(cls.edifici, ref="REF-DE1", usuari=cls.owner)
 
        cls.dades = DadesEnergetiques.objects.create(
            consumEnergiaPrimaria=80.0,
            consumEnergiaFinal=60.0,
            emissionsCO2=20.0,
            costAnualEnergia=800.0,
            energiaCalefaccio=20.0, energiaRefrigeracio=10.0,
            energiaACS=10.0, energiaEnllumenament=10.0,
            emissionsCalefaccio=5.0, emissionsRefrigeracio=3.0,
            emissionsACS=3.0, emissionsEnllumenament=3.0,
            aillamentTermic=60.0, valorFinestres=1.5,
            normativa="CTE", einaCertificacio="CE3X",
            motiuCertificacio="Venda",
            rehabilitacioEnergetica=False,
            dataEntrada="2024-01-01",
        )
        cls.habitatge.dadesEnergetiques = cls.dades
        cls.habitatge.save(update_fields=["dadesEnergetiques"])
 
    def _url_action(self):
        return reverse("edifici-dades-energetiques", args=[self.edifici.idEdifici])
 
    def test_admin_veu_dades_energetiques_de_ledifici(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url_action())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
 
    def test_owner_veu_les_seves_dades_energetiques(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self._url_action())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
 
    def test_altre_usuari_sense_acces_a_dades_energetiques(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.get(self._url_action())
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )
 
    def test_sense_token_retorna_401(self):
        response = self.client.get(self._url_action())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
 
    def test_habitatge_sense_dades_energetiques_no_apareix(self):
        """Un habitatge sense dades energètiques no apareix a la resposta."""
        self._create_habitatge(self.edifici, ref="REF-DE-BUIT")
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url_action())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refs = [d["referenciaCadastral"] for d in response.data]
        self.assertNotIn("REF-DE-BUIT", refs)
 
 
class TestDadesEnergetiquesValidacio(BaseTestData):
    """
    Comprova que el model/serializer rebutja valors fora de rang
    o sense sentit físic a DadesEnergetiques.
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.owner = cls._create_user("owner_val@example.com", RoleChoices.OWNER)
        cls.grup = GrupComparable.objects.create(
            idGrup=20, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-200"
        )
        cls.edifici = cls._create_edifici(cls.owner, cls.grup, numero=300)
        cls.habitatge = Habitatge.objects.create(
            referenciaCadastral="VAL001",
            planta="1", porta="1", superficie=80.0,
            edifici=cls.edifici,
            usuari=cls.owner,
        )
 
    def _url(self):
        return reverse("edifici-me-habitatge", args=[self.edifici.idEdifici, "VAL001"])
 
    def test_consum_energia_negatiu_retorna_400(self):
        """consumEnergiaPrimaria negatiu no té sentit físic → 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(),
            {"dadesEnergetiques": {"consumEnergiaPrimaria": -50, "emissionsCO2": 25}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
 
    def test_emissions_co2_negatiu_retorna_400(self):
        """emissionsCO2 negatiu no té sentit físic → 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(),
            {"dadesEnergetiques": {"consumEnergiaPrimaria": 50, "emissionsCO2": -10}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
 
    def test_aillament_termic_negatiu_retorna_400(self):
        """aillamentTermic negatiu no té sentit físic → 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(),
            {"dadesEnergetiques": {"consumEnergiaPrimaria": 50, "emissionsCO2": 25, "aillamentTermic": -1}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
 
    def test_cost_anual_energia_negatiu_retorna_400(self):
        """costAnualEnergia negatiu no té sentit econòmic → 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(),
            {"dadesEnergetiques": {"consumEnergiaPrimaria": 50, "emissionsCO2": 25, "costAnualEnergia": -200}},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
 
# ============================================================================
# 6. AutocompleteCarrersTests
# ============================================================================
 
class AutocompleteCarrersTests(BaseTestData):
    """
    Cobreix autocomplete_carrers:
    - query < 2 caràcters → llista buida
    - query vàlida → retorna resultats
    - sense token → 401
    - stopwords soles → llista buida o pocs resultats
    """
 
    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_ac@example.com", RoleChoices.ADMIN)
        carrersBarcelona.objects.create(
            codi_via="001", codi_carrer_ine="001", nom_oficial="Carrer de Mallorca",
            nom_curt="Mallorca", tipus_via="Carrer", nre_min=1, nre_max=500,
        )
 
    def _url(self):
        return reverse("autocomplete-carrers")
 
    def test_query_curta_retorna_buida(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url(), {"q": "M"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
 
    def test_query_valida_retorna_resultats(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url(), {"q": "Mallorca"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        noms = [r["nom_oficial"] for r in response.data]
        self.assertIn("Carrer de Mallorca", noms)
 
    def test_sense_token_retorna_401(self):
        response = self.client.get(self._url(), {"q": "Mallorca"})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
 
    def test_query_sense_q_retorna_buida(self):
        """Sense paràmetre q → query buida → retorna []."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
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
        edifici_buit = self._create_edifici(self.admin, self.grup, numero=101)
        edifici_buit.superficieTotal = 100
        edifici_buit.consumFinalKwhAny = None 
        edifici_buit.emissionsKgCO2Any = None
        edifici_buit.save()

        resultat = simular_millores(edifici_buit, [])
        
        self.assertEqual(resultat["abans"]["consumFinalKwhAny"], 11000)
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
        
        items = [{"millora": millora_buda, "quantitat": 0, "coberturaPercent": 0}]
        resultat = simular_millores(self.edifici, items)
        
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
        
        self.assertLessEqual(resultat["delta"]["reduccioConsumPercent"], 100.0)
        self.assertGreaterEqual(resultat["despres"]["consumFinalKwhAny"], 0.0)

    def test_score_base_amb_historial_bhs(self):
        """Cobreix les línies 29-30 creant un historial BHS real a la BD"""
        from apps.buildings.models import BuildingHealthScore
        
        BuildingHealthScore.objects.create(
            edificio=self.edifici,
            version="1.0",
            score=88.5,
            pesos={"clima": 0.5, "envolupant": 0.5} # Camp JSON obligatori
        )
        
        resultat = simular_millores(self.edifici, [])
        self.assertEqual(resultat["abans"]["score"], 88.5)

    def test_dades_base_amb_habitatges(self):
        """Cobreix les línies 40 i 66-81 creant dades energètiques reals"""
        from apps.buildings.models import Habitatge, DadesEnergetiques
        from django.utils import timezone
        
        dades = DadesEnergetiques.objects.create(
            consumEnergiaPrimaria=2500,
            consumEnergiaFinal=2000,
            emissionsCO2=500,
            costAnualEnergia=400,
            energiaCalefaccio=1000,
            energiaRefrigeracio=500,
            energiaACS=300,
            energiaEnllumenament=200,
            emissionsCalefaccio=250,
            emissionsRefrigeracio=150,
            emissionsACS=50,
            emissionsEnllumenament=50,
            aillamentTermic=2.0,
            valorFinestres=3.0,
            normativa="CTE-2019",
            einaCertificacio="CE3X",
            motiuCertificacio="Simulació Test",
            dataEntrada=timezone.now().date() # Camp Data obligatori
        )
        
        Habitatge.objects.create(
            referenciaCadastral="9876543AB1234C0001DE", # PK
            planta="1",
            porta="1A",
            superficie=100.0,
            edifici=self.edifici,
            dadesEnergetiques=dades
        )
            
        resultat = simular_millores(self.edifici, [])
        
        self.assertEqual(resultat["abans"]["origenDades"], "dades_energetiques_habitatges")
        self.assertEqual(resultat["abans"]["consumFinalKwhAny"], 2000)

    def test_inferir_quantitats_per_totes_unitats(self):
        """Cobreix les línies 84-98 inferint automàticament quantitats segons la unitat"""
        from apps.buildings.models import UnitatBaseMillora, CatalegMillora
        
        unitats = [
            UnitatBaseMillora.M2,
            UnitatBaseMillora.UNITAT,
            UnitatBaseMillora.KWP,
            UnitatBaseMillora.KWH,
            UnitatBaseMillora.HABITATGE,
            UnitatBaseMillora.EDIFICI,
            "INVENTADA"
        ]
        
        for idx, unitat in enumerate(unitats):
            millora = CatalegMillora.objects.create(
                idMillora=9200 + idx,
                nom=f"Millora prova {unitat}",
                categoria="envolupant",
                unitatBase=unitat,
                parametresBase={}
            )
            simular_millores(self.edifici, [{"millora": millora, "quantitat": None, "coberturaPercent": 100}])

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


# ============================================================================
# US47 — Validació manual de millores implementades
# ============================================================================

class ValidacioMilloraImplementadaTests(BaseTestData):
    """
    Proves de l'endpoint POST /millores-implementades/{id}/validar/
    Cobreix: permisos, transicions d'estat vàlides i invàlides.
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("admin_val@example.com", RoleChoices.ADMIN)
        cls.other_admin = cls._create_user("other_admin_val@example.com", RoleChoices.ADMIN)
        cls.owner = cls._create_user("owner_val@example.com", RoleChoices.OWNER)
        cls.superuser = User.objects.create_superuser(
            email="super_val@example.com", password="Password123"
        )
        cls.grup = GrupComparable.objects.create(
            idGrup=77, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-100"
        )
        cls.edifici = cls._create_edifici(cls.admin, cls.grup, numero=77)
        cls.cataleg = CatalegMillora.objects.create(
            nom="Millora US47",
            categoria="Envolupant",
            costMinim=1000.0,
            costMaxim=2000.0,
            estalviEnergeticEstimat=10.0,
            impactePunts=5.0,
        )

    def _crear_millora_impl(self, estat=EstatValidacio.EN_REVISIO):
        return MilloraImplementada.objects.create(
            dataExecucio="2025-06-01",
            costReal=1500.0,
            estatValidacio=estat,
            millora=self.cataleg,
            edifici=self.edifici,
        )

    def _url(self, pk):
        return reverse("millora-implementada-validar", args=[pk])

    # --- permisos ---

    def test_admin_finca_no_pot_validar(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_pot_validar(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Rebutjada", "observacionsAdmin": "Documentació incompleta"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["estatValidacio"], "Rebutjada")
        self.assertEqual(resp.data["observacionsAdmin"], "Documentació incompleta")

    def test_admin_daltri_edifici_no_pot_validar(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=self.other_admin)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_no_pot_validar(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_no_pot_validar(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=None)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    # --- transicions d'estat ---

    def test_validar_des_de_pendent_documentacio(self):
        mi = self._crear_millora_impl(estat=EstatValidacio.PENDENT_DOCUMENTACIO)
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_no_es_pot_validar_una_millora_ja_validada(self):
        mi = self._crear_millora_impl(estat=EstatValidacio.VALIDADA)
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Rebutjada"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_es_pot_validar_una_millora_ja_rebutjada(self):
        mi = self._crear_millora_impl(estat=EstatValidacio.REBUTJADA)
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # --- validació d'input ---

    def test_estat_invalid_retorna_400(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(self._url(mi.pk), {"estatValidacio": "EnRevisió"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_estat_absent_retorna_400(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(self._url(mi.pk), {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # --- efectes secundaris ---

    def test_validar_desa_admin_sistema(self):
        mi = self._crear_millora_impl()
        self.client.force_authenticate(user=self.superuser)
        self.client.post(self._url(mi.pk), {"estatValidacio": "Validada"}, format="json")
        mi.refresh_from_db()
        self.assertEqual(mi.administradorFinca, self.superuser)

    def test_admin_sistema_pot_validar_multiples_millores(self):
        """Un admin de sistema pot validar més d'una millora."""
        mi1 = self._crear_millora_impl()
        mi2 = self._crear_millora_impl()
        self.client.force_authenticate(user=self.superuser)
        r1 = self.client.post(self._url(mi1.pk), {"estatValidacio": "Validada"}, format="json")
        r2 = self.client.post(self._url(mi2.pk), {"estatValidacio": "Rebutjada"}, format="json")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.status_code, status.HTTP_200_OK)

    def test_acreditar_implementacio_no_marca_simulacio_com_implementada(self):
        simulacio = SimulacioMillora.objects.create(
            edifici=self.edifici,
            creadaPer=self.admin,
            estatAplicacio=EstatAplicacioSimulacio.APROVADA,
        )
        SimulacioMilloraItem.objects.create(
            simulacio=simulacio,
            millora=self.cataleg,
            coberturaPercent=100,
        )

        document = SimpleUploadedFile(
            "evidencia.pdf",
            b"%PDF-1.4 evidencia de prova",
            content_type="application/pdf",
        )

        self.client.force_authenticate(user=self.admin)
        url = reverse(
            "edifici-acreditar-implementacio-simulacio",
            args=[self.edifici.pk, simulacio.pk],
        )
        resp = self.client.post(
            url,
            {
                "dataExecucio": "2025-06-01",
                "costReal": 1500.0,
                "documentacioAdjunta": document,
            },
            format="multipart",
        )

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        simulacio.refresh_from_db()
        self.assertEqual(simulacio.estatAplicacio, EstatAplicacioSimulacio.APROVADA)
        self.assertEqual(
            MilloraImplementada.objects.filter(
                simulacio=simulacio,
                estatValidacio=EstatValidacio.EN_REVISIO,
            ).count(),
            1,
        )

    def test_simulacio_passa_a_implementada_quan_totes_les_millores_estan_validades(self):
        simulacio = SimulacioMillora.objects.create(
            edifici=self.edifici,
            creadaPer=self.admin,
            estatAplicacio=EstatAplicacioSimulacio.APROVADA,
        )
        mi1 = MilloraImplementada.objects.create(
            dataExecucio="2025-06-01",
            costReal=1500.0,
            estatValidacio=EstatValidacio.EN_REVISIO,
            millora=self.cataleg,
            edifici=self.edifici,
            simulacio=simulacio,
        )
        mi2 = MilloraImplementada.objects.create(
            dataExecucio="2025-06-02",
            costReal=1700.0,
            estatValidacio=EstatValidacio.EN_REVISIO,
            millora=self.cataleg,
            edifici=self.edifici,
            simulacio=simulacio,
        )

        self.client.force_authenticate(user=self.superuser)

        r1 = self.client.post(self._url(mi1.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        simulacio.refresh_from_db()
        self.assertEqual(simulacio.estatAplicacio, EstatAplicacioSimulacio.APROVADA)

        r2 = self.client.post(self._url(mi2.pk), {"estatValidacio": "Validada"}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        simulacio.refresh_from_db()
        self.assertEqual(simulacio.estatAplicacio, EstatAplicacioSimulacio.IMPLEMENTADA)

class TestAdminFincaAltaEdifici(BaseTestData):
    # US-AF1: Validació de permisos, bloquejos i creació d'edificis per a Administradors de Finca

    def test_bloqueig_admin_no_aprovat(self):
        # Creem un admin però el deixem en estat PENDENT
        user = self._create_user(email="admin_pendent@test.com", role=RoleChoices.ADMIN)
        user.profile.estatValidacioAdmin = ValidacioAdmin.PENDENT,
        user.profile.save()

        # Intentem donar d'alta un edifici
        self.client.force_authenticate(user=user)
        url = reverse('admin-finca-edifici-alta')
        response = self.client.post(url, {
            "carrer": "Carrer de Prova",
            "numero": 10,
            "codiPostal": "08001"
        }, format='json')

        # Comprovem que ens retorna un 403 Forbidden i el missatge correcte
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("pendent de validació", response.data['error'])

    def test_bloqueig_edifici_amb_altre_admin(self):
        # Creem un admin vàlid i un edifici que ja és seu
        admin1 = self._create_user(email="admin1@test.com", role=RoleChoices.ADMIN)
        admin1.profile.estatValidacioAdmin = ValidacioAdmin.APROVAT
        admin1.profile.save()

        loc = Localitzacio.objects.create(carrer="Diagonal", numero=1, codiPostal="08001")
        Edifici.objects.create(localitzacio=loc, anyConstruccio=2000, superficieTotal=100, administradorFinca=admin1)

        # Creem un segon admin vàlid
        admin2 = self._create_user(email="admin2@test.com", role=RoleChoices.ADMIN)
        admin2.profile.estatValidacioAdmin = ValidacioAdmin.APROVAT
        admin2.profile.save()

        # El segon admin intenta "robar" l'edifici
        self.client.force_authenticate(user=admin2)
        url = reverse('admin-finca-edifici-alta')
        response = self.client.post(url, {
            "carrer": "Diagonal",
            "numero": 1,
            "codiPostal": "08001"
        }, format='json')

        # Comprovem que dóna un Error 409 Conflict per bloqueig
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("ja té un administrador", response.data['error'])

    def test_crear_edifici_si_no_existeix(self):
        # Creem un admin aprovat
        admin = self._create_user(email="admin_aprovat@test.com", role=RoleChoices.ADMIN)
        admin.profile.estatValidacioAdmin = ValidacioAdmin.APROVAT
        admin.profile.save()

        # Guardem quants edificis hi ha abans
        edificis_abans = Edifici.objects.count()

        # Fem la petició
        self.client.force_authenticate(user=admin)
        url = reverse('admin-finca-edifici-alta')
        response = self.client.post(url, {
            "carrer": "Passeig de Gràcia",
            "numero": 45,
            "codiPostal": "08007",
            "superficieTotal": 500
        }, format='json')

        # Comprovem que es crea correctament (201 Created)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Edifici.objects.count(), edificis_abans + 1)
        
        # Comprovem que l'edifici nou s'ha assignat a aquest admin
        nou_edifici = Edifici.objects.latest('idEdifici')
        self.assertEqual(nou_edifici.administradorFinca, admin)

class TestRestriccionsHabitatge(BaseTestData):
    """
    Validació (Sprint 3): Restriccions sobre els habitatges.
    """
    def test_admin_no_pot_crear_habitatge(self):
        # Creem un usuari Administrador vàlid i aprovat
        admin = self._create_user(email="admin_prova@test.com", role=RoleChoices.ADMIN)
        admin.profile.estatValidacioAdmin = ValidacioAdmin.APROVAT
        admin.profile.save()

        # Creem un edifici i una localització de prova (necessaris per crear un habitatge)
        loc = Localitzacio.objects.create(carrer="Carrer Prova", numero=1, codiPostal="08000")
        edifici = Edifici.objects.create(
            localitzacio=loc, 
            anyConstruccio=2000, 
            superficieTotal=100, 
            administradorFinca=admin
        )

        # Intentem fer un POST per crear un habitatge estant loguejats com a ADMIN
        self.client.force_authenticate(user=admin)
        url = reverse('habitatge-list')  # Aquest és el nom per defecte que crea el router
        response = self.client.post(url, {
            "edifici": edifici.idEdifici,
            "referenciaCadastral": "1234567AB9999C0001XX",
            "planta": "1",
            "porta": "1A",
            "superficie": 50.0
        }, format='json')

        # Comprovem que el sistema ens bloqueja amb un 403 Forbidden
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class HabitatgeFluxTests(BaseTestData):
    """Tests per a la Issue 55: Sol·licitud d'unió i validació d'habitatges."""

    def setUp(self):
        self.admin_finca = self._create_user("admin_finca@test.com", RoleChoices.ADMIN)
        self.usuari = self._create_user("usuari@test.com", RoleChoices.OWNER)
        
        # Creem un edifici gestionat per l'admin
        self.grup = GrupComparable.objects.create(idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-100")
        self.edifici = self._create_edifici(self.admin_finca, self.grup)
        self.url_list = reverse('habitatge-list')

    def test_creacio_habitatge_força_estat_pendent(self):
        """Comprova que qualsevol creació neix en EN_REVISIO i l'usuari és el solicitant."""
        self.client.force_authenticate(user=self.usuari)
        payload = {
            "referenciaCadastral": "BCN-12345",
            "edifici": self.edifici.idEdifici,
            "planta": "2",
            "porta": "1",
            "superficie": 75.0
        }
        response = self.client.post(self.url_list, payload, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        habitatge = Habitatge.objects.get(referenciaCadastral="BCN-12345")
        
        # Verifiquem la lògica de negoci
        self.assertEqual(habitatge.estatValidacio, EstatValidacio.EN_REVISIO)
        self.assertEqual(habitatge.solicitant, self.usuari)

    def test_rebuig_admin_elimina_registre(self):
        """Si l'admin rebutja la sol·licitud, l'habitatge s'esborra de la base de dades."""
        habitatge = Habitatge.objects.create(
            referenciaCadastral="REBUTJAR-ME",
            edifici=self.edifici,
            solicitant=self.usuari,
            estatValidacio=EstatValidacio.EN_REVISIO,
            superficie=80.0,
            planta="1",
            porta="1"
        )
        
        self.client.force_authenticate(user=self.admin_finca)
        url_validar = reverse('habitatge-validar-acces', kwargs={'pk': habitatge.pk})
        
        # L'admin envia rebuig
        response = self.client.post(url_validar, {"estat": "Rebutjada"}, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        habitatge.refresh_from_db()
        self.assertTrue(Habitatge.objects.filter(pk=habitatge.pk).exists())
        self.assertEqual(habitatge.estatValidacio, EstatValidacio.REBUTJADA)
        self.assertIsNone(habitatge.solicitant)

    def test_creacio_habitatge_guarda_rol_solicitat_owner(self):
        self.client.force_authenticate(user=self.usuari)
        payload = {
            "referenciaCadastral": "BCN-ROL-OWNER",
            "edifici": self.edifici.idEdifici,
            "planta": "4",
            "porta": "2",
            "superficie": 75.0,
        }

        response = self.client.post(self.url_list, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        habitatge = Habitatge.objects.get(referenciaCadastral="BCN-ROL-OWNER")
        self.assertEqual(habitatge.estatValidacio, EstatValidacio.EN_REVISIO)
        self.assertEqual(habitatge.solicitant, self.usuari)
        self.assertEqual(habitatge.rolSolicitat, RolVinculacioHabitatge.OWNER)

    def test_habitatge_permet_propietari_i_llogater_alhora(self):
        tenant = self._create_user("tenant_habitatge@test.com", RoleChoices.TENANT)

        habitatge = Habitatge.objects.create(
            referenciaCadastral="OWNER-TENANT-001",
            edifici=self.edifici,
            superficie=80.0,
            planta="1",
            porta="1",
            estatValidacio=EstatValidacio.VALIDADA,
            usuari=self.usuari,
            propietari=self.usuari,
        )

        self.client.force_authenticate(user=tenant)
        url_solicitar = reverse('habitatge-solicitar-acces', kwargs={'pk': habitatge.pk})
        response = self.client.post(url_solicitar, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        habitatge.refresh_from_db()
        self.assertEqual(habitatge.estatValidacio, EstatValidacio.EN_REVISIO)
        self.assertEqual(habitatge.solicitant, tenant)
        self.assertEqual(habitatge.rolSolicitat, RolVinculacioHabitatge.TENANT)
        self.assertEqual(habitatge.propietari, self.usuari)
        self.assertIsNone(habitatge.llogater)

        self.client.force_authenticate(user=self.admin_finca)
        url_validar = reverse('habitatge-validar-acces', kwargs={'pk': habitatge.pk})
        response = self.client.post(url_validar, {"estat": "Validada"}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        habitatge.refresh_from_db()
        self.assertEqual(habitatge.estatValidacio, EstatValidacio.VALIDADA)
        self.assertEqual(habitatge.propietari, self.usuari)
        self.assertEqual(habitatge.llogater, tenant)
        self.assertEqual(habitatge.usuari, self.usuari)
        self.assertIsNone(habitatge.solicitant)
        self.assertIsNone(habitatge.rolSolicitat)


class TestFluxSolicitudHabitatge(BaseTestData):
    """
    Validació US-H2: Sol·licitud d'unió a edifici per part d'un owner/tenant
    """
    def test_llistat_pendents_administrador(self):
        # Preparem dades: Un admin, un llogater i dos habitatges
        admin = self._create_user(email="admin_llista@test.com", role=RoleChoices.ADMIN)
        tenant = self._create_user(email="tenant_espera@test.com", role=RoleChoices.TENANT)
        
        loc = Localitzacio.objects.create(carrer="Carrer Balmes", numero=5, codiPostal="08007")
        edifici = Edifici.objects.create(localitzacio=loc, anyConstruccio=2000, superficieTotal=500, administradorFinca=admin)
        
        # Habitatge 1: En revisió (hauria de sortir a la llista)
        h_pendent = Habitatge.objects.create(
            referenciaCadastral="PENDENT11111", planta="1", porta="1", superficie=50, edifici=edifici,
            estatValidacio=EstatValidacio.EN_REVISIO, solicitant=tenant
        )
        # Habitatge 2: Ja validat (NO hauria de sortir)
        h_validat = Habitatge.objects.create(
            referenciaCadastral="VALIDAT22222", planta="1", porta="2", superficie=50, edifici=edifici,
            estatValidacio=EstatValidacio.VALIDADA, usuari=tenant
        )

        # Fem la petició com a Administrador
        self.client.force_authenticate(user=admin)
        url = reverse('habitatge-pendents')
        response = self.client.get(url)

        # Verificacions
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1) # Només n'hi ha d'haver un
        self.assertEqual(response.data[0]['referenciaCadastral'], "PENDENT11111")

        # Verificació de seguretat: Un llogater NO pot veure aquesta llista
        self.client.force_authenticate(user=tenant)
        response_denied = self.client.get(url)
        self.assertEqual(response_denied.status_code, status.HTTP_403_FORBIDDEN)

# ============================================================================
# HABITATGE ME — PATCH /edificis/<id>/me/habitatge/<referenciaCadastral>/
# ============================================================================

class HabitatgeMeUpdateTests(BaseTestData):
    """
    Tests per a l'endpoint PATCH me/habitatge/<ref>/:
    edició de dades bàsiques i update_or_create de DadesEnergetiques.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = cls._create_user("owner@example.com", RoleChoices.OWNER)
        cls.other_owner = cls._create_user("other@example.com", RoleChoices.OWNER)
        cls.tenant = cls._create_user("tenant@example.com", RoleChoices.TENANT)

        cls.grup = GrupComparable.objects.create(
            idGrup=1, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-200"
        )
        cls.edifici = cls._create_edifici(cls.owner, cls.grup, numero=10)

        cls.habitatge = Habitatge.objects.create(
            referenciaCadastral="HAB001",
            planta="2", porta="1",
            superficie=80.0,
            anyReforma=None,
            edifici=cls.edifici,
            usuari=cls.owner,
        )
        cls.habitatge_tenant = Habitatge.objects.create(
            referenciaCadastral="HAB002",
            planta="3", porta="2",
            superficie=60.0,
            edifici=cls.edifici,
            usuari=cls.tenant,
        )

    def _url(self, edifici_id, ref):
        return reverse("edifici-me-habitatge", args=[edifici_id, ref])

    def _dades_energetiques_payload(self, **overrides):
        base = {
            "qualificacioGlobal": "B",
            "consumEnergiaPrimaria": 120.5,
            "consumEnergiaFinal": 95.2,
            "emissionsCO2": 28.4,
            "costAnualEnergia": 850,
            "energiaCalefaccio": 40,
            "energiaRefrigeracio": 15,
            "energiaACS": 25,
            "energiaEnllumenament": 10,
            "emissionsCalefaccio": 12,
            "emissionsRefrigeracio": 4,
            "emissionsACS": 8,
            "emissionsEnllumenament": 3,
            "aillamentTermic": 1.2,
            "valorFinestres": 2.1,
            "normativa": "CTE 2019",
            "einaCertificacio": "CE3X",
            "motiuCertificacio": "Actualització de dades",
            "rehabilitacioEnergetica": False,
            "dataEntrada": "2026-04-29",
        }
        return {**base, **overrides}

    # ------------------------------------------------------------------
    # 1. Autenticació i permisos
    # ------------------------------------------------------------------

    def test_unauthenticated_returns_401(self):
        """Sense autenticació → 401."""
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"), {}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_can_patch_own_habitatge(self):
        """Owner autenticat pot fer PATCH del seu habitatge → 200."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"superficie": 90.0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_tenant_can_patch_own_habitatge(self):
        """Tenant autenticat pot fer PATCH del seu habitatge → 200."""
        self.client.force_authenticate(user=self.tenant)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB002"),
            {"superficie": 65.0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_other_user_cannot_patch_habitatge(self):
        """Usuari sense relació amb l'habitatge → 404."""
        self.client.force_authenticate(user=self.other_owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"superficie": 90.0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_wrong_edifici_returns_404(self):
        """Referència cadastral correcta però edifici incorrecte → 404."""
        other_edifici = self._create_edifici(self.owner, self.grup, numero=99)
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(other_edifici.idEdifici, "HAB001"),
            {"superficie": 90.0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_nonexistent_habitatge_returns_404(self):
        """Referència cadastral inexistent → 404."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "INEXISTENT"),
            {"superficie": 90.0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ------------------------------------------------------------------
    # 2. Edició de camps bàsics
    # ------------------------------------------------------------------

    def test_patch_basic_fields_persisted(self):
        """Els camps bàsics enviats es guarden correctament a la BD."""
        self.client.force_authenticate(user=self.owner)
        self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"planta": "3", "porta": "2", "superficie": 95.5, "anyReforma": 2015},
            format="json",
        )
        self.habitatge.refresh_from_db()
        self.assertEqual(self.habitatge.planta, "3")
        self.assertEqual(self.habitatge.porta, "2")
        self.assertEqual(float(self.habitatge.superficie), 95.5)
        self.assertEqual(self.habitatge.anyReforma, 2015)

    def test_patch_without_dades_energetiques_does_not_touch_them(self):
        """Si el payload no inclou dadesEnergetiques, no es crea ni modifica res."""
        self.client.force_authenticate(user=self.owner)
        self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"superficie": 85.0},
            format="json",
        )
        self.habitatge.refresh_from_db()
        self.assertIsNone(self.habitatge.dadesEnergetiques)

    def test_response_contains_full_habitatge(self):
        """La resposta retorna l'habitatge complet amb dadesEnergetiques nested."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"superficie": 88.0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("referenciaCadastral", response.data)
        self.assertIn("dadesEnergetiques", response.data)

    # ------------------------------------------------------------------
    # 3. Validacions de camps bàsics
    # ------------------------------------------------------------------

    def test_negative_superficie_rejected(self):
        """Superfície negativa o zero → 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"superficie": -10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("superficie", response.data)

    def test_future_any_reforma_rejected(self):
        """Any de reforma en el futur → 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"anyReforma": 2099},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("anyReforma", response.data)

    def test_any_reforma_before_construccio_rejected(self):
        """Any de reforma anterior a la construcció de l'edifici → 400."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"anyReforma": self.edifici.anyConstruccio - 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # 4. update_or_create de DadesEnergetiques
    # ------------------------------------------------------------------

    def test_creates_dades_energetiques_when_none_exist(self):
        """Si l'habitatge no té DadesEnergetiques, es creen i es vinculen."""
        self.assertIsNone(self.habitatge.dadesEnergetiques)
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"dadesEnergetiques": self._dades_energetiques_payload()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.habitatge.refresh_from_db()
        self.assertIsNotNone(self.habitatge.dadesEnergetiques)
        self.assertEqual(self.habitatge.dadesEnergetiques.qualificacioGlobal, "B")

    def test_updates_existing_dades_energetiques(self):
        """Si l'habitatge ja té DadesEnergetiques, s'actualitzen sense crear-ne de noves."""
        dades = DadesEnergetiques.objects.create(**self._dades_energetiques_payload())
        self.habitatge.dadesEnergetiques = dades
        self.habitatge.save(update_fields=["dadesEnergetiques"])
        id_original = dades.id

        self.client.force_authenticate(user=self.owner)
        self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"dadesEnergetiques": self._dades_energetiques_payload(qualificacioGlobal="A")},
            format="json",
        )

        self.habitatge.refresh_from_db()
        # Mateix objecte (no se n'ha creat un de nou)
        self.assertEqual(self.habitatge.dadesEnergetiques.id, id_original)
        self.assertEqual(self.habitatge.dadesEnergetiques.qualificacioGlobal, "A")

    def test_no_orphan_dades_energetiques_on_create(self):
        """Quan es creen DadesEnergetiques, queden vinculades (no òrfenes)."""
        self.client.force_authenticate(user=self.owner)
        self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"dadesEnergetiques": self._dades_energetiques_payload()},
            format="json",
        )
        self.habitatge.refresh_from_db()
        # La FK inversa ha de trobar exactament aquest habitatge
        self.assertEqual(
            self.habitatge.dadesEnergetiques.dades_energetiques.pk,
            self.habitatge.pk,
        )

    def test_dades_energetiques_response_nested(self):
        """La resposta inclou dadesEnergetiques nested amb les dades actualitzades."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self._url(self.edifici.idEdifici, "HAB001"),
            {"dadesEnergetiques": self._dades_energetiques_payload(consumEnergiaPrimaria=200.0)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data.get("dadesEnergetiques"))
        self.assertEqual(
            float(response.data["dadesEnergetiques"]["consumEnergiaPrimaria"]), 200.0
        )


class EdificiMapaEndpointTests(BaseTestData):
    """Tests de l'endpoint GeoJSON per al mapa d'edificis."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = cls._create_user("map-admin@example.com", RoleChoices.ADMIN)

        cls.grup = GrupComparable.objects.create(
            idGrup=99,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        cls.edifici_visible = cls._create_edifici(
            administrador=cls.admin,
            grup=cls.grup,
            carrer="Carrer Mallorca",
            numero=120,
        )
        cls.edifici_visible.puntuacioBase = 72.5
        cls.edifici_visible.classificacioEstimada = "C"
        cls.edifici_visible.classificacioFont = "estimada"
        cls.edifici_visible.save(
            update_fields=[
                "puntuacioBase",
                "classificacioEstimada",
                "classificacioFont",
            ]
        )

        cls.edifici_sense_coords = cls._create_edifici(
            administrador=cls.admin,
            grup=cls.grup,
            carrer="Carrer Sense Coordenades",
            numero=1,
        )
        cls.edifici_sense_coords.localitzacio.latitud = 0.0
        cls.edifici_sense_coords.localitzacio.longitud = 0.0
        cls.edifici_sense_coords.localitzacio.save(
            update_fields=["latitud", "longitud"]
        )

    def test_mapa_requires_authentication(self):
        response = self.client.get("/api/buildings/edificis/mapa/")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_mapa_returns_geojson_feature_collection(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/buildings/edificis/mapa/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "FeatureCollection")
        self.assertIn("features", response.data)
        self.assertGreaterEqual(len(response.data["features"]), 1)

        feature = response.data["features"][0]
        self.assertEqual(feature["type"], "Feature")
        self.assertEqual(feature["geometry"]["type"], "Point")
        self.assertIn("coordinates", feature["geometry"])
        self.assertIn("properties", feature)

    def test_mapa_excludes_buildings_without_valid_coordinates(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/buildings/edificis/mapa/")

        ids = [
            feature["properties"]["idEdifici"]
            for feature in response.data["features"]
        ]

        self.assertIn(self.edifici_visible.idEdifici, ids)
        self.assertNotIn(self.edifici_sense_coords.idEdifici, ids)

    def test_mapa_does_not_expose_private_user_or_habitatge_data(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/buildings/edificis/mapa/")

        feature = response.data["features"][0]
        properties = feature["properties"]

        self.assertNotIn("habitatges", properties)
        self.assertNotIn("usuari", properties)
        self.assertNotIn("administradorFinca", properties)
        self.assertNotIn("email", properties)

    def test_mapa_bbox_filter(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            "/api/buildings/edificis/mapa/?bbox=1.9,40.9,2.1,41.1"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

class EdificiCercaTests(BaseTestData):
    def setUp(self):
        super().setUp()
        self.user = self._create_user("cercador@test.com", RoleChoices.OWNER)

        loc1 = Localitzacio.objects.create(carrer="Carrer de Mallorca", numero=10, codiPostal="08001")
        Edifici.objects.create(
            localitzacio=loc1,
            anyConstruccio=1990,
            tipologia=TipusEdifici.RESIDENCIAL,
            superficieTotal=500.0
        )

        loc2 = Localitzacio.objects.create(carrer="Carrer de València", numero=20, codiPostal="08002")
        Edifici.objects.create(
            localitzacio=loc2,
            anyConstruccio=1985,
            tipologia=TipusEdifici.RESIDENCIAL,
            superficieTotal=450.0
        )

    def test_cerca_retorna_edificis_correctes(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('edifici-cerca-per-carrer')
        response = self.client.get(url, {'q': 'Mallorca'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['localitzacio']['carrer'], "Carrer de Mallorca")

    def test_cerca_buida_no_retorna_res(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('edifici-cerca-per-carrer')
        response = self.client.get(url, {'q': 'Ma'})
        self.assertEqual(len(response.data), 0)

# ============================================================================
# THIRD PARTY SERVICE — POST /api/third-party/score/
# ============================================================================
class ThirdPartyServiceTests(APITestCase):
    def setUp(self):
        self.url = '/api/third-party-service/'

    def test_no_api_key_returns_401_or_403(self):
        response = self.client.post(self.url, {"points": []}, format="json")
        self.assertIn(response.status_code, [401, 403])


# ============================================================================
# TC-HR-001 a TC-HR-006 — Tests unitaris de calcular_heat_risk_index
# ============================================================================

from apps.buildings.scoring import calcular_heat_risk_index


class TestCalcularHeatRiskIndex(BaseTestData):
    """
    Tests unitaris de la funció calcular_heat_risk_index (scoring.py).
    No toquen la BD: utilitzen mocks per simular l'edifici i les seves dades.
    """

    def _edifici_mock(self, od=None, habitatges_data=None):
        """
        Crea un mock d'edifici amb dades open data i/o habitatges configurables.
        habitatges_data: llista de dicts amb els camps de DadesEnergetiques.

        Camps HRI rellevants:
          - energiaRefrigeracio: float (0–100 kWh/m²a) — CRÍTIC
          - aillamentTermic:     float (0.05–5.0 W/m²K) — CRÍTIC
          - emissionsRefrigeracio: float (0–50 kgCO2/m²a) — opcional
        """
        edifici = MagicMock()
        edifici.dades_energetiques_opendata = od
        # FIX D: camps necessaris per a _calcular_hri_des_de_dades
        edifici.anyConstruccio = 2000          # any neutre → risc mig-baix
        edifici.orientacioPrincipal = "Est"    # orientació neutre → risc 0.6

        habitatges = []
        for data in (habitatges_data or []):
            h = MagicMock()
            dades = MagicMock(spec=DadesEnergetiques)
            for k, v in data.items():
                setattr(dades, k, v)
            h.dadesEnergetiques = dades
            habitatges.append(h)

        # FIX C: configurar tant .all() com .filter() per retornar el mock_qs correcte.
        # calcular_heat_risk_index usa:
        #   edifici.habitatges.filter(dadesEnergetiques__isnull=False).select_related(...)
        # Els habitatges del mock SEMPRE tenen dadesEnergetiques (o és None explícit),
        # així que filter() retorna els que tenen dades != None.
        habitatges_amb_dades = [h for h in habitatges if h.dadesEnergetiques is not None]

        mock_qs_filtrat = MagicMock()
        mock_qs_filtrat.exists.return_value = bool(habitatges_amb_dades)
        mock_qs_filtrat.count.return_value = len(habitatges_amb_dades)
        mock_qs_filtrat.__iter__ = lambda self: iter(habitatges_amb_dades)
        mock_qs_filtrat.select_related.return_value = mock_qs_filtrat

        mock_qs = MagicMock()
        mock_qs.exists.return_value = bool(habitatges)
        mock_qs.count.return_value = len(habitatges)
        mock_qs.__iter__ = lambda self: iter(habitatges)
        mock_qs.select_related.return_value = mock_qs
        mock_qs.all.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs_filtrat  # FIX C

        edifici.habitatges = mock_qs

        return edifici

    # ------------------------------------------------------------------
    # TC-HR-001
    # ------------------------------------------------------------------
    def test_sense_habitatges_retorna_usuaris(self):
        """TC-HR-001: Edifici sense habitatges → font None, index None."""
        # Sense habitatges, filter() retorna queryset buit → va a la branca
        # open data → od=None → retorna {index: None, font: None}
        edifici = self._edifici_mock(od=None, habitatges_data=[])
        resultat = calcular_heat_risk_index(edifici)

        self.assertIsNone(resultat["index"])
        # FIX A: la funció retorna font=None quan no hi ha habitatges ni od
        self.assertIsNone(resultat["font"])

    # ------------------------------------------------------------------
    # TC-HR-002
    # ------------------------------------------------------------------
    def test_dades_critiques_absents_retorna_usuaris(self):
        """TC-HR-002: Habitatge sense dades crítiques HRI → font 'usuaris', index None."""
        # FIX B: els camps crítics del HRI són energiaRefrigeracio i aillamentTermic.
        # Posem-los a None per simular dades insuficients.
        edifici = self._edifici_mock(od=None, habitatges_data=[
            {
                "energiaRefrigeracio": None,
                "aillamentTermic": None,
                "emissionsRefrigeracio": None,
            }
        ])
        resultat = calcular_heat_risk_index(edifici)

        self.assertIsNone(resultat["index"])
        # FIX A: la funció retorna la string "usuaris", no l'enum
        self.assertEqual(resultat["font"], "usuaris")

    # ------------------------------------------------------------------
    # TC-HR-003
    # ------------------------------------------------------------------
    def test_index_alt_amb_dades_desfavorables(self):
        """TC-HR-003: Refrigeració alta + aïllament baix → index >= 75 (risc alt)."""
        # FIX B: usem els camps reals del HRI.
        # energiaRefrigeracio alt (100 kWh) + aillamentTermic baix (0.1 W/m²K)
        # + edifici antic (1920) + orientació Sud → risc molt alt.
        edifici = self._edifici_mock(od=None, habitatges_data=[
            {
                "energiaRefrigeracio": 100.0,
                "aillamentTermic": 0.1,
                "emissionsRefrigeracio": 50.0,
            }
        ])
        # Fem l'edifici antic i orientat al Sud per assegurar index >= 75
        edifici.anyConstruccio = 1920
        edifici.orientacioPrincipal = "Sud"

        resultat = calcular_heat_risk_index(edifici)

        self.assertIsNotNone(resultat["index"])
        self.assertGreaterEqual(resultat["index"], 75)
        # FIX A: la funció retorna la string "usuaris"
        self.assertEqual(resultat["font"], "usuaris")

    # ------------------------------------------------------------------
    # TC-HR-004
    # ------------------------------------------------------------------
    def test_index_baix_amb_dades_favorables(self):
        """TC-HR-004: Refrigeració baixa + aïllament alt + edifici nou → index < 25."""
        # FIX B: energiaRefrigeracio baixa (5 kWh) + aillamentTermic alt (4.5 W/m²K)
        # + edifici nou (2020) + orientació Nord → risc molt baix.
        edifici = self._edifici_mock(od=None, habitatges_data=[
            {
                "energiaRefrigeracio": 5.0,
                "aillamentTermic": 4.5,
                "emissionsRefrigeracio": 2.0,
            }
        ])
        edifici.anyConstruccio = 2020
        edifici.orientacioPrincipal = "Nord"

        resultat = calcular_heat_risk_index(edifici)

        self.assertIsNotNone(resultat["index"])
        self.assertLess(resultat["index"], 25)
        # FIX A: la funció retorna la string "usuaris"
        self.assertEqual(resultat["font"], "usuaris")

    # ------------------------------------------------------------------
    # TC-HR-005
    # ------------------------------------------------------------------
    def test_index_es_mitjana_de_habitatges(self):
        """TC-HR-005: L'índex és la mitjana dels habitatges amb dades suficients."""
        # FIX B: usem camps HRI vàlids
        dades_h1 = {
            "energiaRefrigeracio": 40.0,
            "aillamentTermic": 2.0,
            "emissionsRefrigeracio": 20.0,
        }
        dades_h2 = {
            "energiaRefrigeracio": 70.0,
            "aillamentTermic": 1.0,
            "emissionsRefrigeracio": 35.0,
        }

        resultat_1 = calcular_heat_risk_index(
            self._edifici_mock(od=None, habitatges_data=[dades_h1])
        )
        resultat_2 = calcular_heat_risk_index(
            self._edifici_mock(od=None, habitatges_data=[dades_h2])
        )
        # FIX E: TC-HR-005 original fallava perquè els índexos eren None
        # (camps incorrectes). Ara amb camps HRI correctes, han de ser floats.
        self.assertIsNotNone(resultat_1["index"], "resultat_1 hauria de tenir index")
        self.assertIsNotNone(resultat_2["index"], "resultat_2 hauria de tenir index")

        edifici_dos = self._edifici_mock(od=None, habitatges_data=[dades_h1, dades_h2])
        resultat = calcular_heat_risk_index(edifici_dos)

        esperada = (resultat_1["index"] + resultat_2["index"]) / 2
        self.assertAlmostEqual(resultat["index"], esperada, places=5)

    # ------------------------------------------------------------------
    # TC-HR-006
    # ------------------------------------------------------------------
    def test_habitatge_sense_dades_energetiques_es_ignora(self):
        """TC-HR-006: Habitatge sense DadesEnergetiques es descarta sense error."""
        # FIX B + C: usem camps HRI vàlids per a l'habitatge bo.
        # L'habitatge sense dades (dadesEnergetiques=None) no passarà el filter()
        # del mock, de manera que el filtre retornarà només l'habitatge vàlid.
        edifici = self._edifici_mock(od=None, habitatges_data=[
            {
                "energiaRefrigeracio": 50.0,
                "aillamentTermic": 2.5,
                "emissionsRefrigeracio": 25.0,
            },
        ])

        # Afegim manualment un habitatge sense dades al queryset complet,
        # però el mock_qs_filtrat ja el filtra (perquè dadesEnergetiques=None).
        h_sense_dades = MagicMock()
        h_sense_dades.dadesEnergetiques = None

        # Reconfigurem el mock per incloure l'habitatge buit al total
        # però no al filtrat (comportament real del .filter(dadesEnergetiques__isnull=False))
        habitatges_tots = list(edifici.habitatges) + [h_sense_dades]
        habitatges_amb_dades = [h for h in habitatges_tots if h.dadesEnergetiques is not None]

        mock_qs_filtrat = MagicMock()
        mock_qs_filtrat.exists.return_value = bool(habitatges_amb_dades)
        mock_qs_filtrat.count.return_value = len(habitatges_amb_dades)
        mock_qs_filtrat.__iter__ = lambda self: iter(habitatges_amb_dades)
        mock_qs_filtrat.select_related.return_value = mock_qs_filtrat

        edifici.habitatges.count.return_value = len(habitatges_tots)
        edifici.habitatges.__iter__ = lambda self: iter(habitatges_tots)
        edifici.habitatges.filter.return_value = mock_qs_filtrat

        resultat = calcular_heat_risk_index(edifici)

        # Ha de calcular correctament amb l'habitatge vàlid
        self.assertIsNotNone(resultat["index"])
        self.assertEqual(resultat["font"], "usuaris")


# ============================================================================
# TC-HR-007 a TC-HR-010 — Tests d'integració: endpoint API
# ============================================================================

class TestHeatRiskSerializer(BaseTestData):
    """
    Tests d'integració: comprova que GET /buildings/{id}/ retorna
    el camp heat_risk correctament formatat.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = cls._create_user("owner_hr@example.com", RoleChoices.OWNER)
        cls.grup = GrupComparable.objects.create(
            idGrup=10, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-200"
        )
        cls.edifici = cls._create_edifici(cls.owner, cls.grup, numero=200)
        cls.habitatge = Habitatge.objects.create(
            referenciaCadastral="HR001",
            planta="1", porta="1", superficie=80.0,
            edifici=cls.edifici,
            usuari=cls.owner,
        )

    def _url(self):
        return reverse("edifici-detail", args=[self.edifici.idEdifici])

    def test_heat_risk_present_en_resposta(self):
        """TC-HR-007: El camp heat_risk és present a la resposta de detall d'edifici."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self._url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("heat_risk", response.data)

    def test_heat_risk_estructura_correcta(self):
        """TC-HR-008: El camp heat_risk té les claus index, font, etiqueta i dades_insuficients."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self._url())

        hr = response.data["heat_risk"]
        self.assertIn("index", hr)
        self.assertIn("font", hr)
        self.assertIn("etiqueta", hr)
        self.assertIn("dades_insuficients", hr)

    def test_heat_risk_etiqueta_sense_dades(self):
        """TC-HR-009: Sense DadesEnergetiques → etiqueta 'Sense dades', index null."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self._url())

        hr = response.data["heat_risk"]
        # L'habitatge de test no té DadesEnergetiques associades
        self.assertIsNone(hr["index"])
        self.assertEqual(hr["etiqueta"], "Sense dades")

    def test_heat_risk_etiqueta_risc_alt(self):
        """TC-HR-010: Amb dades desfavorables → etiqueta 'Risc alt'."""
        # FIX D: afegir tots els camps NOT NULL de DadesEnergetiques.
        # Els camps crítics del HRI (energiaRefrigeracio + aillamentTermic) han de
        # tenir valors desfavorables. La resta de camps obligatoris s'omplen amb
        # valors mínims vàlids.
        dades = DadesEnergetiques.objects.create(
            # Camps crítics HRI — valors de risc alt
            energiaRefrigeracio=100.0,
            aillamentTermic=0.1,
            emissionsRefrigeracio=50.0,
            # Resta de camps NOT NULL
            consumEnergiaPrimaria=95.0,
            consumEnergiaFinal=80.0,
            emissionsCO2=48.0,
            costAnualEnergia=2000.0,
            energiaCalefaccio=60.0,
            energiaACS=20.0,
            energiaEnllumenament=10.0,
            emissionsCalefaccio=30.0,
            emissionsACS=10.0,
            emissionsEnllumenament=5.0,
            valorFinestres=2.0,
            normativa="CTE-2006",
            einaCertificacio="CE3X",
            motiuCertificacio="Venda",
            rehabilitacioEnergetica=False,
            dataEntrada="2024-01-01",
        )

        self.habitatge.dadesEnergetiques = dades
        self.habitatge.save()

        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self._url())

        hr = response.data["heat_risk"]

        self.assertIsNotNone(hr["index"])
        self.assertGreaterEqual(hr["index"], 75)
        self.assertEqual(hr["etiqueta"], "Risc alt")


# ============================================================================
# TC-HR-011 a TC-HR-012 — Tests de persistència via signal
# ============================================================================

class TestHeatRiskPersistencia(BaseTestData):
    """
    Comprova que el signal _recalcular_edifici persisteix
    heatRiskIndex i heatRiskFont a l'edifici.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = cls._create_user("owner_signal@example.com", RoleChoices.OWNER)
        cls.grup = GrupComparable.objects.create(
            idGrup=11, zonaClimatica="C2", tipologia="Residencial", rangSuperficie="0-200"
        )
        cls.edifici = cls._create_edifici(cls.owner, cls.grup, numero=201)

    def _crear_dades_energetiques(self, **kwargs):
        """
        Helper per crear DadesEnergetiques amb tots els camps NOT NULL.
        Els kwargs sobreescriuen els valors per defecte.
        FIX D: centralitza la creació per evitar duplicar camps NOT NULL.
        """
        defaults = {
            "consumEnergiaPrimaria": 50.0,
            "consumEnergiaFinal": 40.0,
            "emissionsCO2": 25.0,
            "costAnualEnergia": 1200.0,
            "energiaCalefaccio": 30.0,
            "energiaRefrigeracio": 50.0,   # camp crític HRI
            "energiaACS": 15.0,
            "energiaEnllumenament": 8.0,
            "emissionsCalefaccio": 15.0,
            "emissionsRefrigeracio": 25.0,
            "emissionsACS": 8.0,
            "emissionsEnllumenament": 4.0,
            "aillamentTermic": 2.5,         # camp crític HRI (en W/m²K)
            "valorFinestres": 2.0,
            "normativa": "CTE-2006",
            "einaCertificacio": "CE3X",
            "motiuCertificacio": "Venda",
            "rehabilitacioEnergetica": False,
            "dataEntrada": "2024-01-01",
        }
        defaults.update(kwargs)
        return DadesEnergetiques.objects.create(**defaults)

    def test_signal_persisteix_heat_risk_en_crear_dades(self):
        """TC-HR-011: Crear DadesEnergetiques dispara el signal i omple heatRiskIndex."""

        habitatge = Habitatge.objects.create(
            referenciaCadastral="SIGNAL001",
            planta="1",
            porta="1",
            superficie=70.0,
            edifici=self.edifici,
            usuari=self.owner,
        )

        # FIX D: usem el helper amb tots els camps NOT NULL
        dades = self._crear_dades_energetiques(
            energiaRefrigeracio=50.0,
            aillamentTermic=2.5,
        )

        habitatge.dadesEnergetiques = dades
        habitatge.save()

        self.edifici.refresh_from_db()

        self.assertIsNotNone(self.edifici.heatRiskIndex)
        self.assertIsNotNone(self.edifici.heatRiskFont)

    def test_signal_persisteix_heat_risk_en_esborrar_habitatge(self):
        """TC-HR-012: Esborrar un habitatge recalcula i persisteix el heat risk."""

        habitatge = Habitatge.objects.create(
            referenciaCadastral="SIGNAL002",
            planta="2",
            porta="1",
            superficie=60.0,
            edifici=self.edifici,
            usuari=self.owner,
        )

        # FIX D: usem el helper amb tots els camps NOT NULL
        dades = self._crear_dades_energetiques(
            energiaRefrigeracio=40.0,
            aillamentTermic=3.0,
            rehabilitacioEnergetica=True,
        )

        habitatge.dadesEnergetiques = dades
        habitatge.save()

        self.edifici.refresh_from_db()
        self.assertIsNotNone(self.edifici.heatRiskIndex)

        habitatge.delete()

        self.edifici.refresh_from_db()
        self.assertIsNone(self.edifici.heatRiskIndex)

class LocalitzacioCoordinatesTests(APITestCase):
    def test_localitzacio_without_coordinates_keeps_null_values(self):
        localitzacio = Localitzacio.objects.create(
            carrer="Carrer Sense Coordenades Reals",
            numero=10,
            codiPostal="08001",
            barri="Centre",
        )

        self.assertIsNone(localitzacio.latitud)
        self.assertIsNone(localitzacio.longitud)



class BadgeModelTests(BaseTestData):
    def setUp(self):
        super().setUp()
        self.admin_badges = get_user_model().objects.create_user(
            email="admin.badges@test.com",
            password="TestPassword123",
        )
        self.localitzacio_badges = Localitzacio.objects.create(
            carrer="Carrer Badges",
            numero=1,
            codiPostal="08001",
        )
        self.edifici = Edifici.objects.create(
            localitzacio=self.localitzacio_badges,
            anyConstruccio=2000,
            superficieTotal=500,
            administradorFinca=self.admin_badges,
        )

    def test_crear_badge_definition(self):
        badge = BadgeDefinition.objects.create(
            code="OR_BHS",
            nom="Or BHS",
            descripcio="Edifici amb puntuació alta durant la temporada.",
            categoria=BadgeCategory.SCORE,
            scope=BadgeScope.SEASONAL,
            criteris={"bhs_min": 85},
        )

        self.assertEqual(badge.code, "OR_BHS")
        self.assertTrue(badge.activa)
        self.assertEqual(str(badge), "OR_BHS - Or BHS")

    def test_assignar_badge_permanent_unic_per_edifici(self):
        badge = BadgeDefinition.objects.create(
            code="DADES_VERIFICADES",
            nom="Dades verificades",
            categoria=BadgeCategory.DATA_QUALITY,
            scope=BadgeScope.PERMANENT,
        )

        BuildingBadge.objects.create(
            edifici=self.edifici,
            badge=badge,
            valor_snapshot=Decimal("100.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BuildingBadge.objects.create(
                    edifici=self.edifici,
                    badge=badge,
                    valor_snapshot=Decimal("100.00"),
                )

    def test_assignar_badge_estacional_amb_temporada(self):
        from apps.seasons.models import Temporada
        from datetime import date

        temporada = Temporada.objects.create(
            nom="Temporada Test",
            dataInici=date(2026, 1, 1),
            dataFi=date(2026, 12, 31),
        )
        badge = BadgeDefinition.objects.create(
            code="BRONZE_BHS",
            nom="Bronze BHS",
            categoria=BadgeCategory.SCORE,
            scope=BadgeScope.SEASONAL,
            criteris={"bhs_min": 50},
        )

        assignacio = BuildingBadge.objects.create(
            edifici=self.edifici,
            temporada=temporada,
            badge=badge,
            valor_snapshot=Decimal("62.50"),
            metadata={"font": "test"},
        )

        self.assertEqual(assignacio.temporada, temporada)
        self.assertEqual(assignacio.valor_snapshot, Decimal("62.50"))
        self.assertEqual(assignacio.metadata["font"], "test")
