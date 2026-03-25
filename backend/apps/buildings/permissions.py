# apps/buildings/permissions.py
from rest_framework.permissions import BasePermission
from apps.accounts.models import RoleChoices, AccessDenialLog

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

def log_denial(request, accio, motiu, edifici_id=''):
    role = ''
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        role = request.user.profile.role
    AccessDenialLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        role=role,
        edifici_sol_licitat=str(edifici_id),
        accio=accio,
        motiu=motiu,
        ip=get_client_ip(request)
    )


class EsAdminEdifici(BasePermission):
    """
    RBAC: només rol 'admin'
    ABAC: ha de ser l'administrador de finca d'aquest edifici concret
    """
    def has_permission(self, request, view):
        # RBAC
        if not request.user.is_authenticated:
            return False
        if not hasattr(request.user, 'profile'):
            return False
        if request.user.profile.role != RoleChoices.ADMIN:
            log_denial(request, view.action, 'Rol insuficient (requerit: admin)')
            return False
        return True

    def has_object_permission(self, request, view, obj):
        # ABAC
        if obj.administradorFinca != request.user:
            log_denial(request, view.action, 'No és admin d\'aquest edifici', obj.idEdifici)
            return False
        return True


class EsAdminOPropietariEdifici(BasePermission):
    """
    RBAC: rol 'admin', 'owner' o 'tenant'
    ABAC: ha de tenir relació amb l'edifici (admin o propietari d'un habitatge)
    """
    def has_permission(self, request, view):
        # RBAC: qualsevol rol autenticat
        if not request.user.is_authenticated:
            log_denial(request, view.action, 'Usuari no autenticat')
            return False
        if not hasattr(request.user, 'profile'):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = user.profile.role

        # ABAC + RBAC combinats
        if role == RoleChoices.ADMIN and obj.administradorFinca == user:
            return True
        if role in (RoleChoices.OWNER, RoleChoices.TENANT):
            if obj.habitatges.filter(usuari=user).exists():
                return True

        log_denial(request, view.action, 'Sense relació amb l\'edifici', obj.idEdifici)
        return False


class EsAdminOPropietariHabitatge(BasePermission):
    """
    RBAC: rol 'admin', 'owner' o 'tenant'
    ABAC: ha de tenir relació amb l'habitatge concret
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            log_denial(request, view.action, 'Usuari no autenticat')
            return False
        if not hasattr(request.user, 'profile'):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        # obj és un Habitatge
        user = request.user
        role = user.profile.role

        if role == RoleChoices.ADMIN and obj.edifici.administradorFinca == user:
            return True
        if role in (RoleChoices.OWNER, RoleChoices.TENANT) and obj.usuari == user:
            return True

        log_denial(request, view.action, 'Sense relació amb l\'habitatge',
                   obj.edifici.idEdifici)
        return False