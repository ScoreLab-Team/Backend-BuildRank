# apps/verification/services/extractor.py
"""
Extracció estructurada de dades a partir de text OCR brut.

Crida Ollama (llama3.2:1b) amb un prompt dissenyat per:
- Tolerar soroll OCR (caràcters incorrectes, paraules tallades)
- Retornar sempre JSON vàlid
- No al·lucinar: si no troba un camp, retorna null
"""

import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434')
OLLAMA_MODEL = 'llama3.2:1b'
OLLAMA_TIMEOUT = 60  # segons — el model pot trigar en CPU


# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Ets un sistema d'extracció de dades de documents administratius espanyols.
El text que rebràs prové d'OCR i pot contenir errors tipogràfics, caràcters incorrectes o paraules tallades.

La teva única funció és extreure camps específics i retornar-los en JSON.

REGLES ESTRICTES:
1. Respon ÚNICAMENT amb un objecte JSON vàlid. Cap text addicional, cap explicació.
2. Si no trobes un camp o no n'estàs segur, posa null. MAI inventes dades.
3. El DNI/NIE té format: 8 dígits + lletra (DNI) o lletra + 7 dígits + lletra (NIE).
4. Les dates han d'estar en format ISO: YYYY-MM-DD. Si només tens any/mes, posa el primer dia.
5. Normalitza els noms en MAJÚSCULES."""

USER_PROMPT_TEMPLATE = """Extreu les dades d'aquest document de tipus "{doc_type}".

TEXT OCR:
---
{ocr_text}
---

Retorna EXACTAMENT aquest JSON (substitueix els valors, manté les claus):
{{
  "nom_complet": null,
  "dni_nie": null,
  "carrec": null,
  "nom_comunitat": null,
  "adreca_finca": null,
  "data_inici_vigencia": null,
  "data_fi_vigencia": null,
  "te_signatura": false,
  "te_segell": false,
  "entitat_emissora": null,
  "observacions": null
}}"""


# ── Funcions privades ─────────────────────────────────────────────────────────

def _call_ollama(prompt_system: str, prompt_user: str) -> str:
    """
    Crida a l'API d'Ollama i retorna el text de resposta.
    Usa l'endpoint /api/chat amb format de missatges.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": prompt_system},
            {"role": "user",   "content": prompt_user},
        ],
        "stream": False,
        "options": {
            "temperature": 0.0,   # determinista — no volem creativitat
            "top_p": 0.9,
            "num_predict": 512,   # suficient per al JSON de resposta
        },
    }

    response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
    response.raise_for_status()

    data = response.json()
    return data['message']['content'].strip()


def _parse_json_response(raw: str) -> dict:
    """
    Parseig robust: elimina possibles markdown fences i extreu el JSON.
    Ollama de vegades envolta la resposta amb ```json ... ```.
    """
    # Elimina fences de markdown si existeixen
    clean = raw
    if '```' in clean:
        lines = clean.split('\n')
        lines = [l for l in lines if not l.strip().startswith('```')]
        clean = '\n'.join(lines)

    # Intenta trobar el primer { i l'últim }
    start = clean.find('{')
    end = clean.rfind('}')
    if start == -1 or end == -1:
        raise ValueError(f"No s'ha trobat JSON a la resposta: {raw[:200]}")

    json_str = clean[start:end + 1]
    return json.loads(json_str)


# ── Funció pública ────────────────────────────────────────────────────────────

def extract_structured_data(ocr_text: str, doc_type: str) -> dict:
    """
    Extreu dades estructurades d'un text OCR usant Ollama.

    Args:
        ocr_text:  Text extret per OCR (pot tenir soroll)
        doc_type:  Tipus declarat per l'usuari (ex: 'certificat', 'acta_junta')

    Returns:
        Dict amb els camps extrets. Els camps no trobats són null.
        Inclou metadades del procés:
          _model, _ok, _error (si n'hi ha)
    """
    if not ocr_text or not ocr_text.strip():
        logger.warning("Text OCR buit, no es pot extreure res.")
        return _empty_result(error="Text OCR buit")

    # Limita el text a 3000 caràcters — suficient per al model petit
    # i evita superar el context window de llama3.2:3b
    text_truncat = ocr_text[:3000]
    if len(ocr_text) > 3000:
        logger.info("Text OCR truncat a 3000 caràcters (original: %d)", len(ocr_text))

    prompt_user = USER_PROMPT_TEMPLATE.format(
        doc_type=doc_type,
        ocr_text=text_truncat,
    )

    try:
        logger.info("Cridant Ollama (%s) per doc_type=%s...", OLLAMA_MODEL, doc_type)
        raw_response = _call_ollama(SYSTEM_PROMPT, prompt_user)
        logger.debug("Resposta raw Ollama: %s", raw_response[:300])

        parsed = _parse_json_response(raw_response)

        # Afegeix metadades
        parsed['_model'] = OLLAMA_MODEL
        parsed['_ok'] = True
        parsed['_raw'] = raw_response  # per traçabilitat i debug

        logger.info(
            "Extracció completada. Camps trobats: %s",
            [k for k, v in parsed.items() if v and not k.startswith('_')]
        )
        return parsed

    except requests.exceptions.ConnectionError:
        logger.error("No s'ha pogut connectar amb Ollama a %s", OLLAMA_BASE_URL)
        return _empty_result(error="Ollama no disponible")

    except requests.exceptions.Timeout:
        logger.error("Timeout esperant resposta d'Ollama (%ds)", OLLAMA_TIMEOUT)
        return _empty_result(error="Timeout Ollama")

    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Error parsejant JSON d'Ollama: %s", exc)
        return _empty_result(error=f"JSON invàlid: {exc}")

    except Exception as exc:
        logger.exception("Error inesperat a extract_structured_data: %s", exc)
        return _empty_result(error=str(exc))


def _empty_result(error: str = None) -> dict:
    """Retorna un resultat buit amb tots els camps a null."""
    return {
        "nom_complet":          None,
        "dni_nie":              None,
        "carrec":               None,
        "nom_comunitat":        None,
        "adreca_finca":         None,
        "data_inici_vigencia":  None,
        "data_fi_vigencia":     None,
        "te_signatura":         False,
        "te_segell":            False,
        "entitat_emissora":     None,
        "observacions":         None,
        "_model":               OLLAMA_MODEL,
        "_ok":                  False,
        "_error":               error,
    }


def check_ollama_available() -> bool:
    """
    Comprova si Ollama està disponible i el model carregat.
    Útil per a health checks i tests.
    """
    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5,
        )
        if response.status_code != 200:
            return False
        models = [m['name'] for m in response.json().get('models', [])]
        available = any(OLLAMA_MODEL in m for m in models)
        if not available:
            logger.warning(
                "Model %s no trobat. Models disponibles: %s",
                OLLAMA_MODEL, models
            )
        return available
    except Exception:
        return False