# apps/buildings/permissions.py
from rest_framework.permissions import BasePermission

class EsAdminOPropietariEdifici(BasePermission):
    """Lectura: admin de finca o propietari d'algun habitatge de l'edifici"""
    def has_object_permission(self, request, view, obj):
        user = request.user
        if obj.administradorFinca == user:
            return True
        if obj.habitatges.filter(usuari=user).exists():
            return True
        return False


class EsAdminEdifici(BasePermission):
    """
    Escriptura: només l'administrador de finca de l'edifici.
    Per a PUT/PATCH/DELETE sobre Edifici.
    """
    def has_object_permission(self, request, view, obj):
        return obj.administradorFinca == request.user


class EsAdminOPropietariHabitatge(BasePermission):
    """
    Escriptura sobre Habitatge:
    - Admin de finca de l'edifici al qual pertany l'habitatge
    - Propietari de l'habitatge
    """
    def has_object_permission(self, request, view, obj):
        user = request.user
        # obj és un Habitatge
        if obj.edifici.administradorFinca == user:
            return True
        if obj.usuari == user:
            return True
        return False