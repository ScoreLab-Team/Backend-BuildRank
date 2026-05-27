"""
Custom throttle classes para endpoints de autenticación.

Implementa rate limiting más restrictivo en login, register, refresh
para prevenir brute force, user enumeration y token abuse.
"""

from rest_framework.throttling import SimpleRateThrottle


class AuthThrottle(SimpleRateThrottle):
    """
    Throttle muy restrictivo para endpoints de autenticación.
    Aplica a /login, /register, /refresh.

    - Anónimos: 3 requests/min (brute force protection)
    - Autenticados: 10 requests/min (abuse protection)
    """

    scope = 'auth'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.id
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}


class LoginThrottle(SimpleRateThrottle):
    """
    Throttle específico para /login endpoint.
    Muy restrictivo: 3 intentos por minuto por IP para evitar credential stuffing.
    """

    scope = 'login'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class RegisterThrottle(SimpleRateThrottle):
    """
    Throttle específico para /register endpoint.
    Moderado: 5 registros por hora por IP para evitar account enumeration + spam.
    """

    scope = 'register'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class RefreshThrottle(SimpleRateThrottle):
    """
    Throttle específico para /refresh endpoint.
    Moderado: 20 refreshes por minuto para evitar token abuse en acceso normal.
    """

    scope = 'refresh'

    def get_cache_key(self, request, view):
        if request.user and request.user.is_authenticated:
            ident = request.user.id
        else:
            ident = self.get_ident(request)
        return self.cache_format % {'scope': self.scope, 'ident': ident}
