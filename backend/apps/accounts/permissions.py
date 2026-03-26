from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import AccessDenialLog, RoleChoices


def _get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _deny(request, accio, motiu):
    user = request.user if request.user.is_authenticated else None
    role = getattr(getattr(user, 'profile', None), 'role', '')
    AccessDenialLog.objects.create(
        user=user,
        role=role,
        accio=accio,
        motiu=motiu,
        ip=_get_client_ip(request),
    )
    raise PermissionDenied(detail=motiu)


# ---------------------------------------------------------------------------
# RBAC: permisos per rol
# ---------------------------------------------------------------------------

class IsAdminSistema(BasePermission):
    """
    Permiso: Rol 'admin' de la aplicación.
    Este es el admin de TODOS los edificios (sin filtrado ABAC), NO Django superuser.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return getattr(request.user.profile, 'role', None) == RoleChoices.ADMIN


class IsAdminFinca(BasePermission):
    """
    Permiso: Propietario/Admin de finca (owner) o Admin de aplicación (admin).
    Diferencia:
    - owner: solo SU cartera (filtrado ABAC)
    - admin: TODOS los edificios (sin ABAC)
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        role = getattr(request.user.profile, 'role', None)
        return role in (RoleChoices.ADMIN, RoleChoices.OWNER)


class IsResident(BasePermission):
    """Llogater/Propietari, Administrador de Finca o Admin del Sistema."""
    def has_permission(self, request, view):
        return request.user.is_authenticated


# ---------------------------------------------------------------------------
# ABAC: validació per atributs d'edifici
# ---------------------------------------------------------------------------

class ABACMixin:
    """
    Mixin per a vistes DRF que necessiten validació ABAC.

    Ús a la vista:
        class MevaVista(ABACMixin, APIView):
            def get(self, request, edifici_id):
                self.check_edifici_access(request, edifici_id)
                ...
    """

    def check_edifici_access(self, request, edifici_id):
        """
        Regla A: Resident – l'usuari ha de residir en un habitatge d'aquest edifici.
        Regla B: AdminFinca – l'edifici ha d'estar a la seva cartera gestionada.
        Admin del Sistema: accés total.
        """
        user = request.user
        role = getattr(getattr(user, 'profile', None), 'role', None)
        accio = f"{request.method} edifici={edifici_id}"

        if role == RoleChoices.ADMIN:
            return  # Accés total

        if role == RoleChoices.OWNER:
            # ABAC-B: l'edifici ha d'estar a la cartera de l'admin
            te_acces = user.edificis_administrats.filter(idEdifici=edifici_id).exists()
            if not te_acces:
                _deny(request, accio, "L'edifici no pertany a la cartera de gestió de l'administrador.")

        else:
            # ABAC-A: el resident ha de tenir un habitatge en aquest edifici
            te_acces = user.habitatges_on_resideix.filter(edifici__idEdifici=edifici_id).exists()
            if not te_acces:
                _deny(request, accio, "L'usuari no té vinculació directa amb aquest edifici.")

    def check_twin_building_access(self, request, edifici_a_id, edifici_b_id):
        """
        Regla C: Twin Building – els dos edificis han de compartir tipologia i zona climàtica.
        """
        from apps.buildings.models import Edifici

        accio = f"twin_building edifici_a={edifici_a_id} edifici_b={edifici_b_id}"

        try:
            a = Edifici.objects.select_related('localitzacio').get(idEdifici=edifici_a_id)
            b = Edifici.objects.select_related('localitzacio').get(idEdifici=edifici_b_id)
        except Edifici.DoesNotExist:
            _deny(request, accio, "Un o ambdós edificis no existeixen.")

        if a.tipologia != b.tipologia:
            _deny(request, accio, "Els edificis no comparteixen tipologia.")

        zona_a = getattr(a.localitzacio, 'zonaClimatica', None)
        zona_b = getattr(b.localitzacio, 'zonaClimatica', None)
        if not zona_a or not zona_b or zona_a != zona_b:
            _deny(request, accio, "Els edificis no comparteixen zona climàtica.")
