from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from apps.buildings.models import Edifici, GrupComparable, Localitzacio
from apps.leagues.models import RankingHistorico
from apps.seasons.models import Temporada


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
