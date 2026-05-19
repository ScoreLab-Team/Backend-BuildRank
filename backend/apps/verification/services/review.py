# apps/verification/services/review.py
"""
Lògica de revisió manual (human in the loop).

Quan un superusuari aprova o rebutja una verificació:
  - Aprovació: assigna administradorFinca + esborra fitxers físics
  - Rebuig:    només esborra fitxers físics
  - En ambdós casos: conserva el registre històric
"""

import logging
import os

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import RoleChoices, ValidacioAdmin
from apps.verification.models import (
    AdminFincaDocumentVerification,
    AdminFincaVerificationResult,
)

logger = logging.getLogger(__name__)


def aprovar_verificacio(verification, reviewer) -> None:
    """
    Aprova una verificació:
      1. Assigna l'usuari com a administradorFinca de l'edifici
      2. Actualitza el rol del perfil a ADMIN si no ho és
      3. Desa el registre històric (AdminFincaVerificationResult)
      4. Esborra els fitxers físics
      5. Marca la verificació com a 'approved'
    """
    with transaction.atomic():
        edifici = verification.edifici
        user = verification.user

        # 1. Assigna administradorFinca
        edifici.administradorFinca = user
        edifici.save(update_fields=['administradorFinca'])
        logger.info(
            "Edifici #%s assignat a %s per %s",
            edifici.pk, user.email, reviewer.email,
        )

        # 2. Actualitza rol i estat de validació del perfil
        profile = user.profile
        camps_profile = []

        if profile.role != RoleChoices.ADMIN:
            profile.role = RoleChoices.ADMIN
            camps_profile.append('role')

        if profile.estatValidacioAdmin != ValidacioAdmin.APROVAT:
            profile.estatValidacioAdmin = ValidacioAdmin.APROVAT
            camps_profile.append('estatValidacioAdmin')

        if camps_profile:
            profile.save(update_fields=camps_profile)
            logger.info(
                "Perfil de %s actualitzat. Camps: %s",
                user.email,
                ', '.join(camps_profile),
            )

        # 3. Desa registre històric
        _desar_registre_historic(verification, reviewer, aprovada=True)

        # 4. Esborra fitxers físics
        n_esborrats = _esborrar_fitxers(verification)
        logger.info("%d fitxer(s) esborrat(s) de la verificació #%s", n_esborrats, verification.pk)

        # 5. Marca com aprovada
        verification.status = AdminFincaDocumentVerification.Status.APPROVED
        verification.save(update_fields=['status', 'updated_at'])


def rebutjar_verificacio(verification, reviewer, motiu: str = '') -> None:
    """
    Rebutja una verificació:
      1. Desa el registre històric amb el motiu
      2. Esborra els fitxers físics
      3. Marca la verificació com a 'rejected'
    """
    with transaction.atomic():
        # 0. Marca el perfil com a rebutjat si correspon
        profile = verification.user.profile
        if profile.estatValidacioAdmin != ValidacioAdmin.REBUTJAT:
            profile.estatValidacioAdmin = ValidacioAdmin.REBUTJAT
            profile.save(update_fields=['estatValidacioAdmin'])

        # 1. Registre històric
        _desar_registre_historic(verification, reviewer, aprovada=False, motiu=motiu)

        # 2. Esborra fitxers
        n_esborrats = _esborrar_fitxers(verification)
        logger.info("%d fitxer(s) esborrat(s) de la verificació #%s", n_esborrats, verification.pk)

        # 3. Marca com rebutjada
        verification.status = AdminFincaDocumentVerification.Status.REJECTED
        verification.save(update_fields=['status', 'updated_at'])

        logger.info(
            "Verificació #%s rebutjada per %s. Motiu: %s",
            verification.pk, reviewer.email, motiu or '—',
        )


# ── Helpers privats ───────────────────────────────────────────────────────────

def _desar_registre_historic(verification, reviewer, aprovada: bool, motiu: str = '') -> None:
    """
    Crea o actualitza AdminFincaVerificationResult com a registre permanent.
    Els fitxers ja no existiran, però queda constància de qui va revisar,
    quan, el score i la decisió final.
    """
    # Recull el millor extracted_data disponible per al registre
    millor_doc = (
        verification.documents
        .filter(extracted_data__isnull=False)
        .order_by('-confidence')
        .first()
    )
    extracted = millor_doc.extracted_data if millor_doc else {}

    defaults = {
        'confidence':          verification.score or 0.0,
        'nom_detectat':        extracted.get('nom_complet') or '',
        'dni_detectat':        extracted.get('dni_nie') or '',
        'carrec_detectat':     extracted.get('carrec') or '',
        'comunitat_detectada': extracted.get('nom_comunitat') or '',
        'vigencia_detectada':  bool(extracted.get('data_inici_vigencia')),
        'explicacio': (
            f"{'Aprovada' if aprovada else 'Rebutjada'} per {reviewer.email} "
            f"el {timezone.now().strftime('%d/%m/%Y %H:%M')}."
            + (f" Motiu: {motiu}" if motiu else '')
        ),
        'raw_llm_output':  extracted,
        'reviewed_by':     reviewer,
        'reviewed_at':     timezone.now(),
    }

    result, created = AdminFincaVerificationResult.objects.update_or_create(
        verification=verification,
        defaults=defaults,
    )
    action = 'creat' if created else 'actualitzat'
    logger.info("Registre històric %s per verificació #%s", action, verification.pk)


def _esborrar_fitxers(verification) -> int:
    """
    Esborra tots els fitxers físics dels documents de la verificació.
    No esborra els registres de la BD — conserva la traçabilitat.
    Retorna el nombre de fitxers esborrats.
    """
    n = 0
    for doc in verification.documents.all():
        if doc.fitxer:
            path = doc.fitxer.path
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info("  Fitxer esborrat: %s", path)
                    n += 1
                # Buida el camp FileField per evitar referències mortes
                doc.fitxer.name = ''
                doc.save(update_fields=['fitxer'])
            except OSError as exc:
                logger.error("  Error esborrant %s: %s", path, exc)
    return n