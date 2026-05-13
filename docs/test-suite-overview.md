# Resumen de Suites de Tests

Este documento resume las suites de tests activas del sistema por conjunto funcional, sin detallar cada test individual. El objetivo es tener una única referencia de cobertura, propósito y ubicación del código de pruebas.

---

## Accounts — `backend/apps/accounts/tests.py`

### Autenticación y ciclo de sesión

- **`AuthEndpointTests`**
  Cubre los flujos completos de registro, login, logout, refresh y endpoint `me`. Incluye validaciones funcionales del ciclo básico de autenticación.

- **`PasswordResetTests`**
  Valida el flujo de restablecimiento de contraseña: solicitud con email existente/inexistente (no enumeración), confirmación con token válido e inválido, y el cambio efectivo de contraseña.

### Perfil y roles

- **`MeViewTests`**
  Cubre la lectura y actualización del perfil propio en `/me/`. Valida autenticación requerida, campos retornados y protección frente a modificación de campos sensibles.

- **`MeRoleViewTests`**
  Cubre el endpoint de cambio de rol propio. Valida transiciones permitidas (owner ↔ tenant) y bloqueo de roles reservados al sistema.

- **`AccountUpdateTests`**
  Valida actualización de datos de cuenta: email, nombre y protección frente a escalado por campo `role`.

- **`AdminRoleSemanticsTests`**
  Verifica que la semántica de roles esté alineada con el modelo de dominio: diferencias entre admin de sistema y admin de finca.

- **`SystemAdminMeEndpointTests`**
  Comprueba que `/me/` retorna los flags correctos (`is_superuser`, `is_system_admin`) para superusuarios vs. admins de finca.

### Control de acceso

- **`RBACAuthorizationTests`**
  Verifica permisos por rol en la asignación de administrador de edificio. Cubre acceso permitido para admin de sistema y denegación para owner/no autenticado.

- **`ABACTests`**
  Verifica restricciones por ámbito de edificio. Cubre escenarios IDOR al intentar operar sobre recursos fuera de la cartera autorizada.

- **`AssignmentTests`**
  Valida la asignación de residentes a viviendas dentro del ámbito permitido. Comprueba permisos correctos y denegación para roles sin privilegio.

- **`QuerySetFilteringTests`**
  Valida filtrado de edificios visibles en `/me/edificis/`. Comprueba separación por rol, protección ante fuga de datos y bloqueo de acceso cruzado.

- **`SecurityTests`**
  Cubre overposting, integridad de campos sensibles y controles de registro de roles.

### Rate limiting

- **`RateLimitingTestCase`**
  Verifica throttling en login, register y refresh. Cubre límites, respuestas `429` y comportamiento esperado.

- **`ThrottleByIPTestCase`**
  Comprueba que el throttling se aplica por IP y no depende solo del contenido del payload.

---

## Buildings — `backend/apps/buildings/tests.py`

### Edifici — CRUD y validación

- **`EdificiValidationTests`**
  Valida entrada de datos de edificios y localización. Combina tests vía API con validación directa de serializers para casos de borde.

- **`EdificiAccessTests`**
  Verifica filtrado de queryset y control de acceso sobre edificios. Cubre lectura por rol, acceso cruzado no autorizado y bloqueo de escritura para tenant.

- **`EdificiEdgeCaseAndPerformanceTests`**
  Cubre recursos inexistentes y control básico de N+1 queries. Suite compacta de regresión para errores de detalle y coste de consultas.

### Edifici — Desactivación lógica

- **`EdificiDesactivacioLogicaTests`**
  Comprueba que la desactivación lógica funciona correctamente: campos afectados, manager de activos, visibilidad y reactivación.

- **`EdificiDesactivacioDryRunTests`**
  Verifica el comportamiento del dry-run (sin `?confirmat=true`) y las advertencias de consistencia previas a la desactivación.

- **`EdificiDesactivacioPermisosTests`**
  Comprueba que solo el superusuario puede desactivar/reactivar. Todos los demás roles reciben `403`.

- **`EdificiAuditLogTests`**
  Verifica que `EdificiAuditLog` se crea correctamente al desactivar y reactivar, con los campos de auditoría correctos.

### Clasificación energética estimada

- **`ClassificacioEstimadaUnitatTests`**
  Tests unitarios puros sobre las funciones de scoring. Sin acceso a BD ni HTTP — muy rápidos.

- **`ClassificacioEstimadaServeiTests`**
  Tests de integración sobre `calcular_classificacio_estimada`. Cubre los tres caminos: oficial, estimada e insuficiente.

- **`ClassificacioEstimadaSerializerTests`**
  Verifica que el serializer expone correctamente `classificacio_energetica` y `classificacio_font` en la ficha del edificio.

### Open Data CEE (importación)

- **`OpenDataTipologiaTests`**
  Tests sobre `map_tipus_edifici`: mapeo de valores del CSV a `TipusEdificiOpenData`.

- **`OpenDataHelpersTests`**
  Cubre funciones helpers del command de importación: `_f`, `_bool_si`, `_clau_adreca`.

- **`ConstruirEdificiTests`**
  Tests sobre `_construir_edifici`: mapeo de campos del CSV al modelo `Edifici`.

- **`ConstruirDadesEnergetiquesTests`**
  Tests sobre `_construir_dades_energetiques`: mapeo de campos energéticos.

- **`LlegirChunkTests`**
  Tests sobre `_llegir_chunk`: lectura parcial del CSV por offset y límite.

- **`ImportarCeeCommandTests`**
  Tests de integración del command completo: flujo de importación con escritura real en BD.

- **`OpenDataClassificacioFontTests`**
  Verifica la lógica de origen de clasificación: open data → oficial, datos de usuarios → estimada.

### Permisos de acceso (permission classes)

- **`EsAdminEdificiPermissionTests`**
  Cubre `EsAdminEdifici`: acceso por rol admin y denegación para owner y no autenticado; object permission para edificios fuera de la cartera.

- **`EsAdminOPropietariEdificiPermissionTests`**
  Cubre `EsAdminOPropietariEdifici`: tenant con habitatge → GET `200`; tenant sin habitatge → `403`; tenant → PATCH `403`.

- **`EsAdminOPropietariHabitatgePermissionTests`**
  Cubre `EsAdminOPropietariHabitatge`: acceso de admin del edificio, owner del habitatge y tenant del habitatge.

- **`EsOwnerOAdminHabitatgePermissionTests`**
  Cubre `EsOwnerOAdminHabitatge`: escritura bloqueada para tenant; owner puede eliminar el suyo; owner ajeno bloqueado.

### Habitatge

- **`HabitatgeDetailSerializerTests`**
  Cubre validaciones del serializer: superficie ≤ 0, `anyReforma` en el futuro y `anyReforma` anterior a la construcción del edificio.

- **`HabitatgeViewTests`**
  Cubre `HabitatgeViewSet`: CRUD para admin y owner, visibilidad por rol y protección de escritura para tenant.

- **`TestRestriccionsHabitatge`**
  Verifica restricciones de negocio en habitatge: bloqueos de acceso y validaciones de dominio.

- **`TestFluxSolicitudHabitatge`** (US-H2)
  Valida el flujo completo de solicitud de unión a edificio: solicitud por owner/tenant, revisión y aprobación/rechazo por admin de finca.

- **`HabitatgeMeUpdateTests`**
  Cubre el endpoint `PATCH me/habitatge/<ref>/`: edición de datos básicos y update-or-create de `DadesEnergetiques`.

### Millores i simulació

- **`MilloresImplementadesViewTests`**
  Cubre la action `millores_implementades` en `EdificiViewSet`: permisos por rol y respuesta cuando no hay millores.

- **`ValidacioMilloraImplementadaTests`**
  Cubre `POST /millores-implementades/{id}/validar/`: permisos, transiciones de estado válidas e inválidas.

- **`MotorSimulacioUnitTests`**
  Tests unitarios que validan la matemática del motor de simulación de millores energéticas.

- **`MotorSimulacioEspecificUnitTests`**
  Tests unitarios para casos específicos del motor: interacciones entre millores, casos límite de cobertura.

- **`MotorSimulacioIntegrationTests`**
  Tests de integración del endpoint de previsualización de millores: respuesta correcta de la API ante peticiones del frontend.

### Otros

- **`DadesEnergetiquesViewTests`**
  Cubre `DadesEnergetiquesViewSet` y la action `dades_energetiques` de `EdificiViewSet`: acceso por rol y casos sin datos.

- **`AutocompleteCarrersTests`**
  Cubre `autocomplete_carrers`: query corta → lista vacía; query válida → resultados; sin token → `401`.

- **`TestAdminFincaAltaEdifici`** (US-AF1)
  Valida permisos, bloqueos y creación de edificios por administradores de finca: admin no aprobado bloqueado, admin aprobado puede crear.

- **`ThirdPartyServiceTests`**
  Verifica el endpoint de servicio externo: autenticación por API key y rechazo sin credenciales.

---

## Concurrencia — `tests_concurrency.py`

Ficheros de referencia:
- `backend/apps/accounts/tests_concurrency.py`
- `backend/apps/buildings/tests_concurrency.py`
- `backend/apps/tests_concurrency_utils.py` (helper compartido)

### Patrón general

Todos los tests usan `TransactionTestCase` + `threading.Barrier` para forzar solapamiento real de requests simultáneas. Validan que los endpoints responden con códigos controlados (`201`/`200`/`400`) y nunca con `500`.

Todos los casos están parametrizados con `subTest()` para cubrir diferentes volúmenes de carga sin duplicar código. Todas las clases llevan `@tag('concurrency')` y quedan **excluidas del CI normal** (`--exclude-tag=concurrency`); se ejecutan explícitamente cuando se requiere.

### Fix de producción incluido

`LoginSerializer._enforce_session_limit` tenía un TOCTOU clásico: `count()` + `create()` sin serialización. La corrección usa `@transaction.atomic` + `select_for_update()` sobre la fila del usuario (no sobre `TokenLoginLog`, que sufre phantom reads en READ COMMITTED) para garantizar que el límite de sesiones se aplica correctamente bajo concurrencia.

### `accounts/tests_concurrency.py`

- **`StrictConcurrencyRegistrationTests`**
  Registro simultáneo con el mismo email. Garantiza exactamente 1 × `201` + (N-1) × `400`, nunca `500`.
  Parametrizado: `workers ∈ [4, 8, 16]`.

- **`StrictConcurrencyLoginSessionLimitTests`**
  Logins simultáneos del mismo usuario. Verifica que el límite de sesiones activas (`max_sessions=5`) no se supera bajo concurrencia.
  Parametrizado por `(sesiones_previas, workers)`: `(0,6)`, `(3,6)`, `(4,8)`, `(5,8)`.

- **`StrictConcurrencyAccountEmailUpdateTests`**
  N usuarios cambian su email al mismo valor objetivo simultáneamente. Garantiza exactamente 1 × `200` + (N-1) × `400`, nunca `500`.
  Parametrizado: `workers ∈ [4, 6]`.

### `buildings/tests_concurrency.py`

- **`StrictConcurrencyHabitatgeCreateTests`**
  Creación simultánea de un `Habitatge` con la misma `referenciaCadastral` (PK). El `UniqueValidator` de DRF introduce un TOCTOU SELECT→INSERT; el handler de `IntegrityError` en `perform_create` garantiza `400` en lugar de `500`.
  Parametrizado: `workers ∈ [4, 8, 16]`.

- **`StrictConcurrencySolicitarAccesTests`**
  N usuarios solicitan acceso al mismo habitatge simultáneamente. La view comprueba `if habitatge.usuari:` y luego guarda `solicitant` (last-writer-wins). Verifica que ninguno recibe `500` y que exactamente un `solicitant` queda registrado en BD.
  Parametrizado: `concurrent_users ∈ [2, 4, 6]`.

- **`StrictConcurrencyResidentAssignmentTests`**
  Un admin asigna N residentes distintos al mismo habitatge simultáneamente. Sin constraints UNIQUE implicadas: se verifica que todas las respuestas son `200` y que exactamente un residente queda asignado (last-writer-wins).
  Parametrizado: `workers ∈ [2, 4]`.

---

## Comandos útiles

### Suite rápida (excluye concurrencia) — usar en desarrollo y CI

```powershell
# Solo accounts
python manage.py test apps.accounts.tests --exclude-tag=concurrency -v 2 --noinput

# Solo buildings
python manage.py test apps.buildings.tests --exclude-tag=concurrency -v 2 --noinput

# Suite completa sin concurrencia
python manage.py test apps.accounts apps.buildings --exclude-tag=concurrency -v 2 --noinput
```

### Suite de concurrencia — ejecutar explícitamente

```powershell
# Requiere BD real (PostgreSQL). En local, levantar docker compose primero.
docker compose exec web python manage.py test apps.accounts apps.buildings --tag=concurrency -v 2 --noinput
```

### Con cobertura (formato CI)

```powershell
coverage run manage.py test apps.accounts apps.buildings --exclude-tag=concurrency -v 2
coverage report
coverage xml
```
