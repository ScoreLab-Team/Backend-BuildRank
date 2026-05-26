from django.contrib.auth import get_user_model
from django.test import override_settings, TestCase
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.buildings.models import Edifici, GrupComparable, Localitzacio
from apps.leagues.models import RankingHistorico
from apps.seasons.models import Temporada
from apps.leagues.models import Lliga
from apps.participations.models import Participacio
from apps.leagues.services import generar_snapshots_temporada
from apps.leagues.models import CategoriaRanking


User = get_user_model()


def make_user(email="leagues@example.com"):
    return User.objects.create_user(
        email=email,
        password="Password123",
        first_name="User",
    )


@override_settings(REST_FRAMEWORK={
    "DEFAULT_AUTHENTICATION_CLASSES": (),
    "DEFAULT_PERMISSION_CLASSES": (),
    "DEFAULT_THROTTLE_CLASSES": (),
})
class EvolucioRankingHistoricoAPITest(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=make_user())

        self.group = GrupComparable.objects.create(
            idGrup=50,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100",
        )
        self.localitzacio = Localitzacio.objects.create(
            carrer="Carrer Test",
            numero=1,
            codiPostal="08001",
            barri="Centre",
        )
        self.edifici = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=100,
            nombrePlantes=1,
            reglament="CTE",
            orientacioPrincipal="Nord",
            grupComparable=self.group,
            localitzacio=self.localitzacio,
        )

        self.temporades = [
            Temporada.objects.create(
                nom=f"Temporada {year}",
                dataInici=f"{year}-01-01",
                dataFi=f"{year}-12-31",
            )
            for year in [2023, 2024, 2025]
        ]

        for index, temporada in enumerate(self.temporades, start=1):
            RankingHistorico.objects.create(
                edifici=self.edifici,
                temporada=temporada,
                categoria="PROGRES",
                puntuacio=index * 10,
                posicio=index,
                divisio="Bronze",
            )

    def test_evolucio_sense_limit_mante_historial_complet(self):
        response = self.client.get(
            "/api/leagues/evolucio/"
            f"?edifici={self.edifici.idEdifici}&categoria=PROGRES"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["nom_temporada"] for item in response.data],
            ["Temporada 2023", "Temporada 2024", "Temporada 2025"],
        )

    def test_evolucio_limit_retorna_ultimes_temporades_en_ordre_cronologic(self):
        response = self.client.get(
            "/api/leagues/evolucio/"
            f"?edifici={self.edifici.idEdifici}&categoria=PROGRES&limit=2"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["nom_temporada"] for item in response.data],
            ["Temporada 2024", "Temporada 2025"],
        )

    def test_evolucio_limit_invalid_retorna_400(self):
        response = self.client.get(
            "/api/leagues/evolucio/"
            f"?edifici={self.edifici.idEdifici}&categoria=PROGRES&limit=abc"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"], "limit must be a positive integer")

class LeagueManagerTest(TestCase):

    def setUp(self):

        self.temporada = Temporada.objects.create(
            nom="Temporada Progress",
            dataInici="2025-01-01",
            dataFi="2025-12-31",
            estat="ACTIVA",
        )

        self.group_1 = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100",
        )

        self.group_2 = GrupComparable.objects.create(
            idGrup=2,
            zonaClimatica="B",
            tipologia="Residencial",
            rangSuperficie="100-200",
        )

        self.building_1 = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=80,
            nombrePlantes=1,
            reglament="CTE",
            orientacioPrincipal="Nord",
            grupComparable=self.group_1,
        )

        self.building_2 = Edifici.objects.create(
            anyConstruccio=2010,
            tipologia="Residencial",
            superficieTotal=120,
            nombrePlantes=2,
            reglament="CTE",
            orientacioPrincipal="Sud",
            grupComparable=self.group_1,
        )

        self.building_3 = Edifici.objects.create(
            anyConstruccio=2015,
            tipologia="Residencial",
            superficieTotal=150,
            nombrePlantes=3,
            reglament="CTE",
            orientacioPrincipal="Est",
            grupComparable=self.group_2,
        )

    def test_create_progress_leagues_creates_three_divisions(self):

        leagues = Lliga.objects.create_progress_leagues(self.temporada)

        self.assertEqual(len(leagues), 3)

        self.assertEqual(leagues[0].divisio, "Bronze")
        self.assertEqual(leagues[1].divisio, "Silver")
        self.assertEqual(leagues[2].divisio, "Gold")

    def test_create_progress_leagues_sets_categoria_progres(self):

        leagues = Lliga.objects.create_progress_leagues(self.temporada)

        for league in leagues:
            self.assertEqual(league.categoria, "PROGRES")

    def test_create_progress_leagues_assigns_temporada(self):

        leagues = Lliga.objects.create_progress_leagues(self.temporada)

        for league in leagues:
            self.assertEqual(league.temporada, self.temporada)

class GenerarSnapshotsTemporadaTest(TestCase):

    def setUp(self):
        self.temporada = Temporada.objects.create(
            nom="Snapshot Season",
            dataInici="2025-01-01",
            dataFi="2025-12-31",
            estat="ACTIVA",
        )

        self.group = GrupComparable.objects.create(
            idGrup=10,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100",
        )

        self.building_1 = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=80,
            nombrePlantes=1,
            reglament="CTE",
            orientacioPrincipal="Nord",
            grupComparable=self.group,
        )

        self.building_2 = Edifici.objects.create(
            anyConstruccio=2010,
            tipologia="Residencial",
            superficieTotal=120,
            nombrePlantes=2,
            reglament="CTE",
            orientacioPrincipal="Sud",
            grupComparable=self.group,
        )

        self.lliga = Lliga.objects.create(
            nom="Lliga PROGRES Bronze",
            categoria=CategoriaRanking.PROGRES,
            divisio="Bronze",
            temporada=self.temporada,
        )

    def test_generar_snapshots_creates_ranking_historico(self):

        Participacio.objects.create(
            edifici=self.building_1,
            lliga=self.lliga,
            puntuacio=80,
            puntuacio_inicial=0,
            posicio=0,
            divisio="Bronze",
        )

        Participacio.objects.create(
            edifici=self.building_2,
            lliga=self.lliga,
            puntuacio=60,
            puntuacio_inicial=0,
            posicio=0,
            divisio="Bronze",
        )

        result = generar_snapshots_temporada(self.temporada)

        self.assertGreaterEqual(result["lligues_processades"], 1)
        self.assertEqual(result["items"], 2)

        snapshots = RankingHistorico.objects.filter(temporada=self.temporada)

        self.assertEqual(snapshots.count(), 2)

        # ordre ranking correcte
        self.assertEqual(
            snapshots.get(edifici=self.building_1).posicio,
            1
        )
        self.assertEqual(
            snapshots.get(edifici=self.building_2).posicio,
            2
        )

    def test_generar_snapshots_updates_existing_records(self):

        Participacio.objects.create(
            edifici=self.building_1,
            lliga=self.lliga,
            puntuacio=100,
            puntuacio_inicial=0,
            posicio=5,
            divisio="OldDiv",
        )

        generar_snapshots_temporada(self.temporada)

        # update puntuació
        Participacio.objects.filter(edifici=self.building_1).update(
            puntuacio=200
        )

        generar_snapshots_temporada(self.temporada)

        snapshot = RankingHistorico.objects.get(
            edifici=self.building_1,
            temporada=self.temporada
        )

        self.assertEqual(snapshot.puntuacio, 200)

    def test_generar_snapshots_only_processes_progres(self):

        Lliga.objects.create(
            nom="Ignore League",
            categoria="EFICIENCIA",
            divisio="Silver",
            temporada=self.temporada,
        )

        result = generar_snapshots_temporada(self.temporada)

        self.assertGreaterEqual(result["lligues_processades"], 1)