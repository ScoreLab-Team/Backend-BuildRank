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
        if request.user.profile.role not in (RoleChoices.ADMIN, RoleChoices.OWNER, RoleChoices.TENANT):
            log_denial(request, view.action, 'Rol funcional no permès')
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = user.profile.role

        # ABAC + RBAC combinats
        if role == RoleChoices.ADMIN and obj.administradorFinca == user:
            return True
        if role == RoleChoices.OWNER:
            if obj.habitatges.filter(usuari=user).exists():
                return True
        if role == RoleChoices.TENANT:
            # Tenant: només lectura per matriu de permisos
            if request.method in ('GET', 'HEAD', 'OPTIONS'):
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
        if request.user.profile.role not in (RoleChoices.ADMIN, RoleChoices.OWNER, RoleChoices.TENANT):
            log_denial(request, view.action, 'Rol funcional no permès')
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


class EsOwnerOAdminHabitatge(BasePermission):
    """
    RBAC: rol 'owner' o 'admin'
    ABAC: ha de tenir relació amb l'habitatge concret
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            log_denial(request, view.action, 'Usuari no autenticat')
            return False
        if not hasattr(request.user, 'profile'):
            return False
        if request.user.profile.role not in (RoleChoices.ADMIN, RoleChoices.OWNER):
            log_denial(request, view.action, 'Rol insuficient (requerit: owner o admin)')
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = user.profile.role

        if role == RoleChoices.ADMIN and obj.edifici.administradorFinca == user:
            return True
        if role == RoleChoices.OWNER and obj.usuari == user:
            return True

        log_denial(request, view.action, 'Sense relació owner/admin amb l\'habitatge', obj.edifici.idEdifici)
        return False


class EsOwnerOAdminDadesEnergetiques(BasePermission):
    """
    RBAC: rol 'owner' o 'admin'
    ABAC: dades energètiques del seu habitatge o edifici administrat
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            log_denial(request, view.action, 'Usuari no autenticat')
            return False
        if not hasattr(request.user, 'profile'):
            return False
        if request.user.profile.role not in (RoleChoices.ADMIN, RoleChoices.OWNER):
            log_denial(request, view.action, 'Rol insuficient (requerit: owner o admin)')
            return False
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = user.profile.role

        habitatge = Habitatge = None
        try:
            from .models import Habitatge as _Habitatge
            habitatge = _Habitatge.objects.select_related('edifici').get(dadesEnergetiques=obj)
        except Exception:
            log_denial(request, view.action, 'No es pot resoldre habitatge de dades energètiques')
            return False

        if role == RoleChoices.ADMIN and habitatge.edifici.administradorFinca == user:
            return True
        if role == RoleChoices.OWNER and habitatge.usuari == user:
            return True

        log_denial(request, view.action, 'Sense relació owner/admin amb dades energètiques', habitatge.edifici.idEdifici)
        return False