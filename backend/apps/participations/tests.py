from django.test import TestCase
from rest_framework.test import APIClient, APITestCase
from django.contrib.auth import get_user_model
from rest_framework import status

from apps.participations.models import Participacio
from apps.leagues.models import Lliga
from apps.seasons.models import Temporada
from apps.buildings.models import Edifici, GrupComparable
from apps.accounts.models import RoleChoices

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