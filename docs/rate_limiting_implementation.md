# Rate Limiting - Implementación y Guía

## Resumen

Se ha implementado un sistema de **rate limiting** ("throttling") en los endpoints de autenticación para proteger contra:

- ✅ **Brute force attacks** (fuerza bruta en contraseñas)
- ✅ **Account enumeration** (descubrir qué emails existen)
- ✅ **Token abuse** (rotación/refresh malicioso)
- ✅ **DoS attacks** (denegación de servicio)

---

## Estructura de Archivos

```
backend/
├── config/
│   └── settings.py                   # Configuración nuevas throttle rates
├── apps/accounts/
│   ├── throttles.py                  # ← NUEVO: Custom throttle classes
│   ├── views.py                      # Actualizado: throttle_classes en views
│   ├── urls.py                       # Actualizado: RefreshView personalizado
│   └── tests.py                      # Actualizado: Agregados tests de throttling
└── docs/
    └── matriz-permisos-rbac-abac.md  # Actualizado: sección 5.4 (Rate Limiting)
```

---

## Implementación Técnica

### 1. Configuración en `settings.py`

```python
REST_FRAMEWORK = {
    ...
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '5/min',           # Anónimos: 5 req/min
        'user': '100/min',         # Usuarios auth: 100 req/min
        'login': '3/min',          # /login: 3 intentos/min
        'register': '5/hour',      # /register: 5 registros/hora
        'refresh': '20/min',       # /refresh: 20 refreshes/min
    }
}
```

### 2. Custom Throttle Classes (`throttles.py`)

Cuatro clases personalizadas:

| Clase | Scope | Límite | Uso |
|-------|-------|--------|-----|
| `LoginThrottle` | `login` | 3/min | Endpoint `/login` |
| `RegisterThrottle` | `register` | 5/hora | Endpoint `/register` |
| `RefreshThrottle` | `refresh` | 20/min | Endpoint `/refresh` |
| `AuthThrottle` | `auth` | 3/min | Fallback para auth endpoints |

Cada clase:
- Hereda de `SimpleRateThrottle`
- Define `get_cache_key()`: identifica al cliente por IP (anónimos) o user ID (autenticados)

### 3. Aplicación en Views

**RegisterView:**
```python
class RegisterView(generics.CreateAPIView):
    ...
    throttle_classes = [RegisterThrottle]  # 5 registros/hora
```

**LoginView:**
```python
class LoginView(APIView):
    ...
    throttle_classes = [LoginThrottle]  # 3 intentos/min
```

**RefreshView** (nueva):
```python
class RefreshView(TokenRefreshView):
    throttle_classes = [RefreshThrottle]  # 20 refreshes/min
```

---

## Comportamiento en Producción

### Caso 1: Usuario dentro del límite
```
POST /api/accounts/login/
→ HTTP 200 OK
```

### Caso 2: Usuario sobrepasa límite
```
POST /api/accounts/login/  (4º intento en 1 minuto)
→ HTTP 429 Too Many Requests
{
    "detail": "Request was throttled. Expected available in 45 seconds."
}
```

### Cálculos de Efectividad

**Brute Force en /login:**
- Límite: 3 intentos/min = 180/hora
- Con contraseña de 8 caracteres = 62^8 ≈ 218 billones posibilidades
- Tiempo de fuerza bruta: ~3 billones de años (¡prácticamente imposible!)

**Account Enumeration en /register:**
- Límite: 5 registros/hora por IP
- Probar ~10,000 emails: 2,000 horas = 83 días por IP
- Protección: requiere muchas IPs o tiempo prohibitivo

**Token Abuse en /refresh:**
- Límite: 20 refreshes/min
- Uso legítimo: ~1-2 refreshes por sesión activa
- Abusador: necesitaría muchas sesiones o esperar

---

## Testing

### Ejecutar la suite de tests de throttling

```bash
# Tests completos de rate limiting (en tests.py)
python manage.py test apps.accounts.tests.RateLimitingTestCase -v 2

# Test específico de throttle en login
python manage.py test apps.accounts.tests.RateLimitingTestCase.test_login_throttle_3_per_minute -v 2

# Test específico de throttle en register
python manage.py test apps.accounts.tests.RateLimitingTestCase.test_register_throttle_5_per_hour -v 2

# Test de throttle por IP
python manage.py test apps.accounts.tests.ThrottleByIPTestCase -v 2

# Test de formato de respuesta 429
python manage.py test apps.accounts.tests.RateLimitingTestCase.test_throttle_response_format -v 2
```

### Test Manual con cURL

```bash
# 1. Intentar login 4 veces rápidamente
for i in {1..4}; do
  echo "Attempt $i:"
  curl -X POST http://localhost:8000/api/accounts/login/ \
    -H "Content-Type: application/json" \
    -d '{"email":"test@test.com","password":"wrong"}' \
    -w "\nStatus: %{http_code}\n\n"
  sleep 0.1  # 100ms entre intentos
done

# Respuesta esperada en el 4º: HTTP 429
```

---

## Consideraciones de Producción

### 1. Backend de Cache

Por defecto, Django usa **in-memory cache**. En producción, usar Redis:

```python
# settings.py - Production
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}
```

**Ventaja:** Rate limits persistentes distribuidos en múltiples servidores.

### 2. Logging y Monitoreo

Registrar intentos throttled:

```python
# settings.py - Logging
LOGGING = {
    'version': 1,
    'handlers': {
        'throttle_logs': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/throttle_attempts.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
        },
    },
    'loggers': {
        'rest_framework.throttling': {
            'handlers': ['throttle_logs'],
            'level': 'WARNING',
        },
    },
}
```

### 3. Rate Limits Ajustables

Los límites pueden ajustarse según necesidades:

| Scenario | Login | Register | Refresh |
|----------|-------|----------|---------|
| Alta seguridad | 2/min | 3/hora | 10/min |
| Normal (actual) | 3/min | 5/hora | 20/min |
| Desarrollo | 10/min | 20/hora | 60/min |

Cambiar en `settings.py` → `DEFAULT_THROTTLE_RATES`

### 4. Evasión de Rate Limits (Prevención)

**Atacantes pueden intentar:**
- ✅ **IP spoofing** → Mitigado: usar IPs proxies de confianza (X-Forwarded-For)
- ✅ **Distribuir el ataque** → Mitigado: límites por hora en register
- ✅ **VPNs/Proxies** → Limitado: requerir autenticación en endpoints sensibles

**Recomendación:** En producción, usar headers de proxy de confianza:

```python
# settings.py
REST_FRAMEWORK = {
    ...
    'NUM_PROXIES': 1,  # Confiar en 1 proxy (ej: nginx, CloudFlare)
}
```

---

## Próximas Mejoras

1. **CAPTCHA en límites excedidos:** Mostrar CAPTCHA después de 3 login fallidos
2. **Verificación por email:** Reenviar código de verificación si spam detectado
3. **Dashboard de seguridad:** Mostrar intentos fallidos por IP
4. **Geolocalización:** Alertas si login desde país inesperado
5. **Rate limiting por usuario:** Además de por IP

---

## Validación

✅ Rate limiting implementado en endpoints críticos
✅ Tests de throttling agregados a `tests.py` (RateLimitingTestCase, ThrottleByIPTestCase)
✅ Matriz de permisos actualizada (sección 5.4)
✅ Documentación completa (este archivo)

**Estado:** LISTO PARA TESTING
