from datetime import date

from django.test import TestCase, RequestFactory
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.admin.sites import AdminSite
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model

from .models import Temporada, EstatTemporada
from .admin import TemporadaAdmin
from apps.leagues.models import Lliga
from apps.participations.models import Participacio
from apps.buildings.models import Edifici, GrupComparable, Localitzacio

User = get_user_model()

SEASON_DATA = {
    'nom': 'Temporada Test',
    'dataInici': date(2026, 1, 1),
    'dataFi': date(2026, 12, 31),
}


def make_superuser(email='super@example.com'):
    return User.objects.create_superuser(email=email, password='Password123')


def make_user(email='user@example.com'):
    return User.objects.create_user(email=email, password='Password123', first_name='User')


class EstatTemporadaManagerTest(TestCase):
    """Tests unitaris del SeasonManager."""

    def setUp(self):
        self.temporada = Temporada.objects.create(**SEASON_DATA)

    def test_temporada_creada_en_estat_pendent(self):
        self.assertEqual(self.temporada.estat, EstatTemporada.PENDENT)
        self.assertFalse(self.temporada.activa)

    def test_iniciar_temporada_pendent(self):
        Temporada.objects.iniciar(self.temporada)
        self.temporada.refresh_from_db()
        self.assertEqual(self.temporada.estat, EstatTemporada.ACTIVA)
        self.assertTrue(self.temporada.activa)

    def test_iniciar_temporada_activa_falla(self):
        Temporada.objects.iniciar(self.temporada)
        with self.assertRaises(ValueError):
            Temporada.objects.iniciar(self.temporada)

    def test_iniciar_temporada_tancada_falla(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        with self.assertRaises(ValueError):
            Temporada.objects.iniciar(self.temporada)

    def test_iniciar_quan_ja_existeix_activa_falla(self):
        Temporada.objects.iniciar(self.temporada)
        altra = Temporada.objects.create(
            nom='Altra temporada', dataInici='2027-01-01', dataFi='2027-12-31'
        )
        with self.assertRaises(ValueError):
            Temporada.objects.iniciar(altra)

    def test_tancar_temporada_activa(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        self.temporada.refresh_from_db()
        self.assertEqual(self.temporada.estat, EstatTemporada.TANCADA)
        self.assertFalse(self.temporada.activa)

    def test_tancar_temporada_pendent_falla(self):
        with self.assertRaises(ValueError):
            Temporada.objects.tancar(self.temporada)

    def test_tancar_temporada_tancada_falla(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        with self.assertRaises(ValueError):
            Temporada.objects.tancar(self.temporada)

    def test_is_active_temporada_activa_dins_rang(self):
        Temporada.objects.iniciar(self.temporada)
        self.assertTrue(Temporada.objects.is_active(self.temporada))

    def test_is_active_temporada_pendent(self):
        self.assertFalse(Temporada.objects.is_active(self.temporada))

    def test_is_active_temporada_tancada(self):
        Temporada.objects.iniciar(self.temporada)
        Temporada.objects.tancar(self.temporada)
        self.assertFalse(Temporada.objects.is_active(self.temporada))


class TemporadaAPITest(APITestCase):
    """Tests dels endpoints REST de temporades."""

    def setUp(self):
        self.client = APIClient()
        self.admin = make_superuser()
        self.user = make_user()
        self.temporada = Temporada.objects.create(**SEASON_DATA)

    # --- Creació ---

    def test_admin_pot_crear_temporada(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/seasons/', {
            'nom': 'Nova temporada',
            'dataInici': '2027-01-01',
            'dataFi': '2027-12-31',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['estat'], EstatTemporada.PENDENT)

    def test_usuari_no_admin_no_pot_crear_temporada(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/seasons/', {
            'nom': 'Nova temporada',
            'dataInici': '2027-01-01',
            'dataFi': '2027-12-31',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_autenticat_no_pot_crear_temporada(self):
        response = self.client.post('/api/seasons/', {
            'nom': 'Nova temporada',
            'dataInici': '2027-01-01',
            'dataFi': '2027-12-31',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Llistat i detall (autenticats) ---

    def test_usuari_autenticat_pot_llistar_temporades(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/seasons/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_usuari_autenticat_pot_veure_detall(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f'/api/seasons/{self.temporada.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('estat', response.data)
        self.assertIn('activa', response.data)

    # --- Iniciar ---

    def test_admin_pot_iniciar_temporada_pendent(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['estat'], EstatTemporada.ACTIVA)
        self.assertTrue(response.data['activa'])

    def test_iniciar_temporada_activa_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_iniciar_temporada_tancada_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_iniciar_quan_ja_hi_ha_activa_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        altra = Temporada.objects.create(
            nom='Altra temporada', dataInici='2027-01-01', dataFi='2027-12-31'
        )
        response = self.client.post(f'/api/seasons/{altra.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_usuari_no_admin_no_pot_iniciar(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- Tancar ---

    def test_admin_pot_tancar_temporada_activa(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['estat'], EstatTemporada.TANCADA)
        self.assertFalse(response.data['activa'])

    def test_tancar_temporada_pendent_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_tancar_temporada_tancada_retorna_400(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_usuari_no_admin_no_pot_tancar(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/seasons/{self.temporada.pk}/iniciar/')
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f'/api/seasons/{self.temporada.pk}/tancar/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SeasonManagerExtraTest(TestCase):
    """Tests addicionals del SeasonManager per cobrir create_season i is_active fora de rang."""

    def test_create_season(self):
        t = Temporada.objects.create_season('T1', date(2028, 1, 1), date(2028, 12, 31))
        self.assertEqual(t.nom, 'T1')
        self.assertEqual(t.estat, EstatTemporada.PENDENT)

    def test_is_active_activa_fora_de_rang(self):
        t = Temporada.objects.create(
            nom='Antiga', dataInici=date(2020, 1, 1), dataFi=date(2020, 12, 31), estat='ACTIVA'
        )
        self.assertFalse(Temporada.objects.is_active(t))


class TemporadaAdminActionTest(TestCase):
    """Tests de les accions d'admin de Temporada."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='adminact@example.com', password='Password123'
        )
        self.temporada = Temporada.objects.create(**SEASON_DATA)

    def _do_action(self, action_name, queryset):
        factory = RequestFactory()
        request = factory.post('/')
        request.user = self.admin_user
        setattr(request, 'session', 'session')
        storage = FallbackStorage(request)
        setattr(request, '_messages', storage)
        admin_obj = TemporadaAdmin(Temporada, AdminSite())
        getattr(admin_obj, action_name)(request, queryset)
        return list(storage)

    def test_action_iniciar_success(self):
        msgs = self._do_action('action_iniciar', Temporada.objects.filter(pk=self.temporada.pk))
        self.temporada.refresh_from_db()
        self.assertEqual(self.temporada.estat, EstatTemporada.ACTIVA)
        self.assertTrue(any(m.level_tag == 'success' for m in msgs))

    def test_action_iniciar_error(self):
        Temporada.objects.iniciar(self.temporada)
        msgs = self._do_action('action_iniciar', Temporada.objects.filter(pk=self.temporada.pk))
        self.assertTrue(any(m.level_tag == 'error' for m in msgs))

    def test_action_iniciar_mixed(self):
        altra = Temporada.objects.create(
            nom='Altra', dataInici='2027-01-01', dataFi='2027-12-31', estat='TANCADA'
        )
        qs = Temporada.objects.filter(pk__in=[self.temporada.pk, altra.pk])
        msgs = self._do_action('action_iniciar', qs)
        levels = {m.level_tag for m in msgs}
        self.assertIn('success', levels)
        self.assertIn('error', levels)

    def test_action_tancar_success(self):
        Temporada.objects.iniciar(self.temporada)
        msgs = self._do_action('action_tancar', Temporada.objects.filter(pk=self.temporada.pk))
        self.temporada.refresh_from_db()
        self.assertEqual(self.temporada.estat, EstatTemporada.TANCADA)
        self.assertTrue(any(m.level_tag == 'success' for m in msgs))

    def test_action_tancar_error(self):
        msgs = self._do_action('action_tancar', Temporada.objects.filter(pk=self.temporada.pk))
        self.assertTrue(any(m.level_tag == 'error' for m in msgs))

    def test_action_tancar_mixed(self):
        Temporada.objects.iniciar(self.temporada)
        altra = Temporada.objects.create(
            nom='Altra', dataInici='2027-01-01', dataFi='2027-12-31', estat='PENDENT'
        )
        qs = Temporada.objects.filter(pk__in=[self.temporada.pk, altra.pk])
        msgs = self._do_action('action_tancar', qs)
        levels = {m.level_tag for m in msgs}
        self.assertIn('success', levels)
        self.assertIn('error', levels)


class TemporadaAPIExtraTest(APITestCase):
    """Tests addicionals dels endpoints REST: update, delete i accés no autenticat."""

    def setUp(self):
        self.client = APIClient()
        self.admin = make_superuser()
        self.user = make_user()
        self.temporada = Temporada.objects.create(**SEASON_DATA)

    def test_no_autenticat_no_pot_llistar(self):
        response = self.client.get('/api/seasons/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_autenticat_no_pot_veure_detall(self):
        response = self.client.get(f'/api/seasons/{self.temporada.pk}/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_pot_actualitzar_temporada(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f'/api/seasons/{self.temporada.pk}/', {'nom': 'Nou nom'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['nom'], 'Nou nom')

    def test_no_admin_no_pot_actualitzar(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(f'/api/seasons/{self.temporada.pk}/', {'nom': 'Nou nom'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_pot_eliminar_temporada(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/seasons/{self.temporada.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_no_admin_no_pot_eliminar(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(f'/api/seasons/{self.temporada.pk}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)



class TemporadaRankingAPITest(APITestCase):
    """Tests del nou endpoint global de ranking per temporada."""

    def setUp(self):
        self.client = APIClient()

        self.user = make_user()
        self.client.force_authenticate(user=self.user)

        self.temporada = Temporada.objects.create(
            nom='Temporada Ranking',
            dataInici='2026-01-01',
            dataFi='2026-12-31',
        )

        self.group_a = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica='A',
            tipologia='Residencial',
            rangSuperficie='0-100'
        )

        self.group_b = GrupComparable.objects.create(
            idGrup=2,
            zonaClimatica='B',
            tipologia='Residencial',
            rangSuperficie='0-100'
        )

        self.lliga_bronze = Lliga.objects.create(
            nom='Bronze',
            categoria='EFICIENCIA',
            divisio='Bronze',
            temporada=self.temporada
        )

        self.lliga_gold = Lliga.objects.create(
            nom='Gold',
            categoria='EFICIENCIA',
            divisio='Gold',
            temporada=self.temporada
        )




        self.loc_1 = Localitzacio.objects.create(
            carrer='Carrer Aragó',
            numero=1,
            codiPostal='08001',
            barri='Eixample'
        )

        self.loc_2 = Localitzacio.objects.create(
            carrer='Diagonal',
            numero=2,
            codiPostal='08002',
            barri='Les Corts'
        )

        self.loc_3 = Localitzacio.objects.create(
            carrer='Gran Via',
            numero=3,
            codiPostal='08003',
            barri='Centre'
        )

        self.edifici_1 = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia='Residencial',
            superficieTotal=100,
            nombrePlantes=1,
            reglament='CTE',
            orientacioPrincipal='Nord',
            grupComparable=self.group_a,
            localitzacio=self.loc_1
        )

        self.edifici_2 = Edifici.objects.create(
            anyConstruccio=2005,
            tipologia='Residencial',
            superficieTotal=120,
            nombrePlantes=2,
            reglament='CTE',
            orientacioPrincipal='Sud',
            grupComparable=self.group_a,
            localitzacio=self.loc_2
        )

        self.edifici_3 = Edifici.objects.create(
            anyConstruccio=2010,
            tipologia='Residencial',
            superficieTotal=150,
            nombrePlantes=3,
            reglament='CTE',
            orientacioPrincipal='Est',
            grupComparable=self.group_b,
            localitzacio=self.loc_3
        )




        self.p1 = Participacio.objects.create(
            edifici=self.edifici_1,
            lliga=self.lliga_bronze,
            puntuacio=80,
            posicio=1,
            divisio='Bronze'
        )

        self.p2 = Participacio.objects.create(
            edifici=self.edifici_2,
            lliga=self.lliga_gold,
            puntuacio=95,
            posicio=1,
            divisio='Gold'
        )

        self.p3 = Participacio.objects.create(
            edifici=self.edifici_3,
            lliga=self.lliga_gold,
            puntuacio=70,
            posicio=2,
            divisio='Gold'
        )

    def test_ranking_global_retorna_participacions_de_diferents_lligues(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']

        self.assertEqual(len(results), 3)

        lligues = {r['nom_lliga'] for r in results}

        self.assertIn('Bronze', lligues)
        self.assertIn('Gold', lligues)

    def test_filter_group(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/?group=1'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']

        self.assertEqual(len(results), 2)

        edificis = [r['edifici'] for r in results]

        self.assertIn(self.edifici_1.idEdifici, edificis)
        self.assertIn(self.edifici_2.idEdifici, edificis)
        self.assertNotIn(self.edifici_3.idEdifici, edificis)

    def test_filter_group_invalid_returns_404(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/?group=999'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_league(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/'
            f'?league={self.lliga_gold.pk}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']

        self.assertEqual(len(results), 2)

        for item in results:
            self.assertEqual(item['lliga'], self.lliga_gold.id)
            self.assertEqual(item['nom_lliga'], self.lliga_gold.nom)

    def test_filter_invalid_league_returns_404(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/?league=999'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_search_by_street(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/?search=arag'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data['results']

        self.assertEqual(len(results), 1)

        self.assertEqual(results[0]['edifici'], self.edifici_1.idEdifici)
        self.assertIn('Aragó', results[0]['adreca'])

    def test_ranking_pagination(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/'
            f'?page=1&page_size=2'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data['results']), 2)

        self.assertIn('count', response.data)
        self.assertEqual(response.data['count'], 3)

        self.assertIn('next', response.data)


    def test_posicio_edifici_dins_top_per_defecte(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_2.pk}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["esta_en_top"], True)
        self.assertEqual(response.data["top_objectiu"], 3)
        self.assertEqual(response.data["posicio"], 1)
        self.assertEqual(response.data["scope"], "lliga")

    def test_posicio_edifici_fora_top_calcula_punts(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_3.pk}&top=1'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["esta_en_top"], False)
        self.assertEqual(response.data["top_objectiu"], 1)

        self.assertGreaterEqual(response.data["punts_per_top"], 0)

    def test_posicio_edifici_segmentat_grup_a(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_1.pk}&group=true'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(response.data["grup_comparat"])
        self.assertEqual(response.data["grup_utilitzat"], self.group_a.idGrup)

        self.assertIn(response.data["posicio"], [1, 2])

    def test_posicio_edifici_no_segmentat_global(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_1.pk}&group_filter=false'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(response.data["grup_comparat"])

    def test_posicio_edifici_no_existeix_retorna_404(self):

        fake_building_id = 99999

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={fake_building_id}'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_posicio_edifici_top_mes_gran_que_ranking(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_1.pk}&top=999'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)


        self.assertIsNotNone(response.data["posicio"])
        self.assertEqual(response.data["punts_per_top"], 0)

    def test_posicio_edifici_scope_lliga(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_1.pk}&scope=lliga'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["scope"], "lliga")
        self.assertIn("lliga", response.data)
        self.assertEqual(response.data["lliga"]["id"], self.lliga_bronze.id)

    def test_posicio_edifici_scope_temporada(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_1.pk}&scope=temporada'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["scope"], "temporada")

        self.assertIn(response.data["posicio"], range(1, 1000))

    def test_posicio_edifici_scope_i_segment_combined(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_1.pk}&scope=temporada&group=true'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["scope"], "temporada")
        self.assertTrue(response.data["grup_comparat"])

        self.assertIn("grup_utilitzat", response.data)

        self.assertEqual(
            response.data["grup_utilitzat"],
            self.group_a.idGrup
        )

    def test_scope_no_trenca_segment(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/posicio_edifici/'
            f'?edifici={self.edifici_2.pk}&scope=lliga&group=true'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(response.data["grup_comparat"])
        self.assertIn("grup_utilitzat", response.data)