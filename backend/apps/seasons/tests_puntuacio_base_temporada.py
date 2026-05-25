from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import RoleChoices
from apps.buildings.models import (
    CatalegMillora,
    Edifici,
    EstatValidacio,
    GrupComparable,
    Localitzacio,
    MilloraImplementada,
)
from apps.leagues.models import CategoriaRanking, DivisioLliga, Lliga
from apps.participations.models import Participacio
from apps.seasons.models import Temporada
from apps.seasons.services import actualitzar_puntuacions_base_inici_temporada

User = get_user_model()


class PuntuacioBaseTemporadaTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="admin_temp_score@example.com",
            password="Password123",
            first_name="Admin",
        )
        cls.admin.profile.role = RoleChoices.ADMIN
        cls.admin.profile.save(update_fields=["role"])

        cls.grup = GrupComparable.objects.create(
            idGrup=902,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="0-500",
        )
        cls.loc = Localitzacio.objects.create(
            carrer="Carrer Temporada Score",
            numero=1,
            codiPostal="08001",
            barri="Centre",
            latitud=41.0,
            longitud=2.0,
            zonaClimatica="C2",
        )
        cls.edifici = Edifici.objects.create(
            anyConstruccio=2000,
            tipologia="Residencial",
            superficieTotal=400,
            reglament="CTE",
            orientacioPrincipal="Sud",
            localitzacio=cls.loc,
            administradorFinca=cls.admin,
            grupComparable=cls.grup,
        )
        cls.edifici.puntuacioBase = 50.0
        cls.edifici.save(update_fields=["puntuacioBase"])

        cls.temporada_anterior = Temporada.objects.create(
            nom="Temporada anterior",
            dataInici="2026-01-01",
            dataFi="2026-03-31",
        )
        cls.temporada_nova = Temporada.objects.create(
            nom="Temporada nova",
            dataInici="2026-04-01",
            dataFi="2026-06-30",
        )

        cls.lliga = Lliga.objects.create(
            nom="Bronze Eficiència",
            categoria=CategoriaRanking.EFICIENCIA,
            divisio=DivisioLliga.BRONZE,
            temporada=cls.temporada_nova,
        )
        cls.participacio = Participacio.objects.create(
            edifici=cls.edifici,
            lliga=cls.lliga,
            puntuacio=50.0,
            puntuacio_inicial=30,
            posicio=1,
            divisio="Bronze",
        )

        cls.millora_validada = CatalegMillora.objects.create(
            nom="Millora validada temporada anterior",
            descripcio="Ha de comptar a la temporada següent.",
            categoria="envolupant",
            costMinim=1000.0,
            costMaxim=2000.0,
            estalviEnergeticEstimat=10.0,
            impactePunts=7.0,
            activa=True,
        )
        cls.millora_rebutjada = CatalegMillora.objects.create(
            nom="Millora rebutjada",
            descripcio="No ha de comptar.",
            categoria="envolupant",
            costMinim=1000.0,
            costMaxim=2000.0,
            estalviEnergeticEstimat=10.0,
            impactePunts=90.0,
            activa=True,
        )

        MilloraImplementada.objects.create(
            dataExecucio="2026-02-15",
            costReal=1500.0,
            estatValidacio=EstatValidacio.VALIDADA,
            millora=cls.millora_validada,
            edifici=cls.edifici,
            administradorFinca=cls.admin,
        )
        MilloraImplementada.objects.create(
            dataExecucio="2026-02-20",
            costReal=1500.0,
            estatValidacio=EstatValidacio.REBUTJADA,
            millora=cls.millora_rebutjada,
            edifici=cls.edifici,
            administradorFinca=cls.admin,
        )

    def test_inici_temporada_actualitza_base_amb_validada_anterior(self):
        resum = actualitzar_puntuacions_base_inici_temporada(self.temporada_nova)

        self.edifici.refresh_from_db()
        self.participacio.refresh_from_db()

        self.assertEqual(self.edifici.puntuacioBase, 57.0)
        self.assertEqual(self.participacio.puntuacio, 57.0)
        self.assertEqual(resum["temporada_anterior"], self.temporada_anterior.id_temporada)
        self.assertGreaterEqual(resum["edificis_actualitzats"], 1)

    def test_millores_no_validades_no_compten(self):
        actualitzar_puntuacions_base_inici_temporada(self.temporada_nova)

        self.edifici.refresh_from_db()

        self.assertNotEqual(self.edifici.puntuacioBase, 140.0)
        self.assertEqual(self.edifici.puntuacioBase, 57.0)
