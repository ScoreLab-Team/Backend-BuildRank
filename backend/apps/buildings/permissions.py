# apps/buildings/permissions.py
from rest_framework.permissions import BasePermission

class EsAdminOPropietariEdifici(BasePermission):
    """
    Permet accés si l'usuari és:
    - L'administrador de finca de l'edifici
    - Propietari (usuari) d'algun habitatge de l'edifici
    """
    def has_object_permission(self, request, view, obj):
        # obj és una instància d'Edifici
        user = request.user

        if obj.administradorFinca == user:
            return True

        if obj.habitatges.filter(usuari=user).exists():
            return True

        return False