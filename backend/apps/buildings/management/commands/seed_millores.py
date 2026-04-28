from django.core.management.base import BaseCommand

from apps.buildings.models import (
    CatalegMillora,
    CategoriaMillora,
    UnitatBaseMillora,
    AmbitActuacio,
    TipusAcord,
    NivellConfianca,
)


MILLORES = [
    {
        "slug": "aillament-sate-facana",
        "nom": "Aïllament exterior SATE de façana",
        "categoria": CategoriaMillora.ENVOLUPANT,
        "unitatBase": UnitatBaseMillora.M2,
        "costEstimatBase": 95.0,
        "costMinim": 70.0,
        "costMaxim": 120.0,
        "mantenimentAnual": 1.2,
        "vidaUtil": 30,
        "estalviEnergeticEstimat": 20.0,
        "impactePunts": 8.0,
        "nivellConfianca": NivellConfianca.MIG,
        "ambit": AmbitActuacio.EDIFICI,
        "requereixAcordComunitat": True,
        "tipusAcordEstimat": TipusAcord.MAJORIA_3_5,
        "requereixLlicenciaMunicipal": True,
        "requereixTecnicCompetent": True,
        "requereixCeePrePost": True,
        "descripcio": "Millora de l'envolupant mitjançant sistema SATE exterior. Cost orientatiu basat en rangs de mercat.",
        "bloquejadorsFrequents": ["Façana catalogada", "Edifici protegit", "Restriccions comunitàries"],
        "parametresBase": {
            "impactes": {
                "reduccio_demanda_calefaccio": 0.28,
                "reduccio_demanda_refrigeracio": 0.10,
                "reduccio_infiltracions": 0.08,
                "co2_factor_kg_per_kwh_estalviat": 0.18
            }
        },
    },
    {
        "slug": "aillament-coberta",
        "nom": "Aïllament de coberta",
        "categoria": CategoriaMillora.ENVOLUPANT,
        "unitatBase": UnitatBaseMillora.M2,
        "costEstimatBase": 85.0,
        "costMinim": 65.0,
        "costMaxim": 110.0,
        "mantenimentAnual": 1.0,
        "vidaUtil": 30,
        "estalviEnergeticEstimat": 14.0,
        "impactePunts": 5.0,
        "nivellConfianca": NivellConfianca.MIG,
        "ambit": AmbitActuacio.EDIFICI,
        "requereixAcordComunitat": True,
        "tipusAcordEstimat": TipusAcord.MAJORIA_SIMPLE,
        "requereixLlicenciaMunicipal": True,
        "requereixTecnicCompetent": True,
        "requereixCeePrePost": True,
        "descripcio": "Aïllament de coberta plana o inclinada per reduir pèrdues a l'hivern i guanys tèrmics a l'estiu.",
        "bloquejadorsFrequents": ["Coberta no accessible", "Elements comunitaris incompatibles"],
        "parametresBase": {
            "impactes": {
                "reduccio_demanda_calefaccio": 0.12,
                "reduccio_demanda_refrigeracio": 0.16,
                "co2_factor_kg_per_kwh_estalviat": 0.18
            }
        },
    },
    {
        "slug": "finestres-eficients",
        "nom": "Substitució per finestres eficients",
        "categoria": CategoriaMillora.ENVOLUPANT,
        "unitatBase": UnitatBaseMillora.M2,
        "costEstimatBase": 420.0,
        "costMinim": 300.0,
        "costMaxim": 600.0,
        "mantenimentAnual": 3.0,
        "vidaUtil": 30,
        "estalviEnergeticEstimat": 12.0,
        "impactePunts": 5.0,
        "nivellConfianca": NivellConfianca.MIG,
        "ambit": AmbitActuacio.HABITATGE,
        "requereixAcordComunitat": False,
        "tipusAcordEstimat": TipusAcord.NO_CAL,
        "requereixLlicenciaMunicipal": False,
        "requereixTecnicCompetent": False,
        "requereixCeePrePost": True,
        "descripcio": "Canvi de finestres per models amb doble o triple vidre i millor estanquitat.",
        "bloquejadorsFrequents": ["Estètica de façana protegida", "Normativa comunitària"],
        "parametresBase": {
            "impactes": {
                "reduccio_demanda_calefaccio": 0.15,
                "reduccio_demanda_refrigeracio": 0.07,
                "reduccio_infiltracions": 0.12,
                "millora_confort": 0.20,
                "co2_factor_kg_per_kwh_estalviat": 0.18
            }
        },
    },
    {
        "slug": "illuminacio-led",
        "nom": "Substitució a il·luminació LED",
        "categoria": CategoriaMillora.ELECTRICITAT,
        "unitatBase": UnitatBaseMillora.UNITAT,
        "costEstimatBase": 55.0,
        "costMinim": 20.0,
        "costMaxim": 90.0,
        "mantenimentAnual": 0.3,
        "vidaUtil": 12,
        "estalviEnergeticEstimat": 10.0,
        "impactePunts": 3.0,
        "nivellConfianca": NivellConfianca.ALT,
        "ambit": AmbitActuacio.COMU,
        "requereixAcordComunitat": False,
        "tipusAcordEstimat": TipusAcord.NO_CAL,
        "requereixLlicenciaMunicipal": False,
        "requereixTecnicCompetent": False,
        "requereixCeePrePost": False,
        "descripcio": "Substitució de lluminàries existents per LED en zones comunes o habitatges.",
        "bloquejadorsFrequents": [],
        "parametresBase": {
            "impactes": {
                "reduccio_consum_illuminacio": 0.65,
                "reduccio_consum_electric_total_tipica": 0.03,
                "co2_factor_kg_per_kwh_estalviat": 0.18
            }
        },
    },
    {
        "slug": "control-illuminacio",
        "nom": "Sensors de presència i control d'il·luminació",
        "categoria": CategoriaMillora.CONTROL_MONITORATGE,
        "unitatBase": UnitatBaseMillora.UNITAT,
        "costEstimatBase": 82.0,
        "costMinim": 50.0,
        "costMaxim": 120.0,
        "mantenimentAnual": 2.5,
        "vidaUtil": 10,
        "estalviEnergeticEstimat": 4.0,
        "impactePunts": 2.0,
        "nivellConfianca": NivellConfianca.MIG,
        "ambit": AmbitActuacio.COMU,
        "requereixAcordComunitat": False,
        "tipusAcordEstimat": TipusAcord.NO_CAL,
        "requereixLlicenciaMunicipal": False,
        "requereixTecnicCompetent": False,
        "requereixCeePrePost": False,
        "descripcio": "Instal·lació de sensors de presència o regulació per reduir hores d'encesa innecessàries.",
        "bloquejadorsFrequents": ["Instal·lació elèctrica antiga"],
        "parametresBase": {
            "impactes": {
                "reduccio_consum_illuminacio_addicional": 0.18,
                "co2_factor_kg_per_kwh_estalviat": 0.18
            }
        },
    },
    {
        "slug": "plaques-solars-fotovoltaica",
        "nom": "Instal·lació fotovoltaica d'autoconsum",
        "categoria": CategoriaMillora.RENOVABLES,
        "unitatBase": UnitatBaseMillora.KWP,
        "costEstimatBase": 1350.0,
        "costMinim": 1100.0,
        "costMaxim": 1800.0,
        "mantenimentAnual": 22.0,
        "vidaUtil": 25,
        "estalviEnergeticEstimat": 20.0,
        "impactePunts": 7.0,
        "nivellConfianca": NivellConfianca.MIG,
        "ambit": AmbitActuacio.EDIFICI,
        "requereixAcordComunitat": True,
        "tipusAcordEstimat": TipusAcord.MAJORIA_3_5,
        "requereixLlicenciaMunicipal": True,
        "requereixTecnicCompetent": True,
        "requereixCeePrePost": False,
        "descripcio": "Instal·lació fotovoltaica d'autoconsum comunitari o individual. El càlcul estima producció i autoconsum directe.",
        "bloquejadorsFrequents": ["Coberta sense espai", "Ombres", "Edifici protegit", "Acord comunitari pendent"],
        "parametresBase": {
            "impactes": {
                "produccio_kwh_per_kwp_any": 1300,
                "factor_perdues_sistema": 0.14,
                "factor_ombra_base": 0.90,
                "autoconsum_directe_base": 0.55,
                "co2_evitat_kg_per_kwh_fv": 0.18
            }
        },
    },
    {
        "slug": "aerotermia-centralitzada",
        "nom": "Aerotèrmia per calefacció i ACS",
        "categoria": CategoriaMillora.INSTAL_LACIO_TERMICA,
        "unitatBase": UnitatBaseMillora.HABITATGE,
        "costEstimatBase": 8500.0,
        "costMinim": 7000.0,
        "costMaxim": 13000.0,
        "mantenimentAnual": 95.0,
        "vidaUtil": 18,
        "estalviEnergeticEstimat": 25.0,
        "impactePunts": 6.0,
        "nivellConfianca": NivellConfianca.MIG,
        "ambit": AmbitActuacio.HABITATGE,
        "requereixAcordComunitat": False,
        "tipusAcordEstimat": TipusAcord.NO_CAL,
        "requereixLlicenciaMunicipal": True,
        "requereixTecnicCompetent": True,
        "requereixCeePrePost": True,
        "descripcio": "Substitució de sistemes convencionals per aerotèrmia. Cost orientatiu per habitatge.",
        "bloquejadorsFrequents": ["Espai per unitats exteriors", "Soroll", "Compatibilitat amb instal·lació existent"],
        "parametresBase": {
            "impactes": {
                "cop_mitja": 3.2,
                "reduccio_emissions_calefaccio": 0.45,
                "reduccio_consum_primari_no_renovable": 0.30,
                "co2_factor_kg_per_kwh_estalviat": 0.18
            }
        },
    },
    {
        "slug": "monitoratge-energetic-bms",
        "nom": "Monitoratge energètic i subcomptadors",
        "categoria": CategoriaMillora.CONTROL_MONITORATGE,
        "unitatBase": UnitatBaseMillora.EDIFICI,
        "costEstimatBase": 7800.0,
        "costMinim": 4000.0,
        "costMaxim": 12000.0,
        "mantenimentAnual": 260.0,
        "vidaUtil": 12,
        "estalviEnergeticEstimat": 6.0,
        "impactePunts": 3.0,
        "nivellConfianca": NivellConfianca.MIG,
        "ambit": AmbitActuacio.EDIFICI,
        "requereixAcordComunitat": True,
        "tipusAcordEstimat": TipusAcord.MAJORIA_SIMPLE,
        "requereixLlicenciaMunicipal": False,
        "requereixTecnicCompetent": True,
        "requereixCeePrePost": False,
        "descripcio": "Sistema de monitoratge per detectar consums anòmals i facilitar decisions de gestió energètica.",
        "bloquejadorsFrequents": ["Accés a comptadors", "Compatibilitat tècnica", "Privacitat de dades"],
        "parametresBase": {
            "impactes": {
                "reduccio_consum_electric_total_tipica": 0.06,
                "co2_factor_kg_per_kwh_estalviat": 0.18
            }
        },
    },
]


class Command(BaseCommand):
    help = "Crea o actualitza el catàleg inicial de millores de BuildRank."

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for data in MILLORES:
            slug = data["slug"]
            obj, was_created = CatalegMillora.objects.update_or_create(
                slug=slug,
                defaults=data,
            )

            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Creada millora: {obj.nom}"))
            else:
                updated += 1
                self.stdout.write(self.style.WARNING(f"Actualitzada millora: {obj.nom}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Catàleg de millores carregat. Creades: {created}. Actualitzades: {updated}."
            )
        )