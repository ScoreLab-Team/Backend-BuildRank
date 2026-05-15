# apps/verification/tasks.py
import logging

from celery import shared_task
from django.db import transaction

from .models import (
    AdminFincaDocumentVerification,
    AdminFincaVerificationDocument,
)
from .services.ocr import extract_text
from .services.extractor import extract_structured_data, check_ollama_available
from .services.scorer import compute_score

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_verification(self, verification_id: int) -> dict:
    """
    Pipeline principal de verificació documental.

    Pas 1 (Part 2): OCR de cada document
    Pas 2 (Part 3): Extracció estructurada Ollama
    Pas 3 (Part 4): Scoring i validació            ← implementat
    """
    logger.info("Iniciant pipeline verificació #%s", verification_id)

    try:
        verification = AdminFincaDocumentVerification.objects.prefetch_related(
            'documents'
        ).get(pk=verification_id)
    except AdminFincaDocumentVerification.DoesNotExist:
        logger.error("Verificació #%s no trobada", verification_id)
        return {'error': 'not_found'}

    verification.status = AdminFincaDocumentVerification.Status.RUNNING
    verification.save(update_fields=['status'])

    try:
        # ── Pas 1: OCR ──────────────────────────────────────────────────────
        resultats_ocr = _run_ocr_pipeline(verification)

        # ── Pas 2: Extracció LLM ────────────────────────────────────────────
        resultats_extraccio = _run_extraction_pipeline(verification)

        # ── Pas 3: Scoring ───────────────────────────────────────────────────
        resultat_scoring = _run_scoring_pipeline(verification, resultats_extraccio)

        verification.status = AdminFincaDocumentVerification.Status.REVIEW
        verification.save(update_fields=['status', 'updated_at'])

        logger.info(
            "Pipeline verificació #%s completat. OCR: %d docs, Extracció: %d docs, Score: %.4f",
            verification_id, len(resultats_ocr), len(resultats_extraccio),
            resultat_scoring.get('score_final', 0),
        )
        return {
            'verification_id':       verification_id,
            'documents_processats':  len(resultats_ocr),
            'resultats_ocr':         resultats_ocr,
            'resultats_extraccio':   resultats_extraccio,
            'scoring':               resultat_scoring,
        }

    except Exception as exc:
        logger.exception(
            "Error al pipeline de verificació #%s: %s", verification_id, exc
        )
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            verification.status = AdminFincaDocumentVerification.Status.REJECTED
            verification.save(update_fields=['status', 'updated_at'])
            return {'error': str(exc), 'verification_id': verification_id}


def _run_ocr_pipeline(verification: AdminFincaDocumentVerification) -> list[dict]:
    """Executa OCR sobre tots els documents i desa el text extret."""
    resultats = []

    for doc in verification.documents.all():
        logger.info("  OCR document #%s [%s]...", doc.pk, doc.doc_type)
        try:
            text = extract_text(doc.fitxer)
            confidence = _calcular_ocr_confidence(text)

            with transaction.atomic():
                doc.ocr_text = text
                doc.confidence = confidence
                doc.save(update_fields=['ocr_text', 'confidence'])

            resultats.append({
                'document_id': doc.pk,
                'doc_type': doc.doc_type,
                'chars_extrets': len(text),
                'confidence': confidence,
                'ok': True,
            })
            logger.info(
                "  Document #%s: %d caràcters, confiança %.2f",
                doc.pk, len(text), confidence
            )

        except Exception as exc:
            logger.warning("  ✗ Error OCR document #%s: %s", doc.pk, exc)
            resultats.append({
                'document_id': doc.pk,
                'doc_type': doc.doc_type,
                'ok': False,
                'error': str(exc),
            })

    return resultats


def _run_extraction_pipeline(verification: AdminFincaDocumentVerification) -> list[dict]:
    """
    Crida Ollama per extreure dades estructurades del text OCR de cada document.
    Desa el resultat a extracted_data del document.
    """
    resultats = []

    # Comprova disponibilitat d'Ollama abans de processar
    if not check_ollama_available():
        logger.warning("Ollama no disponible, saltant extracció LLM.")
        return []

    for doc in verification.documents.filter(ocr_text__gt=''):
        logger.info("  Extracció LLM document #%s [%s]...", doc.pk, doc.doc_type)
        try:
            extracted = extract_structured_data(
                ocr_text=doc.ocr_text,
                doc_type=doc.doc_type,
            )

            with transaction.atomic():
                doc.extracted_data = extracted
                doc.save(update_fields=['extracted_data'])

            camps_trobats = [
                k for k, v in extracted.items()
                if v and not k.startswith('_')
            ]
            resultats.append({
                'document_id': doc.pk,
                'doc_type': doc.doc_type,
                'camps_trobats': camps_trobats,
                'ok': extracted.get('_ok', False),
            })
            logger.info(
                "  ✓ Document #%s: camps extrets → %s",
                doc.pk, camps_trobats
            )

        except Exception as exc:
            logger.warning(
                "  ✗ Error extracció document #%s: %s", doc.pk, exc
            )
            resultats.append({
                'document_id': doc.pk,
                'ok': False,
                'error': str(exc),
            })

    return resultats


def _run_scoring_pipeline(
    verification: AdminFincaDocumentVerification,
    resultats_extraccio: list[dict],
) -> dict:
    """
    Calcula el score de confiança per a cada document amb extracció OK
    i després agrega un score final per a tota la verificació.

    Estratègia d'agregació: màxim dels scores individuals.
    Raó: en una verificació multi-document, n'hi ha prou que UN document
    sigui de bona qualitat per considerar la verificació vàlida.
    Si la verificació té un sol document, és el seu propi màxim.

    Desa a la verificació:
      - score          → float 0-1
      - score_flags    → llista de problemes (JSONField)
      - suggeriment    → text per a l'operador
    """
    if not resultats_extraccio:
        logger.warning("  Scoring: cap resultat d'extracció disponible.")
        verification.score       = 0.0
        verification.score_flags = ["Sense dades extretes per calcular score"]
        verification.suggeriment = "Rebuig recomanat — sense dades extretes."
        verification.save(update_fields=['score', 'score_flags', 'suggeriment'])
        return {'score_final': 0.0, 'scores_per_document': []}

    scores_per_doc = []

    for doc in verification.documents.filter(extracted_data__isnull=False):
        extracted = doc.extracted_data
        if not extracted:
            continue

        logger.info("  Scoring document #%s [%s]...", doc.pk, doc.doc_type)
        result = compute_score(extracted)

        # Guarda score i flags al document individual
        with transaction.atomic():
            doc.score       = result.score
            doc.score_flags = result.flags
            doc.save(update_fields=['score', 'score_flags'])

        scores_per_doc.append({
            'document_id': doc.pk,
            'doc_type':    doc.doc_type,
            'score':       result.score,
            'flags':       result.flags,
            'detall':      result.detall,
        })
        logger.info(
            "  ✓ Document #%s: score=%.4f | %s",
            doc.pk, result.score, result.suggeriment,
        )

    if not scores_per_doc:
        score_final     = 0.0
        flags_agregats  = ["Cap document amb dades extretes vàlides"]
        suggeriment     = "Rebuig recomanat — cap document puntuable."
    else:
        # El document millor representa la verificació
        millor = max(scores_per_doc, key=lambda d: d['score'])
        score_final    = millor['score']
        flags_agregats = millor['flags']

        # Recalcula suggeriment a nivell de verificació
        from .services.scorer import LLINDAR_APROVAT, LLINDAR_REVISAR
        n_docs = len(scores_per_doc)
        if score_final >= LLINDAR_APROVAT:
            suggeriment = (
                f"Acceptable (score {score_final:.2f}, {n_docs} doc(s)) — "
                "revisió superficial suficient."
            )
        elif score_final >= LLINDAR_REVISAR:
            suggeriment = (
                f"Revisió detallada recomanada (score {score_final:.2f}, {n_docs} doc(s)) — "
                f"{len(flags_agregats)} incidència(es)."
            )
        else:
            suggeriment = (
                f"Rebuig recomanat (score {score_final:.2f}, {n_docs} doc(s)) — "
                "qualitat insuficient."
            )

    with transaction.atomic():
        verification.score       = score_final
        verification.score_flags = flags_agregats
        verification.suggeriment = suggeriment
        verification.save(update_fields=['score', 'score_flags', 'suggeriment'])

    logger.info(
        "  Score final verificació #%s: %.4f — %s",
        verification.pk, score_final, suggeriment,
    )
    return {
        'score_final':        score_final,
        'scores_per_document': scores_per_doc,
    }


def _calcular_ocr_confidence(text: str) -> float:
    """Estima la qualitat de l'OCR per heurístiques."""
    if not text or not text.strip():
        return 0.0
    total_chars = len(text)
    if total_chars < 50:
        return 0.2
    chars_estranys = sum(
        1 for c in text
        if not c.isalnum() and c not in ' \n\t.,;:()-/\'\"àáèéíïóòúüçñ·'
    )
    ratio_soroll = chars_estranys / total_chars
    if ratio_soroll > 0.3:
        return 0.4
    elif ratio_soroll > 0.15:
        return 0.65
    elif total_chars > 500:
        return 0.9
    else:
        return 0.75