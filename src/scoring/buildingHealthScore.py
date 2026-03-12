# scoring/building_health_score.py
from models.dadesEnergetiques import DadesEnergetiques
from .versions import BHS_VERSIONS

def calcular_building_health_score(dades: DadesEnergetiques, version: str = "1.0"):
    """
    Calcula el Building Health Score (BHS)
    Version: la clave de BHS_VERSIONS
    """
    if version not in BHS_VERSIONS:
        raise ValueError(f"Versión {version} no definida en BHS_VERSIONS")

    pesos = BHS_VERSIONS[version]

    # Normalización simple (0-100)
    consumo_norm = max(0, min(100, (100 - dades.consum_energia_primaria)))  # menos consumo = mejor
    emissions_norm = max(0, min(100, (50 - dades.emissions_co2) * 2))       # ejemplo
    aillament_norm = max(0, min(100, getattr(dades, "valor_aillaments", 0) * 100))
    rehabilitacio_norm = 100 if getattr(dades, "rehabilitacio_energetica", False) else 0

    score = (
        consumo_norm * pesos["pes_consum"] +
        emissions_norm * pesos["pes_emissions"] +
        aillament_norm * pesos["pes_aillament"] +
        rehabilitacio_norm * pesos["pes_rehabilitacio"]
    )

    # Retorna score + version + pesos per a trazabilitat
    return {
        "score": score,
        "version": version,
        "pesos": pesos
    }