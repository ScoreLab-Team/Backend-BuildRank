# apps/buildings/scoring.py


from .models import DadesEnergetiques, LletraEnergetica, FontClassificacio, Edifici
from .versions import BHS_VERSIONS


# ---------------------------------------------------------------------------
# Mapeig BHS score → lletra energètica (A–G)
# ---------------------------------------------------------------------------

# Rangs basats en l'escala energètica europea, adaptats a la normalització 0–100 del BHS.
_RANGS_CLASSIFICACIO = [
    (85, LletraEnergetica.A),
    (70, LletraEnergetica.B),
    (55, LletraEnergetica.C),
    (40, LletraEnergetica.D),
    (25, LletraEnergetica.E),
    (10, LletraEnergetica.F),
    (0,  LletraEnergetica.G),
]

# Camps crítics: si algun és None o 0.0, les dades es consideren insuficients.
_CAMPS_CRITICS = ["consumEnergiaPrimaria", "emissionsCO2"]


def _score_a_lletra(score: float) -> str:
    """Converteix un score numèric (0–100) a la lletra energètica corresponent."""
    for llindar, lletra in _RANGS_CLASSIFICACIO:
        if score >= llindar:
            return lletra
    return LletraEnergetica.G  # Fallback de seguretat


def _te_dades_suficients(dades: DadesEnergetiques) -> bool:
    """
    Comprova que els camps crítics no siguin None ni zero.
    Retorna False si falten dades per fer una estimació fiable.
    """
    for camp in _CAMPS_CRITICS:
        valor = getattr(dades, camp, None)
        if valor is None or valor == 0.0:
            return False
    return True


# ---------------------------------------------------------------------------
# US15 — Tarea #149: Servei de classificació energètica estimada
# ---------------------------------------------------------------------------

def calcular_classificacio_estimada(edifici):
    """
    Calcula la classificació energètica estimada d'un edifici.

    Prioritat:
      0. Si l'edifici té DadesEnergetiquesOpenData amb qualificacioGlobal → font='oficial'.
         Les dades CEE oficials tenen precedència absoluta.
      1. Si TOTS els habitatges tenen qualificacioGlobal oficial → font='oficial'.
      2. Si hi ha dades energètiques suficients → font='estimada'.
      3. Si no hi ha dades suficients → font='insuficient'.
    """

    # --- Pas 0: Dades open data (CEE oficial) ---
    od = getattr(edifici, 'dades_energetiques_opendata', None)
    if od is not None and od.qualificacioGlobal:
        return {
            "classificacio": od.qualificacioGlobal,
            "font": FontClassificacio.OFICIAL,
            "detall": (
                f"Classificació obtinguda del certificat energètic oficial (open data CEE). "
                f"Lletra: {od.qualificacioGlobal}."
            ),
        }

    habitatges = edifici.habitatges.select_related('dadesEnergetiques').all()

    if not habitatges.exists():
        return {
            "classificacio": None,
            "font": FontClassificacio.INSUFICIENT,
            "detall": "L'edifici no té habitatges registrats.",
            "dades_insuficients": ["habitatges"],
        }

    # --- Pas 1: Tots els habitatges amb qualificació oficial? ---
    lletres_oficials = []
    for h in habitatges:
        dades = getattr(h, 'dadesEnergetiques', None)
        if dades and dades.qualificacioGlobal:
            lletres_oficials.append(dades.qualificacioGlobal)

    if lletres_oficials and len(lletres_oficials) == habitatges.count():
        ordre = list(LletraEnergetica.values)
        pitjor = max(lletres_oficials, key=lambda l: ordre.index(l))
        return {
            "classificacio": pitjor,
            "font": FontClassificacio.OFICIAL,
            "detall": (
                f"Classificació obtinguda a partir dels certificats oficials "
                f"de {len(lletres_oficials)} habitatge(s). "
                f"Es mostra la lletra més desfavorable ({pitjor})."
            ),
        }

    # --- Pas 2: Estimar a partir del BHS ---
    camps_que_falten = set()
    scores = []

    for h in habitatges:
        dades = getattr(h, 'dadesEnergetiques', None)
        if dades is None:
            camps_que_falten.add("dadesEnergetiques")
            continue

        if not _te_dades_suficients(dades):
            for camp in _CAMPS_CRITICS:
                valor = getattr(dades, camp, None)
                if valor is None or valor == 0.0:
                    camps_que_falten.add(camp)
            continue

        # Normalització idèntica a calcular_building_health_score v1.0
        consumo_norm   = max(0, min(100, 100 - dades.consumEnergiaPrimaria))
        emissions_norm = max(0, min(100, (50 - dades.emissionsCO2) * 2))
        aillament_norm = max(0, min(100, dades.aillamentTermic))
        rehab_norm     = 100 if dades.rehabilitacioEnergetica else 0

        score = (
            consumo_norm   * 0.40 +
            emissions_norm * 0.30 +
            aillament_norm * 0.20 +
            rehab_norm     * 0.10
        )
        scores.append(score)

    if not scores:
        return {
            "classificacio": None,
            "font": FontClassificacio.INSUFICIENT,
            "detall": "No s'ha pogut calcular la classificació estimada per manca de dades crítiques.",
            "dades_insuficients": sorted(camps_que_falten),
        }

    # --- Pas 3: Score mitjà → lletra ---
    score_mitja = sum(scores) / len(scores)
    lletra = _score_a_lletra(score_mitja)

    cobertura = len(scores)
    total = habitatges.count()
    advertencia = (
        f" Atenció: només {cobertura} de {total} habitatge(s) tenien dades suficients."
        if cobertura < total else ""
    )

    return {
        "classificacio": lletra,
        "font": FontClassificacio.ESTIMADA,
        "detall": (
            f"Classificació estimada a partir del BHS mitjà ({score_mitja:.1f}/100) "
            f"de {cobertura} habitatge(s).{advertencia} "
            f"Aquesta classificació no substitueix un certificat energètic oficial."
        ),
    }


# ---------------------------------------------------------------------------
# Càlcul del Building Health Score (BHS) — existent
# ---------------------------------------------------------------------------

def calcular_building_health_score(dades: DadesEnergetiques, version: str = "1.0"):
    """
    Calcula el Building Health Score (BHS).
    Version: la clau de BHS_VERSIONS.
    """
    if version not in BHS_VERSIONS:
        raise ValueError(f"Versió {version} no definida a BHS_VERSIONS")

    pesos = BHS_VERSIONS[version]

    consumo_norm       = max(0, min(100, (100 - getattr(dades, "consumEnergiaPrimaria", 0))))
    emissions_norm     = max(0, min(100, (50  - getattr(dades, "emissionsCO2", 0)) * 2))
    aillament_norm     = max(0, min(100, getattr(dades, "aillamentTermic", 0)))
    rehabilitacio_norm = 100 if getattr(dades, "rehabilitacioEnergetica", False) else 0

    score = (
        consumo_norm       * pesos["pes_consum"] +
        emissions_norm     * pesos["pes_emissions"] +
        aillament_norm     * pesos["pes_aillament"] +
        rehabilitacio_norm * pesos["pes_rehabilitacio"]
    )

    return {
        "score":   score,
        "version": version,
        "pesos":   pesos,
    }

# ---------------------------------------------------------------------------
# Càlcul del BHS a partir de les dades open data (DadesEnergetiquesOpenData)
# ---------------------------------------------------------------------------

def calcular_bhs_opendata(edifici, version: str = "1.0"):
    """
    Calcula el Building Health Score (BHS) d'un edifici usant les seves
    dades open data (DadesEnergetiquesOpenData), si existeixen.

    Utilitza exactament la mateixa fórmula que calcular_building_health_score,
    però prenent com a font les dades CEE en comptes de les dades d'habitatge.

    Retorna un dict:
      {
        "score":   float,        # BHS calculat (0–100)
        "version": str,
        "pesos":   dict,
      }
    O None si l'edifici no té dades open data associades.
    """
    od = getattr(edifici, 'dades_energetiques_opendata', None)
    if od is None:
        return None

    return calcular_building_health_score(od, version=version)