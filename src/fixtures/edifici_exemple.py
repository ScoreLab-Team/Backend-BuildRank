from models import Edifici, Habitatge, Localitzacio, DadesEnergetiques

def crear_edifici_exemple():

    # Crear el edificio
    edifici = Edifici(
        id_edifici="EDIF001",
        any_construccio=1995,
        tipologia="Residencial",
        superficie_total=1200,
        reglament="CTE",
        orientacio_principal="Sud",
        puntuacio_base=50
    )

    # Localización
    localitzacio = Localitzacio(
        carrer="Carrer Mallorca",
        numero=123,
        codi_postal="08036",
        barri="Eixample",
        latitud=41.387,
        longitud=2.170,
        zona_climatica="C2"
    )
    edifici.set_localitzacio(localitzacio)

    # Crear habitatges
    habitatge1 = Habitatge("REF123", "2", "A", 80)
    habitatge2 = Habitatge("REF124", "3", "B", 95)

    # Añadir dades energètiques a cada habitatge
    dades1 = DadesEnergetiques(
        qualificacio_global="B",
        consum_energia_primaria=41.66,
        consum_energia_final=38.2,
        emissions_co2=8.53,
        cost_anual_energia=900
    )
    dades1.energia_calefaccio = 20
    dades1.energia_refrigeracio = 10
    dades1.energia_acs = 5
    dades1.energia_enllumenament = 3

    habitatge1.set_dades_energetiques(dades1)

    dades2 = DadesEnergetiques(
        qualificacio_global="C",
        consum_energia_primaria=55.12,
        consum_energia_final=50.0,
        emissions_co2=12.1,
        cost_anual_energia=1100
    )
    dades2.energia_calefaccio = 25
    dades2.energia_refrigeracio = 12
    dades2.energia_acs = 6
    dades2.energia_enllumenament = 4

    habitatge2.set_dades_energetiques(dades2)

    # Añadir habitatges al edificio
    edifici.afegir_habitatge(habitatge1)
    edifici.afegir_habitatge(habitatge2)

    return edifici