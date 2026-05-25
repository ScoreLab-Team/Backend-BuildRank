from django.test import TestCase
from rest_framework.test import APIClient, APITestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status

from apps.participations.models import Participacio
from apps.leagues.models import Lliga
from apps.seasons.models import Temporada
from apps.buildings.models import Edifici, GrupComparable, MilloraImplementada, CatalegMillora
from apps.accounts.models import RoleChoices
from datetime import timedelta
User = get_user_model()

class ParticipationManagerTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="Password123",
            first_name="Test"
        )
        self.user.profile.role = RoleChoices.ADMIN
        self.user.profile.save()

        self.client.force_authenticate(user=self.user)

        self.season = Temporada.objects.create(
            nom="Season",
            dataInici="2026-01-01",
            dataFi="2026-12-31",
            estat="ACTIVA"
        )

        self.league = Lliga.objects.create(
            nom="League",
            categoria="EFICIENCIA",
            divisio="Bronze",
            temporada=self.season
        )

        self.group = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100"
        )

        self.building = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=80,
            nombrePlantes=1,
            reglament="test",
            orientacioPrincipal="Nord",
            grupComparable=self.group
        )

    def test_create_participation(self):
        p = Participacio.objects.create_participation(self.building, self.league)

        self.assertEqual(p.puntuacio, 0)
        self.assertEqual(p.puntuacio_inicial, 0)
        self.assertEqual(p.posicio, 0)
        self.assertEqual(p.divisio, self.league.divisio)

    def test_update_score(self):
        p = Participacio.objects.create_participation(self.building, self.league)

        Participacio.objects.update_score(p, 95)

        p.refresh_from_db()
        self.assertEqual(p.puntuacio, 95)

    def test_get_segment_ranking(self):
        p1 = Participacio.objects.create_participation(self.building, self.league)
        p1.puntuacio = 50
        p1.save()

        ranking = Participacio.objects.get_segment_ranking(self.league, self.group)

        self.assertEqual(ranking.count(), 1)
        self.assertEqual(ranking.first(), p1)



class ParticipationAPITest(APITestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="admin@example.com",
            password="Password123",
            first_name="Test"
        )
        self.user.profile.role = RoleChoices.ADMIN
        self.user.profile.save()

        self.client.force_authenticate(user=self.user)

        self.season = Temporada.objects.create(
            nom="Season",
            dataInici="2026-01-01",
            dataFi="2026-12-31",
            estat="ACTIVA"
        )

        self.league = Lliga.objects.create(
            nom="League",
            categoria="EFICIENCIA",
            divisio="Bronze",
            temporada=self.season
        )

        self.group = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100"
        )

        self.building = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=80,
            nombrePlantes=1,
            reglament="test",
            orientacioPrincipal="Nord",
            grupComparable=self.group
        )

        self.participation = Participacio.objects.create(
            edifici=self.building,
            lliga=self.league,
            puntuacio=10,
            puntuacio_inicial=5,
            posicio=0,
            divisio="Bronze"
        )

    def test_update_score_endpoint(self):

        url = f"/api/participations/{self.participation.pk}/update_score/"
        response = self.client.post(url, {"puntuacio": 50}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.participation.refresh_from_db()
        self.assertEqual(self.participation.puntuacio, 50)



    def test_current_participation_success(self):

        url = "/api/participations/current/?edifici={}".format(
            self.building.idEdifici
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["edifici"], self.building.idEdifici)
        self.assertEqual(response.data["lliga"], self.league.id)
        self.assertEqual(response.data["puntuacio"], 10)
        self.assertEqual(response.data["puntuacio_inicial"], 5)
        self.assertEqual(response.data["divisio"], "Bronze")

    def test_current_participation_building_not_found(self):

        url = "/api/participations/current/?edifici=99999"

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_current_participation_not_found(self):

        empty_building = Edifici.objects.create(
            anyConstruccio=2010,
            tipologia="Residencial",
            superficieTotal=100,
            nombrePlantes=1,
            reglament="test2",
            orientacioPrincipal="Sud",
            grupComparable=self.group
        )

        url = "/api/participations/current/?edifici={}".format(
            empty_building.idEdifici
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"], "Participacio not found")

    def test_current_participation_missing_edifici(self):

        url = "/api/participations/current/"

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "edifici is required")

class ParticipationEvolutionAPITest(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            email="admin@example.com",
            password="Password123",
            first_name="Test"
        )

        self.user.profile.role = RoleChoices.ADMIN
        self.user.profile.save()

        self.client.force_authenticate(user=self.user)

        self.group = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100"
        )

        self.building = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=80,
            nombrePlantes=1,
            reglament="test",
            orientacioPrincipal="Nord",
            grupComparable=self.group
        )

        self.season_1 = Temporada.objects.create(
            nom="2024",
            dataInici="2024-01-01",
            dataFi="2024-12-31",
            estat="TANCADA"
        )

        self.season_2 = Temporada.objects.create(
            nom="2025",
            dataInici="2025-01-01",
            dataFi="2025-12-31",
            estat="TANCADA"
        )

        self.league_1 = Lliga.objects.create(
            nom="Bronze",
            categoria="EFICIENCIA",
            divisio="Bronze",
            temporada=self.season_1
        )

        self.league_2 = Lliga.objects.create(
            nom="Silver",
            categoria="EFICIENCIA",
            divisio="Silver",
            temporada=self.season_2
        )

        self.participation_1 = Participacio.objects.create(
            edifici=self.building,
            lliga=self.league_1,
            puntuacio=70,
            puntuacio_inicial=50,
            posicio=1,
            divisio="Bronze"
        )

        self.participation_2 = Participacio.objects.create(
            edifici=self.building,
            lliga=self.league_2,
            puntuacio=90,
            puntuacio_inicial=70,
            posicio=1,
            divisio="Silver"
        )

    def test_evolucio_puntuacio_success(self):

        url = (
            "/api/participations/evolucio_puntuacio/"
            f"?edifici={self.building.idEdifici}"
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 2)

        self.assertEqual(response.data[0]["nom_temporada"], "2025")
        self.assertEqual(response.data[0]["puntuacio_inicial"], 70)
        self.assertEqual(response.data[0]["puntuacio_actual"], 90)
        self.assertEqual(response.data[0]["delta_puntuacio"], 20)

        self.assertEqual(response.data[1]["nom_temporada"], "2024")
        self.assertEqual(response.data[1]["puntuacio_inicial"], 50)
        self.assertEqual(response.data[1]["puntuacio_actual"], 70)
        self.assertEqual(response.data[1]["delta_puntuacio"], 20)



    def test_evolucio_puntuacio_limit_temporades(self):

        url = (
            "/api/participations/evolucio_puntuacio/"
            f"?edifici={self.building.idEdifici}&temporades=1"
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 1)

        self.assertEqual(response.data[0]["nom_temporada"], "2025")

    def test_evolucio_puntuacio_missing_edifici(self):

        response = self.client.get(
            "/api/participations/evolucio_puntuacio/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["error"],
            "edifici is required"
        )

    def test_evolucio_puntuacio_building_not_found(self):

        response = self.client.get(
            "/api/participations/evolucio_puntuacio/?edifici=99999"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND
        )

    def test_evolucio_puntuacio_empty_history(self):

        empty_building = Edifici.objects.create(
            anyConstruccio=2010,
            tipologia="Residencial",
            superficieTotal=100,
            nombrePlantes=1,
            reglament="test2",
            orientacioPrincipal="Sud",
            grupComparable=self.group
        )

        response = self.client.get(
            "/api/participations/evolucio_puntuacio/"
            f"?edifici={empty_building.idEdifici}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data, [])

class ParticipationAnnualProgressAPITest(APITestCase):
    def setUp(self):

        self.client = APIClient()

        self.user = User.objects.create_user(
            email="admin@example.com",
            password="Password123",
            first_name="Test"
        )

        self.user.profile.role = RoleChoices.ADMIN
        self.user.profile.save()

        self.client.force_authenticate(user=self.user)

        self.group = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100"
        )

        self.building = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=80,
            nombrePlantes=1,
            reglament="test",
            orientacioPrincipal="Nord",
            grupComparable=self.group
        )

        today = timezone.now().date()



        self.season_old = Temporada.objects.create(
            nom="Old Season",
            dataInici=today - timedelta(days=500),
            dataFi=today - timedelta(days=450),
            estat="TANCADA"
        )

        self.season_start = Temporada.objects.create(
            nom="Start Season",
            dataInici=today - timedelta(days=300),
            dataFi=today - timedelta(days=250),
            estat="TANCADA"
        )

        self.season_middle = Temporada.objects.create(
            nom="Middle Season",
            dataInici=today - timedelta(days=150),
            dataFi=today - timedelta(days=100),
            estat="TANCADA"
        )

        self.season_current = Temporada.objects.create(
            nom="Current Season",
            dataInici=today - timedelta(days=30),
            dataFi=today + timedelta(days=30),
            estat="ACTIVA"
        )



        self.league_old = Lliga.objects.create(
            nom="Old League",
            categoria="EFICIENCIA",
            divisio="Bronze",
            temporada=self.season_old
        )

        self.league_start = Lliga.objects.create(
            nom="Start League",
            categoria="EFICIENCIA",
            divisio="Bronze",
            temporada=self.season_start
        )

        self.league_middle = Lliga.objects.create(
            nom="Middle League",
            categoria="EFICIENCIA",
            divisio="Silver",
            temporada=self.season_middle
        )

        self.league_current = Lliga.objects.create(
            nom="Current League",
            categoria="EFICIENCIA",
            divisio="Gold",
            temporada=self.season_current
        )




        Participacio.objects.create(
            edifici=self.building,
            lliga=self.league_old,
            puntuacio=20,
            puntuacio_inicial=10,
            posicio=5,
            divisio="Bronze"
        )


        self.participation_start = Participacio.objects.create(
            edifici=self.building,
            lliga=self.league_start,
            puntuacio=50,
            puntuacio_inicial=40,
            posicio=3,
            divisio="Bronze"
        )

        self.participation_middle = Participacio.objects.create(
            edifici=self.building,
            lliga=self.league_middle,
            puntuacio=65,
            puntuacio_inicial=50,
            posicio=2,
            divisio="Silver"
        )


        self.participation_current = Participacio.objects.create(
            edifici=self.building,
            lliga=self.league_current,
            puntuacio=80,
            puntuacio_inicial=65,
            posicio=1,
            divisio="Gold"
        )



        self.improvement = CatalegMillora.objects.create(
            nom="Aïllament façana",
            categoria="envolupant",
            costMinim=1000,
            costMaxim=5000,
            estalviEnergeticEstimat=20,
            impactePunts=10
        )


        self.implemented_improvement = MilloraImplementada.objects.create(
            dataExecucio=today - timedelta(days=60),
            costReal=12000,
            estatValidacio="Validada",
            millora=self.improvement,
            edifici=self.building
        )

    def test_progres_anual_success(self):

        response = self.client.get(
            "/api/participations/progres_anual/"
            f"?edifici={self.building.idEdifici}"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )



        self.assertEqual(
            response.data["temporada_inicial"]["nom"],
            "Start Season"
        )

        self.assertEqual(
            response.data["temporada_actual"]["nom"],
            "Current Season"
        )



        self.assertEqual(
            response.data["puntuacio"]["inicial"],
            50
        )

        self.assertEqual(
            response.data["puntuacio"]["actual"],
            80
        )

        self.assertEqual(
            response.data["puntuacio"]["delta"],
            30
        )



        self.assertEqual(
            response.data["tendencia"],
            "millora"
        )



        self.assertEqual(
            response.data["resum"]["millores_implementades"],
            1
        )

        self.assertEqual(
            len(response.data["millores"]),
            1
        )

        self.assertEqual(
            response.data["millores"][0]["nom"],
            "Aïllament façana"
        )

    def test_progres_anual_missing_edifici(self):

        response = self.client.get(
            "/api/participations/progres_anual/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

        self.assertEqual(
            response.data["error"],
            "edifici is required"
        )

    def test_progres_anual_building_not_found(self):

        response = self.client.get(
            "/api/participations/progres_anual/"
            "?edifici=99999"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND
        )

    def test_progres_anual_no_recent_participations(self):

        empty_building = Edifici.objects.create(
            anyConstruccio=2010,
            tipologia="Residencial",
            superficieTotal=100,
            nombrePlantes=1,
            reglament="test2",
            orientacioPrincipal="Sud",
            grupComparable=self.group
        )

        old_season = Temporada.objects.create(
            nom="Very Old",
            dataInici=timezone.now().date() - timedelta(days=800),
            dataFi=timezone.now().date() - timedelta(days=700),
            estat="TANCADA"
        )

        old_league = Lliga.objects.create(
            nom="Old League",
            categoria="EFICIENCIA",
            divisio="Bronze",
            temporada=old_season
        )

        Participacio.objects.create(
            edifici=empty_building,
            lliga=old_league,
            puntuacio=10,
            puntuacio_inicial=5,
            posicio=5,
            divisio="Bronze"
        )

        response = self.client.get(
            "/api/participations/progres_anual/"
            f"?edifici={empty_building.idEdifici}"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        self.assertEqual(
            response.data["estat"],
            "sense_dades"
        )

    def test_progres_anual_estancament(self):

        self.participation_current.puntuacio = 51
        self.participation_current.save()

        response = self.client.get(
            "/api/participations/progres_anual/"
            f"?edifici={self.building.idEdifici}"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        self.assertEqual(
            response.data["tendencia"],
            "estancament"
        )

    def test_progres_anual_empitjorament(self):

        self.participation_current.puntuacio = 40
        self.participation_current.save()

        response = self.client.get(
            "/api/participations/progres_anual/"
            f"?edifici={self.building.idEdifici}"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK
        )

        self.assertEqual(
            response.data["tendencia"],
            "empitjorament"
        )