"""Helpers d'autorització relacionats amb verificació documental.

Regla funcional:
- si un admin finca té una verificació documental per un edifici, només pot
  gestionar-lo quan existeix una verificació APPROVED;
- mentre la verificació és pending/running/review/rejected, no té accés efectiu;
- per compatibilitat amb assignacions manuals/històriques sense verificació,
  una assignació directa sense cap verificació associada es considera vàlida.
"""

from django.db.models import Exists, OuterRef, Q

from apps.verification.models import AdminFincaDocumentVerification


def admin_assignment_is_effective(user, edifici) -> bool:
    """Retorna True si l'usuari és admin efectiu de l'edifici."""
    if not user or not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    if not edifici or edifici.administradorFinca_id != user.id:
        return False

    verifications = AdminFincaDocumentVerification.objects.filter(
        user=user,
        edifici=edifici,
    )

    if not verifications.exists():
        return True

    return verifications.filter(
        status=AdminFincaDocumentVerification.Status.APPROVED,
    ).exists()


def effective_admin_buildings_queryset(queryset, user):
    """Filtra edificis administrats visibles per un admin finca."""
    user_verifications = AdminFincaDocumentVerification.objects.filter(
        user=user,
        edifici=OuterRef("pk"),
    )
    approved_verifications = user_verifications.filter(
        status=AdminFincaDocumentVerification.Status.APPROVED,
    )

    return (
        queryset
        .filter(administradorFinca=user)
        .annotate(
            _te_verificacio_admin=Exists(user_verifications),
            _te_verificacio_admin_aprovada=Exists(approved_verifications),
        )
        .filter(
            Q(_te_verificacio_admin=False)
            | Q(_te_verificacio_admin_aprovada=True)
        )
        .distinct()
    )
