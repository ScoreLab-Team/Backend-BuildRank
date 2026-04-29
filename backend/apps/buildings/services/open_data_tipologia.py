# apps/buildings/services/open_data_tipologia.py

from apps.buildings.models import TipusEdificiOpenData


MAP_TIPUS_EDIFICI = {
    # Bloc de pisos
    "Bloc d'habitatges":                        TipusEdificiOpenData.BLOC_PISOS,
    "Bloc d'habitatges plurifamiliar":          TipusEdificiOpenData.BLOC_PISOS,
    "Bloque de viviendas":                      TipusEdificiOpenData.BLOC_PISOS,
    "Bloque de viviendas plurifamiliar":        TipusEdificiOpenData.BLOC_PISOS,

    # Habitatge dins bloc
    "Habitatge individual en bloc d'habitatges": TipusEdificiOpenData.HABITATGE_BLOC,
    "Vivienda individual en bloque de viviendas": TipusEdificiOpenData.HABITATGE_BLOC,

    # Unifamiliar
    "Habitatge unifamiliar":                    TipusEdificiOpenData.UNIFAMILIAR,
    "Vivienda unifamiliar":                     TipusEdificiOpenData.UNIFAMILIAR,

    # Terciari
    "Terciari":                                 TipusEdificiOpenData.TERCIARI,
    "Terciario":                                TipusEdificiOpenData.TERCIARI,
}


def map_tipus_edifici(valor: str) -> str:
    """
    Mapeja el valor raw del camp us_edifici del CSV al TipusEdificiOpenData intern.
    Si el valor no es reconeix, retorna DESCONEGUT (i quedarà registrat a dades_raw).
    """
    return MAP_TIPUS_EDIFICI.get((valor or '').strip(), TipusEdificiOpenData.DESCONEGUT)