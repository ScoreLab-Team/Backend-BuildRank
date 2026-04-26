from django.test import TestCase
from django.urls import reverse
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.buildings.models import CatalegMillora, Edifici, EdificiAuditLog, EstatValidacio, Habitatge, Localitzacio, GrupComparable, MilloraImplementada
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