from datetime import date

from django.test import TestCase, RequestFactory, override_settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.admin.sites import AdminSite
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model

from .models import Temporada, EstatTemporada
from .admin import TemporadaAdmin
from apps.leagues.models import Lliga, RankingHistorico
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
            puntuacio_inicial=30,
            posicio=1,
            divisio='Bronze'
        )

        self.p2 = Participacio.objects.create(
            edifici=self.edifici_2,
            lliga=self.lliga_gold,
            puntuacio=95,
            puntuacio_inicial=50,
            posicio=1,
            divisio='Gold'
        )

        self.p3 = Participacio.objects.create(
            edifici=self.edifici_3,
            lliga=self.lliga_gold,
            puntuacio=70,
            puntuacio_inicial=10,
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


    def test_ranking_global_recalcula_posicions_per_temporada(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]

        self.assertEqual(results[0]["puntuacio"], 95)
        self.assertEqual(results[0]["posicio"], 1)

        self.assertEqual(results[1]["puntuacio"], 80)
        self.assertEqual(results[1]["posicio"], 2)

        self.assertEqual(results[2]["puntuacio"], 70)
        self.assertEqual(results[2]["posicio"], 3)

    def test_ranking_per_lliga_mante_posicions_correctes(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/'
            f'?league={self.lliga_gold.pk}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]

        self.assertEqual(len(results), 2)

        self.assertEqual(results[0]["puntuacio"], 95)
        self.assertEqual(results[0]["posicio"], 1)

        self.assertEqual(results[1]["puntuacio"], 70)
        self.assertEqual(results[1]["posicio"], 2)

    def test_ranking_per_grup_recalcula_posicions(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/?group=1'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]

        self.assertEqual(len(results), 2)

        self.assertEqual(results[0]["puntuacio"], 95)
        self.assertEqual(results[0]["posicio"], 1)

        self.assertEqual(results[1]["puntuacio"], 80)
        self.assertEqual(results[1]["posicio"], 2)

    def test_ranking_group_i_lliga_recalcula_posicions_correctament(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/'
            f'?group=1&league={self.lliga_gold.pk}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]

        self.assertEqual(len(results), 1)

        self.assertEqual(results[0]["puntuacio"], 95)
        self.assertEqual(results[0]["posicio"], 1)

    def test_ranking_search_recalcula_posicio_sobre_resultat_filtrat(self):

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/?search=gran'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]

        self.assertEqual(len(results), 1)

        self.assertEqual(results[0]["edifici"], self.edifici_3.idEdifici)
        self.assertEqual(results[0]["posicio"], 1)

    def test_ranking_no_utilitza_posicions_guardades_originals(self):

        self.assertEqual(self.p1.posicio, 1)
        self.assertEqual(self.p2.posicio, 1)

        response = self.client.get(
            f'/api/seasons/{self.temporada.pk}/ranking/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = response.data["results"]

        posicions = [r["posicio"] for r in results]

        self.assertEqual(posicions, [1, 2, 3])


@override_settings(REST_FRAMEWORK={
    "DEFAULT_AUTHENTICATION_CLASSES": (),
    "DEFAULT_PERMISSION_CLASSES": (),
    "DEFAULT_THROTTLE_CLASSES": (),
})
class TemporadaRankingProgresAPITest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user(email="ranking-progres@example.com")
        self.client.force_authenticate(user=self.user)

        self.group = GrupComparable.objects.create(
            idGrup=10,
            zonaClimatica='A',
            tipologia='Residencial',
            rangSuperficie='0-100'
        )

        self.temporada_2023 = Temporada.objects.create(
            nom='2023',
            dataInici='2023-01-01',
            dataFi='2023-12-31',
        )
        self.temporada_2024 = Temporada.objects.create(
            nom='2024',
            dataInici='2024-01-01',
            dataFi='2024-12-31',
        )
        self.temporada_2025 = Temporada.objects.create(
            nom='2025',
            dataInici='2025-01-01',
            dataFi='2025-12-31',
        )

        self.edificis = []
        for index, carrer in enumerate(['Aragó', 'Diagonal', 'Gran Via'], start=1):
            localitzacio = Localitzacio.objects.create(
                carrer=carrer,
                numero=index,
                codiPostal=f'0800{index}',
                barri='Centre'
            )
            self.edificis.append(Edifici.objects.create(
                anyConstruccio=2000 + index,
                tipologia='Residencial',
                superficieTotal=100 + index,
                nombrePlantes=1,
                reglament='CTE',
                orientacioPrincipal='Nord',
                grupComparable=self.group,
                localitzacio=localitzacio
            ))

        self._snapshot(self.edificis[0], self.temporada_2023, 40, 3, 'Bronze')
        self._snapshot(self.edificis[0], self.temporada_2024, 50, 2, 'Silver')
        self._snapshot(self.edificis[0], self.temporada_2025, 80, 1, 'Gold')

        self._snapshot(self.edificis[1], self.temporada_2023, 20, 2, 'Bronze')
        self._snapshot(self.edificis[1], self.temporada_2024, 65, 1, 'Silver')
        self._snapshot(self.edificis[1], self.temporada_2025, 75, 2, 'Silver')

        self._snapshot(self.edificis[2], self.temporada_2023, 35, 1, 'Bronze')
        self._snapshot(self.edificis[2], self.temporada_2024, 45, 3, 'Bronze')
        self._snapshot(self.edificis[2], self.temporada_2025, 75, 3, 'Silver')

    def _snapshot(self, edifici, temporada, puntuacio, posicio, divisio):
        return RankingHistorico.objects.create(
            edifici=edifici,
            temporada=temporada,
            categoria='PROGRES',
            puntuacio=puntuacio,
            posicio=posicio,
            divisio=divisio,
        )

    def test_ranking_progres_ordena_per_delta_i_desempata_establement(self):
        response = self.client.get(
            f'/api/seasons/{self.temporada_2025.pk}/ranking/progres/?window=3'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            [item['edifici'] for item in response.data],
            [
                self.edificis[1].idEdifici,
                self.edificis[0].idEdifici,
                self.edificis[2].idEdifici,
            ]
        )
        self.assertEqual([item['delta'] for item in response.data], [55, 40, 40])
        self.assertEqual([item['posicio'] for item in response.data], [1, 2, 3])
        self.assertEqual(response.data[0]['puntuacio_inicial'], 20)
        self.assertEqual(response.data[0]['puntuacio_actual'], 75)
        self.assertEqual(response.data[0]['divisio_actual'], 'Silver')
        self.assertEqual(len(response.data[0]['serie_temporal']), 3)

    def test_ranking_progres_window_limita_finestra_de_temporades(self):
        response = self.client.get(
            f'/api/seasons/{self.temporada_2025.pk}/ranking/progres/?window=2'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]['edifici'], self.edificis[0].idEdifici)
        self.assertEqual(response.data[0]['delta'], 30)
        self.assertEqual(
            [item['nom_temporada'] for item in response.data[0]['serie_temporal']],
            ['2024', '2025']
        )

    def test_ranking_progres_window_invalid_retorna_400(self):
        response = self.client.get(
            f'/api/seasons/{self.temporada_2025.pk}/ranking/progres/?window=0'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'window must be a positive integer')



class TemporadaOpenDataSnapshotsAPITest(APITestCase):
    """Regressió de temporada: Open Data, lligues de progrés i snapshots."""

    def setUp(self):
        self.client = APIClient()
        self.admin = make_superuser(email="season-opendata-admin@example.com")
        self.user = make_user(email="season-opendata-user@example.com")

        self.group = GrupComparable.objects.create(
            idGrup=501,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

    def _crear_edifici(self, carrer, numero, puntuacio_base=None, puntuacio_od=None, font_open_data=False):
        loc = Localitzacio.objects.create(
            carrer=carrer,
            numero=numero,
            codiPostal="08001",
            barri="Eixample",
        )
        return Edifici.objects.create(
            anyConstruccio=1990,
            tipologia="Residencial",
            superficieTotal=120,
            nombrePlantes=4,
            reglament="Desconegut",
            orientacioPrincipal="Sud",
            grupComparable=self.group,
            localitzacio=loc,
            puntuacioBase=puntuacio_base,
            puntuacioBaseOpenData=puntuacio_od,
            font_open_data=font_open_data,
        )

    def test_iniciar_temporada_crea_només_lligues_progres_i_inclou_opendata(self):
        temporada = Temporada.objects.create(
            nom="Temporada Open Data",
            dataInici="2027-01-01",
            dataFi="2027-12-31",
        )

        edifici_manual = self._crear_edifici(
            "Carrer Manual",
            1,
            puntuacio_base=80,
        )
        edifici_opendata = self._crear_edifici(
            "Carrer CEE",
            2,
            puntuacio_od=55,
            font_open_data=True,
        )
        edifici_sense_score = self._crear_edifici(
            "Carrer Sense Score",
            3,
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f"/api/seasons/{temporada.pk}/iniciar/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(
            Lliga.objects.filter(temporada=temporada, categoria="PROGRES").count(),
            3,
        )
        self.assertEqual(
            Lliga.objects.filter(temporada=temporada, categoria__in=["EFICIENCIA", "RESILIENCIA"]).count(),
            0,
        )

        participacio_manual = Participacio.objects.get(
            edifici=edifici_manual,
            lliga__temporada=temporada,
        )
        participacio_od = Participacio.objects.get(
            edifici=edifici_opendata,
            lliga__temporada=temporada,
        )

        self.assertEqual(participacio_manual.puntuacio, 80)
        self.assertEqual(participacio_manual.puntuacio_inicial, 80)

        self.assertEqual(participacio_od.puntuacio, 55)
        self.assertEqual(participacio_od.puntuacio_inicial, 55)

        self.assertFalse(
            Participacio.objects.filter(
                edifici=edifici_sense_score,
                lliga__temporada=temporada,
            ).exists()
        )

    def test_generar_snapshot_temporada_es_idempotent(self):
        temporada = Temporada.objects.create(
            nom="Temporada Snapshot",
            dataInici="2028-01-01",
            dataFi="2028-12-31",
        )
        edifici = self._crear_edifici(
            "Carrer Snapshot",
            10,
            puntuacio_base=70,
        )

        Temporada.objects.iniciar(temporada)

        from apps.leagues.services import generar_snapshots_temporada

        resum_1 = generar_snapshots_temporada(temporada)
        resum_2 = generar_snapshots_temporada(temporada)

        self.assertEqual(resum_1["items"], 1)
        self.assertEqual(resum_2["items"], 1)
        self.assertEqual(
            RankingHistorico.objects.filter(
                edifici=edifici,
                temporada=temporada,
                categoria="PROGRES",
            ).count(),
            1,
        )

    def test_tancar_temporada_genera_snapshot_automaticament(self):
        temporada = Temporada.objects.create(
            nom="Temporada Tancar Snapshot",
            dataInici="2029-01-01",
            dataFi="2029-12-31",
        )
        edifici = self._crear_edifici(
            "Carrer Tancar",
            20,
            puntuacio_base=60,
        )

        Temporada.objects.iniciar(temporada)
        participacio = Participacio.objects.get(
            edifici=edifici,
            lliga__temporada=temporada,
        )
        participacio.puntuacio = 88
        participacio.save(update_fields=["puntuacio"])

        Temporada.objects.tancar(temporada)

        snapshot = RankingHistorico.objects.get(
            edifici=edifici,
            temporada=temporada,
            categoria="PROGRES",
        )

        self.assertEqual(snapshot.puntuacio, 88)
        self.assertEqual(snapshot.posicio, 1)
        self.assertEqual(snapshot.divisio, participacio.divisio)

    def test_endpoint_anteriors_retorna_només_temporades_tancades(self):
        tancada = Temporada.objects.create(
            nom="Temporada Tancada",
            dataInici="2024-01-01",
            dataFi="2024-12-31",
            estat="TANCADA",
        )
        Temporada.objects.create(
            nom="Temporada Pendent",
            dataInici="2025-01-01",
            dataFi="2025-12-31",
            estat="PENDENT",
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/seasons/anteriors/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id_temporada"] for item in response.data], [tancada.id_temporada])

    def test_admin_pot_crear_i_iniciar_temporada_en_un_sol_endpoint(self):
        self._crear_edifici(
            "Carrer Crear Iniciar",
            30,
            puntuacio_base=66,
        )

        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/seasons/crear-i-iniciar/", {
            "nom": "Temporada Crear I Iniciar",
            "dataInici": "2030-01-01",
            "dataFi": "2030-12-31",
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["estat"], EstatTemporada.ACTIVA)
        self.assertEqual(
            Lliga.objects.filter(
                temporada_id=response.data["id_temporada"],
                categoria="PROGRES",
            ).count(),
            3,
        )
        self.assertEqual(
            Participacio.objects.filter(
                lliga__temporada_id=response.data["id_temporada"],
            ).count(),
            1,
        )
        self.assertEqual(
            RankingHistorico.objects.filter(
                temporada_id=response.data["id_temporada"],
                categoria="PROGRES",
            ).count(),
            1,
        )
