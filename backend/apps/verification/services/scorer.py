# apps/verification/services/scorer.py
"""
Scoring de confiança (0.0 – 1.0) sobre les dades extretes per Ollama.

El score final és una mitjana ponderada de tres dimensions:
  - Completesa  (0.40): quants camps crítics estan presents
  - Validesa    (0.35): els valors passen validacions formals
  - Credibilitat(0.25): indicadors documentals (signatura, segell, emissora)

A més del score numèric, retorna:
  - `suggeriment`: text llegible per a l'operador de revisió manual
  - `flags`:       llista de problemes detectats (per mostrar a la UI)
  - `detall`:      puntuació de cada dimensió (per a depuració/logs)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ── Configuració de pesos ────────────────────────────────────────────────────

WEIGHT_COMPLETESA   = 0.40
WEIGHT_VALIDESA     = 0.35
WEIGHT_CREDIBILITAT = 0.25

# Camps obligatoris i el seu pes dins la dimensió de completesa
CAMPS_CRITICS: dict[str, float] = {
    "nom_complet":         0.25,
    "dni_nie":             0.25,
    "carrec":              0.20,
    "adreca_finca":        0.15,
    "data_inici_vigencia": 0.10,
    "entitat_emissora":    0.05,
}

# Umbrals per al suggeriment final
LLINDAR_APROVAT   = 0.75   # score >= aquest → "Acceptable, revisió superficial"
LLINDAR_REVISAR   = 0.50   # score >= aquest → "Revisió detallada recomanada"
                            # score <  aquest → "Rebuig recomanat"

# Patrons de validació
_RE_DNI = re.compile(r'^\d{8}[A-Z]$')
_RE_NIE = re.compile(r'^[XYZ]\d{7}[A-Z]$')
_DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d')

# Col·legis i entitats emissores reconegudes (fragments, case-insensitive)
_ENTITATS_RECONEGUDES = [
    'col·legi', 'colegio', 'coapi', 'cgcafe', 'administrador',
    'ajuntament', 'ayuntamiento', 'registre', 'registro',
    'notari', 'notario', 'gestoria',
]


# ── Dataclass de resultat ────────────────────────────────────────────────────

@dataclass
class ScoreResult:
   score: float                        # 0.0 – 1.0, arrodonit a 4 decimals
   suggeriment: str                    # text per a l'operador
   flags: list[str] = field(default_factory=list)   # problemes detectats
   detall: dict[str, float] = field(default_factory=dict)  # per dimensió

   def to_dict(self) -> dict:
      return {
         "score":        self.score,
         "suggeriment":  self.suggeriment,
         "flags":        self.flags,
         "detall":       self.detall,
      }


# ── Funcions de validació individuals ───────────────────────────────────────

def _valida_dni_nie(valor: str | None) -> tuple[bool, str | None]:
   """
   Retorna (és_vàlid, flag_error).
   Accepta DNI (12345678A) i NIE (X1234567A).
   """
   if not valor:
      return False, None  # absent — no és error de format, és de completesa
   net = valor.strip().upper().replace(' ', '').replace('-', '')
   if _RE_DNI.match(net):
      return True, None
   if _RE_NIE.match(net):
      return True, None
   return False, f"DNI/NIE amb format incorrecte: '{valor}'"


def _parse_data(valor: str | None) -> date | None:
   """Intenta parsejar una data en diversos formats. Retorna None si falla."""
   if not valor:
      return None
   for fmt in _DATE_FORMATS:
      try:
         return datetime.strptime(valor.strip(), fmt).date()
      except ValueError:
         continue
   return None


def _valida_dates(inici: str | None, fi: str | None) -> list[str]:
   """
   Comprova:
   - Formats parsejables
   - data_inici < data_fi
   - data_fi no caducada (> avui)
   """
   flags = []
   d_inici = _parse_data(inici)
   d_fi    = _parse_data(fi)
   avui    = date.today()

   if inici and d_inici is None:
      flags.append(f"data_inici_vigencia no parsejable: '{inici}'")
   if fi and d_fi is None:
      flags.append(f"data_fi_vigencia no parsejable: '{fi}'")

   if d_inici and d_fi:
      if d_inici >= d_fi:
         flags.append("data_inici_vigencia >= data_fi_vigencia (incoherent)")
      if d_fi < avui:
         flags.append(f"Document caducat (data_fi: {d_fi})")

   return flags


def _valida_nom(valor: str | None) -> tuple[bool, str | None]:
   """Un nom complet ha de tenir almenys dues paraules."""
   if not valor:
      return False, None
   paraules = [p for p in valor.strip().split() if len(p) > 1]
   if len(paraules) < 2:
      return False, f"nom_complet sembla incomplet: '{valor}'"
   return True, None


def _entitat_reconeguda(valor: str | None) -> bool:
   if not valor:
      return False
   val_lower = valor.lower()
   return any(e in val_lower for e in _ENTITATS_RECONEGUDES)


# ── Dimensions de scoring ────────────────────────────────────────────────────

def _score_completesa(dades: dict[str, Any]) -> tuple[float, list[str]]:
   """
   Puntuació ponderada: cada camp crític present suma el seu pes.
   Retorna (score 0-1, flags dels camps absents).
   """
   score = 0.0
   flags = []
   for camp, pes in CAMPS_CRITICS.items():
      valor = dades.get(camp)
      if valor not in (None, '', False):
         score += pes
      else:
         flags.append(f"Camp absent: {camp}")
   return round(score, 4), flags


def _score_validesa(dades: dict[str, Any]) -> tuple[float, list[str]]:
   """
   Validació formal dels valors presents.
   Penalitza errors de format, incoherències i caducitat.
   """
   flags       = []
   penalitzacio = 0.0

   # DNI/NIE
   dni_valid, flag_dni = _valida_dni_nie(dades.get('dni_nie'))
   if dades.get('dni_nie') and not dni_valid:
      flags.append(flag_dni)
      penalitzacio += 0.35  # error crític

   # Nom complet
   nom_valid, flag_nom = _valida_nom(dades.get('nom_complet'))
   if dades.get('nom_complet') and not nom_valid:
      flags.append(flag_nom)
      penalitzacio += 0.15

   # Dates
   flags_dates = _valida_dates(
      dades.get('data_inici_vigencia'),
      dades.get('data_fi_vigencia'),
   )
   if flags_dates:
      flags.extend(flags_dates)
      penalitzacio += 0.15 * len(flags_dates)  # fins a 0.30 per dos errors

   score = max(0.0, 1.0 - penalitzacio)
   return round(score, 4), flags


def _score_credibilitat(dades: dict[str, Any]) -> tuple[float, list[str]]:
   """
   Indicadors que fan el document més o menys creïble:
   - Signatura present         +0.35
   - Segell present            +0.35
   - Entitat emissora coneguda +0.30
   """
   flags = []
   score = 0.0

   if dades.get('te_signatura'):
      score += 0.35
   else:
      flags.append("Sense signatura detectada")

   if dades.get('te_segell'):
      score += 0.35
   else:
      flags.append("Sense segell detectat")

   if _entitat_reconeguda(dades.get('entitat_emissora')):
      score += 0.30
   else:
      flags.append("Entitat emissora desconeguda o absent")

   return round(score, 4), flags


# ── Funció pública ────────────────────────────────────────────────────────────

def compute_score(dades: dict[str, Any]) -> ScoreResult:
   """
   Calcula el score de confiança a partir del dict retornat per extract_structured_data.

   Args:
      dades: Dict de camps extrets per Ollama (inclou metadades _ok, _model…)

   Returns:
      ScoreResult amb score, suggeriment, flags i detall per dimensió.

   Exemple d'ús (a tasks.py):
      from .services.extractor import extract_structured_data
      from .services.scorer   import compute_score

      dades  = extract_structured_data(ocr_text, doc_type)
      result = compute_score(dades)
      verification.score          = result.score
      verification.score_flags    = result.flags
      verification.suggeriment    = result.suggeriment
      verification.save()
   """

   # Si Ollama ha fallat, score mínim directament
   if not dades.get('_ok', False):
      error = dades.get('_error', 'Error desconegut')
      logger.warning("Scorer: extracció fallida (%s), score=0", error)
      return ScoreResult(
         score=0.0,
         suggeriment="Rebuig recomanat — extracció OCR/LLM fallida.",
         flags=[f"Error d'extracció: {error}"],
         detall={"completesa": 0.0, "validesa": 0.0, "credibilitat": 0.0},
      )

   # ── Calcula les tres dimensions ──────────────────────────────────────────
   s_comp,  flags_comp  = _score_completesa(dades)
   s_val,   flags_val   = _score_validesa(dades)
   s_cred,  flags_cred  = _score_credibilitat(dades)

   score_final = round(
      s_comp  * WEIGHT_COMPLETESA
      + s_val   * WEIGHT_VALIDESA
      + s_cred  * WEIGHT_CREDIBILITAT,
      4,
   )

   tots_flags = flags_comp + flags_val + flags_cred

   # ── Suggeriment per a l'operador ─────────────────────────────────────────
   if score_final >= LLINDAR_APROVAT:
      suggeriment = (
         f"Acceptable (score {score_final:.2f}) — "
         "revisió superficial suficient."
      )
   elif score_final >= LLINDAR_REVISAR:
      suggeriment = (
         f"Revisió detallada recomanada (score {score_final:.2f}) — "
         f"{len(tots_flags)} incidència(es) detectada(es)."
      )
   else:
      suggeriment = (
         f"Rebuig recomanat (score {score_final:.2f}) — "
         "document amb massa incidències per a aprovació automàtica."
      )

   logger.info(
      "Score final: %.4f | completesa=%.4f validesa=%.4f credibilitat=%.4f | flags=%d",
      score_final, s_comp, s_val, s_cred, len(tots_flags),
   )

   return ScoreResult(
      score=score_final,
      suggeriment=suggeriment,
      flags=tots_flags,
      detall={
         "completesa":   s_comp,
         "validesa":     s_val,
         "credibilitat": s_cred,
      },
   )