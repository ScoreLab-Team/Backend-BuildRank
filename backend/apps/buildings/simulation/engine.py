from __future__ import annotations

from typing import Any, Dict, List
from django.db.models import Sum

from apps.buildings.models import (
    Edifici,
    CatalegMillora,
    UnitatBaseMillora,
)

MOTOR_VERSION = "SIM-1.0"

# Hipòtesis MVP. No són valors oficials: serveixen com a fallback quan no hi ha dades reals.
CONSUM_KWH_M2_ANY_FALLBACK = 110.0
PREU_KWH_FALLBACK = 0.22
FACTOR_CO2_KG_KWH_FALLBACK = 0.18


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _round(value: float) -> float:
    return round(float(value or 0), 2)


def _num_habitatges(edifici: Edifici) -> int:
    total = edifici.habitatges.count()
    return max(total, 1)


def _score_base(edifici: Edifici) -> float:
    """
    Preferim l'últim BHS si existeix. Si no, usem puntuacioBase.
    Es limita a 0-100 perquè el motor sigui estable de cara al frontend.
    """
    last_bhs = edifici.bhs_history.first()
    if last_bhs:
        return clamp(last_bhs.score)

    return clamp(edifici.puntuacioBase or 0)


def _dades_base_edifici(edifici: Edifici) -> Dict[str, Any]:
    """
    Agrega les dades energètiques dels habitatges de l'edifici.
    Si no hi ha dades energètiques, genera una hipòtesi orientativa per superfície.
    """
    habitatges = edifici.habitatges.select_related("dadesEnergetiques").all()

    consum_final = 0.0
    emissions = 0.0
    cost_anual = 0.0

    calefaccio = 0.0
    refrigeracio = 0.0
    acs = 0.0
    enllumenament = 0.0

    aillament_values = []
    finestres_values = []
    count = 0

    for habitatge in habitatges:
        dades = habitatge.dadesEnergetiques
        if not dades:
            continue

        count += 1
        consum_final += dades.consumEnergiaFinal or 0
        emissions += dades.emissionsCO2 or 0
        cost_anual += dades.costAnualEnergia or 0

        calefaccio += dades.energiaCalefaccio or 0
        refrigeracio += dades.energiaRefrigeracio or 0
        acs += dades.energiaACS or 0
        enllumenament += dades.energiaEnllumenament or 0

        aillament_values.append(dades.aillamentTermic or 0)
        finestres_values.append(dades.valorFinestres or 0)

    if count > 0:
        categories_sum = calefaccio + refrigeracio + acs + enllumenament
        altres = max(consum_final - categories_sum, 0)

        preu_kwh = (
            cost_anual / consum_final
            if consum_final > 0 and cost_anual > 0
            else PREU_KWH_FALLBACK
        )
        factor_co2 = (
            emissions / consum_final
            if consum_final > 0 and emissions > 0
            else FACTOR_CO2_KG_KWH_FALLBACK
        )

        return {
            "origen": "dades_energetiques_habitatges",
            "num_habitatges_amb_dades": count,
            "consumFinalKwhAny": consum_final,
            "emissionsKgCO2Any": emissions,
            "costAnualEnergia": cost_anual,
            "energiaCalefaccio": calefaccio,
            "energiaRefrigeracio": refrigeracio,
            "energiaACS": acs,
            "energiaEnllumenament": enllumenament,
            "energiaAltres": altres,
            "aillamentTermicMitja": sum(aillament_values) / len(aillament_values) if aillament_values else 0,
            "valorFinestresMitja": sum(finestres_values) / len(finestres_values) if finestres_values else 0,
            "preuKwhEstimatiu": preu_kwh,
            "factorCo2KgKwhEstimatiu": factor_co2,
            "scoreBase": _score_base(edifici),
        }

    # Fallback quan l'edifici encara no té dades energètiques carregades.
    superficie = max(edifici.superficieTotal or 0, 1)
    consum_estimat = superficie * CONSUM_KWH_M2_ANY_FALLBACK

    calefaccio = consum_estimat * 0.35
    refrigeracio = consum_estimat * 0.15
    acs = consum_estimat * 0.20
    enllumenament = consum_estimat * 0.10
    altres = consum_estimat * 0.20

    return {
        "origen": "estimacio_mvp_per_superficie",
        "num_habitatges_amb_dades": 0,
        "consumFinalKwhAny": consum_estimat,
        "emissionsKgCO2Any": consum_estimat * FACTOR_CO2_KG_KWH_FALLBACK,
        "costAnualEnergia": consum_estimat * PREU_KWH_FALLBACK,
        "energiaCalefaccio": calefaccio,
        "energiaRefrigeracio": refrigeracio,
        "energiaACS": acs,
        "energiaEnllumenament": enllumenament,
        "energiaAltres": altres,
        "aillamentTermicMitja": 0,
        "valorFinestresMitja": 0,
        "preuKwhEstimatiu": PREU_KWH_FALLBACK,
        "factorCo2KgKwhEstimatiu": FACTOR_CO2_KG_KWH_FALLBACK,
        "scoreBase": _score_base(edifici),
    }


def _inferir_quantitat(edifici: Edifici, millora: CatalegMillora, quantitat: float | None, cobertura: float) -> float:
    """
    Permet que el frontend no hagi de calcular superfícies o unitats complexes.
    Si s'envia quantitat, es respecta. Si no, fem una estimació MVP.
    """
    if quantitat is not None:
        return max(float(quantitat), 0)

    cobertura_factor = cobertura / 100

    if millora.unitatBase == UnitatBaseMillora.M2:
        return max((edifici.superficieTotal or 0) * cobertura_factor, 1)

    if millora.unitatBase == UnitatBaseMillora.HABITATGE:
        return _num_habitatges(edifici) * cobertura_factor

    if millora.unitatBase == UnitatBaseMillora.EDIFICI:
        return 1

    if millora.unitatBase == UnitatBaseMillora.KWP:
        return 3.0

    if millora.unitatBase == UnitatBaseMillora.KWH:
        return 5.0

    return 1


def _cost_millora(edifici: Edifici, millora: CatalegMillora, quantitat: float | None, cobertura: float) -> float:
    quantitat_final = _inferir_quantitat(edifici, millora, quantitat, cobertura)
    return quantitat_final * (millora.cost_orientatiu_unitari or 0)


def _aplicar_millora(
    *,
    edifici: Edifici,
    estat: Dict[str, float],
    millora: CatalegMillora,
    quantitat: float | None,
    coberturaPercent: float,
) -> Dict[str, Any]:
    cobertura = clamp(coberturaPercent, 0, 100) / 100
    impactes = millora.parametresBase.get("impactes", {}) if isinstance(millora.parametresBase, dict) else {}

    consum_abans = sum(estat.values())
    emissions_factor = impactes.get("co2_factor_kg_per_kwh_estalviat", FACTOR_CO2_KG_KWH_FALLBACK)

    reduccio_kwh = 0.0
    reduccio_emissions = 0.0

    # Envolupant: calefacció/refrigeració
    reduccio_calefaccio = estat["calefaccio"] * impactes.get("reduccio_demanda_calefaccio", 0) * cobertura
    reduccio_refrigeracio = estat["refrigeracio"] * impactes.get("reduccio_demanda_refrigeracio", 0) * cobertura
    reduccio_infiltracions = (
        (estat["calefaccio"] + estat["refrigeracio"])
        * impactes.get("reduccio_infiltracions", 0)
        * 0.25
        * cobertura
    )

    # ACS
    reduccio_acs = estat["acs"] * impactes.get("reduccio_demanda_acs", 0) * cobertura

    # Il·luminació
    reduccio_led = estat["enllumenament"] * impactes.get("reduccio_consum_illuminacio", 0) * cobertura
    reduccio_control = estat["enllumenament"] * impactes.get("reduccio_consum_illuminacio_addicional", 0) * cobertura

    # Reducció elèctrica total genèrica
    reduccio_total_tipica = consum_abans * impactes.get("reduccio_consum_electric_total_tipica", 0) * cobertura

    reduccio_kwh += (
        reduccio_calefaccio
        + reduccio_refrigeracio
        + reduccio_infiltracions
        + reduccio_acs
        + reduccio_led
        + reduccio_control
        + reduccio_total_tipica
    )

    # Fotovoltaica: la producció redueix energia de xarxa, no demanda real.
    produccio_fv = 0.0
    if "produccio_kwh_per_kwp_any" in impactes:
        kwp = _inferir_quantitat(edifici, millora, quantitat, coberturaPercent)
        produccio_fv = (
            kwp
            * impactes.get("produccio_kwh_per_kwp_any", 0)
            * (1 - impactes.get("factor_perdues_sistema", 0))
            * impactes.get("factor_ombra_base", 1)
        )
        autoconsum = impactes.get("autoconsum_directe_base", 0.55)
        reduccio_fv = min(produccio_fv * autoconsum, consum_abans)
        reduccio_kwh += reduccio_fv
        emissions_factor = impactes.get("co2_evitat_kg_per_kwh_fv", emissions_factor)

    # Aerotèrmia / climatització: tractament simplificat.
    reduccio_clima_emissions = 0.0
    if "reduccio_emissions_calefaccio" in impactes:
        reduccio_clima_emissions = (
            (estat["calefaccio"] + estat["acs"])
            * impactes.get("reduccio_emissions_calefaccio", 0)
            * emissions_factor
            * cobertura
        )

    reduccio_kwh = max(reduccio_kwh, 0)
    reduccio_kwh = min(reduccio_kwh, consum_abans * 0.85)

    reduccio_emissions += reduccio_kwh * emissions_factor
    reduccio_emissions += reduccio_clima_emissions

    # Repartiment simplificat de la reducció sobre categories.
    # Primer restem de les categories directament afectades.
    estat["calefaccio"] = max(estat["calefaccio"] - reduccio_calefaccio - reduccio_infiltracions * 0.6, 0)
    estat["refrigeracio"] = max(estat["refrigeracio"] - reduccio_refrigeracio - reduccio_infiltracions * 0.4, 0)
    estat["acs"] = max(estat["acs"] - reduccio_acs, 0)
    estat["enllumenament"] = max(estat["enllumenament"] - reduccio_led - reduccio_control, 0)

    # Si encara queda reducció genèrica/fotovoltaica, la reflectim en altres.
    reduccio_directa = (
        reduccio_calefaccio
        + reduccio_refrigeracio
        + reduccio_infiltracions
        + reduccio_acs
        + reduccio_led
        + reduccio_control
    )
    restant = max(reduccio_kwh - reduccio_directa, 0)
    estat["altres"] = max(estat["altres"] - restant, 0)

    cost = _cost_millora(edifici, millora, quantitat, coberturaPercent)
    impacte_punts = (millora.impactePunts or 0) * cobertura

    return {
        "milloraId": millora.idMillora,
        "slug": millora.slug,
        "nom": millora.nom,
        "categoria": millora.categoria,
        "unitatBase": millora.unitatBase,
        "quantitatAplicada": _round(_inferir_quantitat(edifici, millora, quantitat, coberturaPercent)),
        "coberturaPercent": _round(coberturaPercent),
        "costEstimat": _round(cost),
        "reduccioConsumKwhAny": _round(reduccio_kwh),
        "reduccioEmissionsKgCO2Any": _round(reduccio_emissions),
        "impactePunts": _round(impacte_punts),
        "produccioFotovoltaicaKwhAny": _round(produccio_fv),
        "nivellConfianca": millora.nivellConfianca,
        "hipotesisAplicades": {
            "motor": MOTOR_VERSION,
            "fontCost": "cataleg_millores_orientatiu",
            "calculExacte": False,
            "nota": "Estimació MVP. No substitueix auditoria energètica ni pressupost professional.",
        },
    }


def simular_millores(edifici: Edifici, millores_input: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Entrada esperada:
    [
      {"millora": CatalegMillora, "quantitat": 20, "coberturaPercent": 80},
      ...
    ]
    """
    base = _dades_base_edifici(edifici)

    estat = {
        "calefaccio": base["energiaCalefaccio"],
        "refrigeracio": base["energiaRefrigeracio"],
        "acs": base["energiaACS"],
        "enllumenament": base["energiaEnllumenament"],
        "altres": base["energiaAltres"],
    }

    items_resultat = []
    cost_total = 0.0
    reduccio_total_kwh = 0.0
    reduccio_total_emissions = 0.0
    impacte_total_punts = 0.0

    for item in millores_input:
        millora = item["millora"]
        quantitat = item.get("quantitat")
        cobertura = item.get("coberturaPercent", 100)

        parcial = _aplicar_millora(
            edifici=edifici,
            estat=estat,
            millora=millora,
            quantitat=quantitat,
            coberturaPercent=cobertura,
        )

        items_resultat.append(parcial)
        cost_total += parcial["costEstimat"]
        reduccio_total_kwh += parcial["reduccioConsumKwhAny"]
        reduccio_total_emissions += parcial["reduccioEmissionsKgCO2Any"]
        impacte_total_punts += parcial["impactePunts"]

    consum_despres = max(base["consumFinalKwhAny"] - reduccio_total_kwh, 0)
    emissions_despres = max(base["emissionsKgCO2Any"] - reduccio_total_emissions, 0)
    cost_despres = max(base["costAnualEnergia"] - reduccio_total_kwh * base["preuKwhEstimatiu"], 0)
    estalvi_anual = max(base["costAnualEnergia"] - cost_despres, 0)

    score_abans = base["scoreBase"]
    score_despres = clamp(score_abans + impacte_total_punts)

    return {
        "versioMotor": MOTOR_VERSION,
        "edificiId": edifici.idEdifici,
        "abans": {
            "consumFinalKwhAny": _round(base["consumFinalKwhAny"]),
            "emissionsKgCO2Any": _round(base["emissionsKgCO2Any"]),
            "costAnualEnergia": _round(base["costAnualEnergia"]),
            "score": _round(score_abans),
            "origenDades": base["origen"],
        },
        "despres": {
            "consumFinalKwhAny": _round(consum_despres),
            "emissionsKgCO2Any": _round(emissions_despres),
            "costAnualEnergia": _round(cost_despres),
            "score": _round(score_despres),
        },
        "delta": {
            "reduccioConsumKwhAny": _round(reduccio_total_kwh),
            "reduccioConsumPercent": _round((reduccio_total_kwh / base["consumFinalKwhAny"]) * 100 if base["consumFinalKwhAny"] else 0),
            "reduccioEmissionsKgCO2Any": _round(reduccio_total_emissions),
            "reduccioEmissionsPercent": _round((reduccio_total_emissions / base["emissionsKgCO2Any"]) * 100 if base["emissionsKgCO2Any"] else 0),
            "estalviAnualEstimatiu": _round(estalvi_anual),
            "costTotalEstimat": _round(cost_total),
            "incrementScore": _round(score_despres - score_abans),
        },
        "items": items_resultat,
        "hipotesis": {
            "preuKwhEstimatiu": _round(base["preuKwhEstimatiu"]),
            "factorCo2KgKwhEstimatiu": _round(base["factorCo2KgKwhEstimatiu"]),
            "calculExacte": False,
            "missatge": "Resultat orientatiu basat en paràmetres simplificats i dades disponibles de l'edifici.",
        },
    }