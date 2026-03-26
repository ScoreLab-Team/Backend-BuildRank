# Resumen de Suites de Tests

Este documento resume las suites de tests activas del sistema por conjunto funcional, sin detallar cada test individual. El objetivo es tener una única referencia de cobertura, propósito y ubicación del código de pruebas.

## Cobertura principal

### Accounts: autenticación, autorización y seguridad

Fichero de referencia: `backend/apps/accounts/tests.py`

Conjuntos cubiertos:

- `RBACAuthorizationTests`
  - Verifica permisos por rol en asignación de administrador de edificio.
  - Cubre acceso permitido para admin de sistema y denegación para owner/no autenticado.

- `ABACTests`
  - Verifica restricciones por ámbito de edificio.
  - Cubre escenarios IDOR al intentar operar sobre recursos fuera de la cartera autorizada.

- `AssignmentTests`
  - Valida la asignación de residentes a viviendas dentro del ámbito permitido.
  - Comprueba permisos correctos y denegación para roles sin privilegio.

- `QuerySetFilteringTests`
  - Valida filtrado de edificios visibles en `/me/edificis/`.
  - Comprueba separación por rol, protección ante fuga de datos y bloqueo de acceso cruzado.

- `SecurityTests`
  - Cubre overposting, integridad de campos sensibles y controles de registro de roles.

- `AccountUpdateTests`
  - Valida lectura y actualización de perfil propio.
  - Cubre autenticación requerida y protección frente a escalado por campo `role`.

- `AuthEndpointTests`
  - Cubre flujos de registro, login, logout, refresh y endpoint `me`.
  - Incluye validaciones funcionales del ciclo básico de autenticación.

- `TemporaryConcurrencyRegistrationTests`
  - Suite diagnóstica opt-in para detectar problemas de concurrencia en registro.

- `StrictConcurrencyRegistrationTests`
  - Suite estricta opt-in para validar hardening frente a carreras en registro.

- `RateLimitingTestCase`
  - Verifica throttling en login, register y refresh.
  - Cubre límites, respuestas `429` y comportamiento esperado del sistema de rate limiting.

- `ThrottleByIPTestCase`
  - Comprueba que el throttling se aplica por IP y no depende solo del contenido del payload.

### Buildings: validación, permisos de acceso y rendimiento

Fichero de referencia: `backend/apps/buildings/tests.py`

Conjuntos cubiertos:

- `EdificiValidationTests`
  - Valida entrada de datos de edificios y localización.
  - Combina tests vía API con validación directa de serializers para casos de borde.

- `EdificiAccessTests`
  - Verifica filtrado de queryset y control de acceso sobre edificios.
  - Cubre lectura por rol, acceso cruzado no autorizado y bloqueo de escritura para tenant.

- `EdificiEdgeCaseAndPerformanceTests`
  - Cubre recursos inexistentes y control básico de N+1 queries.
  - Sirve como suite compacta de regresión para errores de detalle y coste de consultas.

## Suites opt-in o con condiciones especiales

### Concurrencia en registro

Fichero de referencia: `backend/apps/accounts/tests.py`

- Las suites de concurrencia están desactivadas por defecto.
- Se activan con la variable de entorno `RUN_CONCURRENCY_TESTS`.
- Modos previstos:
  - `diagnostic`: activa la suite diagnóstica.
  - `strict`: activa diagnóstico y validación estricta.

### Rate limiting

Fichero de referencia: `backend/apps/accounts/tests.py`

- La cobertura de throttling reside en las suites `RateLimitingTestCase` y `ThrottleByIPTestCase`.
- La implementación funcional relacionada está en:
  - `backend/apps/accounts/throttles.py`
  - `backend/apps/accounts/views.py`
  - `backend/config/settings.py`

## Comandos útiles

### Suite de buildings

```powershell
python.exe manage.py test apps.buildings.tests -v 2 --noinput
```

### Suite de accounts

```powershell
python.exe manage.py test apps.accounts.tests -v 2 --noinput
```

### Suite completa

```powershell
python.exe manage.py test -v 2 --noinput
```

### Concurrencia diagnóstico

```powershell
$env:RUN_CONCURRENCY_TESTS='diagnostic'; python.exe manage.py test apps.accounts.tests.TemporaryConcurrencyRegistrationTests -v 2 --noinput; Remove-Item Env:RUN_CONCURRENCY_TESTS -ErrorAction SilentlyContinue
```

### Concurrencia strict

```powershell
$env:RUN_CONCURRENCY_TESTS='strict'; python.exe manage.py test apps.accounts.tests.StrictConcurrencyRegistrationTests -v 2 --noinput; Remove-Item Env:RUN_CONCURRENCY_TESTS -ErrorAction SilentlyContinue
```
