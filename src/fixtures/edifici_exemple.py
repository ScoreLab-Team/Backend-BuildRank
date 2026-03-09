from models import Edifici, Habitatge, Localitzacio


def crear_edifici_exemple():

    edifici = Edifici(
        id_edifici="EDIF001",
        any_construccio=1995,
        tipologia="Residencial",
        superficie_total=1200,
        reglament="CTE",
        orientacio_principal="Sud",
        puntuacio_base=50
    )

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

    habitatge1 = Habitatge("REF123", "2", "A", 80)
    habitatge2 = Habitatge("REF124", "3", "B", 95)

    edifici.afegir_habitatge(habitatge1)
    edifici.afegir_habitatge(habitatge2)

    return edifici