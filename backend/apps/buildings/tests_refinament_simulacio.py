from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import RoleChoices
from apps.buildings.models import (
    CatalegMillora,
    DadesEnergetiquesOpenData,
    Edifici,
    EstatValidacio,
    GrupComparable,
    Localitzacio,
    MilloraImplementada,
    UnitatBaseMillora,
)
from apps.buildings.serializers import SimulacioMilloraPreviewSerializer
from apps.buildings.simulation.engine import simular_millores

User = get_user_model()


class SimulacioMilloresRefinamentTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            email="admin_ref_sim@example.com",
            password="Password123",
            first_name="Admin",
        )
        cls.admin.profile.role = RoleChoices.ADMIN
        cls.admin.profile.save(update_fields=["role"])

        cls.grup = GrupComparable.objects.create(
            idGrup=901,
            zonaClimatica="C2",
            tipologia="Residencial",
            rangSuperficie="0-500",
        )
        cls.loc = Localitzacio.objects.create(
            carrer="Carrer Simulacio Refinada",
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

        DadesEnergetiquesOpenData.objects.create(
            edifici=cls.edifici,
            qualificacioGlobal="D",
            consumEnergiaPrimaria=9000.0,
            consumEnergiaFinal=8000.0,
            emissionsCO2=1600.0,
            costAnualEnergia=1760.0,
            energiaCalefaccio=3000.0,
            energiaRefrigeracio=1000.0,
            energiaACS=1800.0,
            energiaEnllumenament=700.0,
            aillamentTermic=45.0,
            valorFinestres=2.5,
        )

        cls.edifici.refresh_from_db()
        cls.edifici.puntuacioBase = None
        cls.edifici.puntuacioBaseOpenData = 64.0
        cls.edifici.save(update_fields=["puntuacioBase", "puntuacioBaseOpenData"])

    @staticmethod
    def _crear_millora(nom="Millora test", impactes=None, **kwargs):
        defaults = {
            "nom": nom,
            "descripcio": "Millora de prova per al motor de simulació.",
            "categoria": "envolupant",
            "unitatBase": UnitatBaseMillora.M2,
            "costMinim": 1000.0,
            "costMaxim": 2000.0,
            "costEstimatBase": 100.0,
            "estalviEnergeticEstimat": 10.0,
            "impactePunts": 10.0,
            "activa": True,
            "parametresBase": {"impactes": impactes or {}},
        }
        defaults.update(kwargs)
        return CatalegMillora.objects.create(**defaults)

    def test_simulacio_usa_opendata_abans_del_fallback_per_superficie(self):
        resultat = simular_millores(self.edifici, [])

        self.assertEqual(resultat["abans"]["origenDades"], "opendata_cee")
        self.assertEqual(resultat["abans"]["consumFinalKwhAny"], 8000.0)
        self.assertEqual(resultat["abans"]["score"], 64.0)

    def test_quantitat_zero_i_cobertura_positiva_no_generen_impacte(self):
        millora = self._crear_millora(
            nom="Millora quantitat zero",
            impactePunts=25.0,
            impactes={"reduccio_consum_electric_total_tipica": 0.5},
        )

        resultat = simular_millores(
            self.edifici,
            [{"millora": millora, "quantitat": 0, "coberturaPercent": 100}],
        )

        self.assertEqual(resultat["delta"]["reduccioConsumKwhAny"], 0.0)
        self.assertEqual(resultat["delta"]["costTotalEstimat"], 0.0)
        self.assertEqual(resultat["delta"]["incrementScore"], 0.0)

    def test_percentatge_reduccio_emissions_no_supera_100(self):
        millora = self._crear_millora(
            nom="Millora emissions extremes",
            impactePunts=5.0,
            impactes={
                "reduccio_consum_electric_total_tipica": 10.0,
                "co2_factor_kg_per_kwh_estalviat": 100.0,
            },
        )

        resultat = simular_millores(
            self.edifici,
            [{"millora": millora, "coberturaPercent": 100}],
        )

        self.assertLessEqual(resultat["delta"]["reduccioEmissionsPercent"], 100.0)
        self.assertGreaterEqual(resultat["despres"]["emissionsKgCO2Any"], 0.0)

    def test_serializer_rebutja_millores_duplicades(self):
        millora = self._crear_millora(nom="Millora duplicada")

        serializer = SimulacioMilloraPreviewSerializer(data={
            "millores": [
                {"milloraId": millora.idMillora, "coberturaPercent": 50},
                {"milloraId": millora.idMillora, "coberturaPercent": 50},
            ]
        })

        self.assertFalse(serializer.is_valid())
        self.assertIn("mateixa millora", str(serializer.errors))

    def test_validar_millora_no_canvia_puntuacio_base_immediatament(self):
        millora = self._crear_millora(nom="Millora validada no immediata", impactePunts=20.0)

        implementada = MilloraImplementada.objects.create(
            dataExecucio="2026-04-01",
            costReal=1500.0,
            estatValidacio=EstatValidacio.EN_REVISIO,
            millora=millora,
            edifici=self.edifici,
        )

        self.edifici.puntuacioBase = 64.0
        self.edifici.save(update_fields=["puntuacioBase"])

        implementada.estatValidacio = EstatValidacio.VALIDADA
        implementada.administradorFinca = self.admin
        implementada.save(update_fields=["estatValidacio", "administradorFinca"])

        self.edifici.refresh_from_db()
        self.assertEqual(self.edifici.puntuacioBase, 64.0)
