import re
import time

from django.contrib.auth import get_user_model

from .models import AuditLog

_UUID_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)
_INT_RE = re.compile(r'(?<=/)\d+(?=/|$)')

_SKIP_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
    '/swagger/',
    '/redoc/',
    '/schema/',
    '/__debug__/',
)


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = int((time.monotonic() - start) * 1000)

        if self._should_log(request):
            try:
                self._write_log(request, response, duration_ms)
            except Exception:
                pass  # no bloquear la respuesta si falla el log

        return response

    def _should_log(self, request):
        return not any(request.path.startswith(p) for p in _SKIP_PREFIXES)

    def _write_log(self, request, response, duration_ms):
        normalized, resource_type, resource_id = self._parse_path(request.path)

        AuditLog.objects.create(
            user=self._get_user(request),
            method=request.method,
            endpoint=normalized,
            resource_type=resource_type,
            resource_id=resource_id,
            status_code=response.status_code,
            ip_address=self._get_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            duration_ms=duration_ms,
        )

    def _parse_path(self, path):
        # Extraer IDs crudos antes de normalizar (el último es el recurso más específico)
        uuid_ids = _UUID_RE.findall(path)
        int_ids = _INT_RE.findall(path)
        resource_id = (uuid_ids + int_ids)[-1] if (uuid_ids or int_ids) else ''

        # Normalizar: reemplazar IDs por :id
        normalized = _UUID_RE.sub(':id', path)
        normalized = _INT_RE.sub(':id', normalized)

        # resource_type: primer segmento no vacío y no 'api'
        parts = [p for p in normalized.strip('/').split('/') if p and p != 'api']
        resource_type = parts[0] if parts else ''

        return normalized, resource_type, resource_id

    def _get_user(self, request):
        # DRF autentica JWT en la capa de vista, no en middleware.
        # Decodificamos el token manualmente para obtener el usuario.
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Bearer '):
            return None
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            token = AccessToken(auth.split(' ', 1)[1])
            User = get_user_model()
            return User.objects.get(id=token['user_id'])
        except Exception:
            return None

    def _get_ip(self, request):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded:
            return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
