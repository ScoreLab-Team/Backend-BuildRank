# apps/verification/tasks.py
import logging

from celery import shared_task
from django.db import transaction

from .models import (
    AdminFincaDocumentVerification,
    AdminFincaVerificationDocument,
)
from .services.ocr import extract_text

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_verification(self, verification_id: int) -> dict:
    """
    Pipeline principal de verificació documental.

    Pas 1 (Sprint 2): OCR de cada document
    Pas 2 (Sprint 3): Extracció estructurada amb Ollama  ← pendent
    Pas 3 (Sprint 4): Scoring i validació determinista   ← pendent

    Args:
        verification_id: PK de AdminFincaDocumentVerification

    Returns:
        Dict amb resum del processament
    """
    logger.info("Iniciant pipeline verificació #%s", verification_id)

    # ── Carrega la verificació ──────────────────────────────────────────────
    try:
        verification = AdminFincaDocumentVerification.objects.prefetch_related(
            'documents'
        ).get(pk=verification_id)
    except AdminFincaDocumentVerification.DoesNotExist:
        logger.error("Verificació #%s no trobada", verification_id)
        return {'error': 'not_found'}

    # Marca com a "en procés"
    verification.status = AdminFincaDocumentVerification.Status.RUNNING
    verification.save(update_fields=['status'])

    try:
        # ── Pas 1: OCR de cada document ─────────────────────────────────────
        resultats_ocr = _run_ocr_pipeline(verification)

        # ── Pas 2: Extracció LLM (Sprint 3) ─────────────────────────────────
        # resultats_extraccio = _run_extraction_pipeline(verification)

        # ── Pas 3: Scoring (Sprint 4) ────────────────────────────────────────
        # _run_scoring_pipeline(verification, resultats_extraccio)

        # Per ara (Sprint 2): status REVIEW fins que el LLM estigui integrat
        verification.status = AdminFincaDocumentVerification.Status.REVIEW
        verification.save(update_fields=['status', 'updated_at'])

        logger.info(
            "Pipeline verificació #%s completat. Documents processats: %d",
            verification_id, len(resultats_ocr)
        )
        return {
            'verification_id': verification_id,
            'documents_processats': len(resultats_ocr),
            'resultats': resultats_ocr,
        }

    except Exception as exc:
        logger.exception(
            "Error al pipeline de verificació #%s: %s", verification_id, exc
        )
        # Reintenta fins a max_retries vegades
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            verification.status = AdminFincaDocumentVerification.Status.REJECTED
            verification.save(update_fields=['status', 'updated_at'])
            return {'error': str(exc), 'verification_id': verification_id}


def _run_ocr_pipeline(
    verification: AdminFincaDocumentVerification,
) -> list[dict]:
    """
    Executa OCR sobre tots els documents d'una verificació.
    Desa el text extret i la confiança a cada AdminFincaVerificationDocument.
    """
    resultats = []

    for doc in verification.documents.all():
        logger.info(
            "  OCR document #%s [%s]...", doc.pk, doc.doc_type
        )
        try:
            text = extract_text(doc.fitxer)
            confidence = _calcular_ocr_confidence(text)

            # Desa els resultats OCR al document
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
                "  ✓ Document #%s: %d caràcters, confiança %.2f",
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


def _calcular_ocr_confidence(text: str) -> float:
    """
    Estima la qualitat de l'OCR basant-se en heurístiques simples.

    Criteris:
    - Text buit             → 0.0
    - Massa caràcters rars  → penalització
    - Longitud adequada     → bonus

    Sprint 3: substituir per la confiança real d'EasyOCR (detail=1)
    """
    if not text or not text.strip():
        return 0.0

    total_chars = len(text)
    if total_chars < 50:
        return 0.2

    # Caràcters estranys = indicador de mala qualitat OCR
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