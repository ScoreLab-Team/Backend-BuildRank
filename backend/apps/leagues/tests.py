from django.test import TestCase
from rest_framework.test import APIClient

from apps.leagues.models import Lliga
from apps.seasons.models import Temporada
from apps.buildings.models import Edifici, GrupComparable
from apps.participation.models import Participacio


class RankingSegmentationTest(TestCase):

    def setUp(self):
        self.season = Temporada.objects.create(
            nom="Test Season",
            dataInici="2026-01-01",
            dataFi="2026-12-31",
            activa=True
        )

        self.league = Lliga.objects.create(
            nom="Test League",
            categoria="EFICIENCIA",
            divisio="Bronze",
            temporada=self.season
        )

        self.group_a = GrupComparable.objects.create(
            idGrup=1,
            zonaClimatica="A",
            tipologia="Residencial",
            rangSuperficie="0-100"
        )

        self.group_b = GrupComparable.objects.create(
            idGrup=2,
            zonaClimatica="B",
            tipologia="Residencial",
            rangSuperficie="0-100"
        )

        self.building_a1 = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=80,
            nombrePlantes=1,
            reglament="test",
            orientacioPrincipal="Nord",
            grupComparable=self.group_a
        )

        self.building_a2 = Edifici.objects.create(
            anyConstruccio=2005,
            tipologia="Residencial",
            superficieTotal=90,
            nombrePlantes=1,
            reglament="test",
            orientacioPrincipal="Sud",
            grupComparable=self.group_a
        )

        self.building_b1 = Edifici.objects.create(
            anyConstruccio=2010,
            tipologia="Residencial",
            superficieTotal=85,
            nombrePlantes=1,
            reglament="test",
            orientacioPrincipal="Est",
            grupComparable=self.group_b
        )

        self.p1 = Participacio.objects.create(
            edifici=self.building_a1,
            lliga=self.league,
            puntuacio=90,
            posicio=0,
            divisio="Bronze"
        )

        self.p2 = Participacio.objects.create(
            edifici=self.building_a2,
            lliga=self.league,
            puntuacio=80,
            posicio=0,
            divisio="Bronze"
        )

        self.p3 = Participacio.objects.create(
            edifici=self.building_b1,
            lliga=self.league,
            puntuacio=100,
            posicio=0,
            divisio="Bronze"
        )

    """Comprobar funcionament del ranking global"""
    def test_ranking_global_includes_all_segments(self):
        ranking = self.league.participations.order_by("-puntuacio")

        self.assertEqual(ranking.count(), 3)

        self.assertEqual(ranking[0].edifici, self.building_b1)  # 100 puntos

    """Comprobar segmentacio correcta"""
    def test_ranking_segment_group_a(self):
        ranking = self.league.participations.filter(
            edifici__grupComparable=self.group_a
        ).order_by("-puntuacio")

        self.assertEqual(ranking.count(), 2)

        edificios = [p.edifici for p in ranking]

        self.assertIn(self.building_a1, edificios)
        self.assertIn(self.building_a2, edificios)
        self.assertNotIn(self.building_b1, edificios)

    """Comprovar segmentacio correcta d'una altra manera"""
    def test_ranking_segment_group_b(self):
        ranking = self.league.participations.filter(
            edifici__grupComparable=self.group_b
        ).order_by("-puntuacio")

        self.assertEqual(ranking.count(), 1)
        self.assertEqual(ranking[0].edifici, self.building_b1)

    """Test de endpoint real"""
    def test_api_segmented_ranking(self):
        client = APIClient()

        response = client.get(
            f"/api/leagues/{self.league.id}/ranking/?group={self.group_a.idGrup}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    """Test grup no valid"""
    def test_ranking_invalid_group_returns_404(self):
        invalid_group_id = 999  # no existe

        response = self.client.get(
            f"/api/leagues/{self.league.id}/ranking/?group={invalid_group_id}"
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "Invalid group")

    """Test ranking segmentat normal, comprobar que el grup correcte s'utilitza automaticament"""
    def test_ranking_segmentado_auto(self):
        response = self.client.get(
            f"/api/leagues/{self.league.id}/posicion_edifici/"
            f"?edifici={self.building_a1.idEdifici}&segment=true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["segmentado"], True)
        self.assertEqual(response.data["grupo_usado"], self.group_a.idGrup)

    """Test per comprovar que la versio sense segmentar tambe funciona"""
    def test_ranking_sin_segmentacion(self):
        response = self.client.get(
            f"/api/leagues/{self.league.id}/posicion_edifici/"
            f"?edifici={self.building_a1.idEdifici}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["segmentado"], False)