"""
services/ocr.py

Pipeline OCR per a AdminFinca:
  1. PDF digital   → pypdf extreu text directament (ràpid)
  2. PDF escanejat → pdf2image converteix a imatges → EasyOCR
  3. Imatge        → EasyOCR directament

Retorna sempre un string amb el text extret.
"""

import logging
import os
import tempfile

import cv2
import easyocr
import numpy as np
from pdf2image import convert_from_path
from PIL import Image
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# EasyOCR es carrega una sola vegada (el model pesa ~1GB)
# gpu=False per compatibilitat màxima; canvia a True si tens CUDA
_reader = None


def _get_reader() -> easyocr.Reader:
    """Singleton: inicialitza EasyOCR només la primera vegada."""
    global _reader
    if _reader is None:
        logger.info("Carregant model EasyOCR (primera vegada, pot trigar)...")
        _reader = easyocr.Reader(['es', 'en'], gpu=False)
        logger.info("Model EasyOCR carregat.")
    return _reader


# ─── Pre-processament d'imatge ────────────────────────────────────────────────

def _preprocess_image(pil_image: Image.Image) -> np.ndarray:
    """
    Millora la qualitat de la imatge per a l'OCR:
    1. Escala de grisos
    2. Augment resolució si és massa petita
    3. Binarització adaptativa (elimina soroll de fons)
    """
    img = np.array(pil_image.convert('RGB'))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Augmentar resolució si la imatge és petita
    h, w = gray.shape
    if w < 1500:
        scale = 1500 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC)

    # Binarització adaptativa: funciona bé amb documents amb fons irregular
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15,
    )

    return binary


# ─── Estratègies d'extracció ──────────────────────────────────────────────────

def _extract_text_from_image(pil_image: Image.Image) -> str:
    """Aplica pre-processament i EasyOCR a una imatge PIL."""
    preprocessed = _preprocess_image(pil_image)
    reader = _get_reader()
    results = reader.readtext(preprocessed, detail=0, paragraph=True)
    return '\n'.join(results)


def _extract_text_from_pdf_digital(path: str) -> str | None:
    """
    Intenta extreure text d'un PDF digital (text seleccionable).
    Retorna None si el PDF és escanejat (menys de 50 caràcters per pàgina).
    """
    try:
        reader = PdfReader(path)
        pages_text = []
        for page in reader.pages:
            pages_text.append(page.extract_text() or '')

        full_text = '\n'.join(pages_text).strip()
        avg_chars = len(full_text) / max(len(reader.pages), 1)

        if avg_chars < 50:
            logger.info("PDF amb poc text (<50 car/pàg), tractat com a escanejat.")
            return None

        return full_text

    except Exception as exc:
        logger.warning("Error llegint PDF digital: %s", exc)
        return None


def _extract_text_from_pdf_scanned(path: str) -> str:
    """
    Converteix cada pàgina del PDF a imatge i aplica EasyOCR.
    Estratègia principal per a documents escanejats.
    """
    logger.info("Convertint PDF escanejat a imatges: %s", path)

    # DPI 300 = qualitat suficient per OCR sense massa memòria
    pages = convert_from_path(path, dpi=300)
    logger.info("%d pàgines trobades.", len(pages))

    texts = []
    for i, page_img in enumerate(pages):
        logger.info("  OCR pàgina %d/%d...", i + 1, len(pages))
        text = _extract_text_from_image(page_img)
        texts.append(text)

    return '\n\n--- Pàgina següent ---\n\n'.join(texts)


# ─── Funció pública ───────────────────────────────────────────────────────────

def extract_text(file_field) -> str:
    """
    Punt d'entrada principal. Rep un FileField de Django i retorna el text.

    Estratègia:
      - PDF digital  → pypdf (ràpid)
      - PDF escanejat → pdf2image + EasyOCR
      - Imatge        → EasyOCR directament

    Args:
        file_field: El FileField del model (ex: doc.fitxer)

    Returns:
        String amb el text extret. Buit si no s'ha pogut extreure res.
    """
    path = file_field.path
    extension = os.path.splitext(path)[1].lower()

    logger.info("Iniciant OCR: %s", os.path.basename(path))

    try:
        if extension == '.pdf':
            # Primer intentem extracció digital (ràpid)
            text = _extract_text_from_pdf_digital(path)
            if text:
                logger.info("PDF digital detectat, text extret sense OCR.")
                return text

            # Fallback: PDF escanejat → EasyOCR
            return _extract_text_from_pdf_scanned(path)

        elif extension in {'.jpg', '.jpeg', '.png', '.webp'}:
            pil_image = Image.open(path)
            return _extract_text_from_image(pil_image)

        else:
            logger.warning("Extensió no suportada: %s", extension)
            return ''

    except Exception as exc:
        logger.exception("Error inesperat durant l'OCR de %s: %s", path, exc)
        return ''