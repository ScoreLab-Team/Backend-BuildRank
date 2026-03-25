# Testing: Security Debt y Concurrency

Este documento resume el estado actual de tests de seguridad/concurrencia y los comandos recomendados para ejecutarlos.

## Estado actual

### Security debt documentado

En `apps.accounts.tests.QueryTests` existe un test marcado como deuda:

- `test_tenant_cannot_access_other_building_detail`
- Está marcado con `@unittest.skip(...)` para no romper CI.
- Objetivo futuro: cuando se endurezca el endpoint de detalle de edificio, este test debe pasar a activo y esperar `403`.

### Concurrency tests (opt-in)

Los tests de concurrencia están desactivados por defecto y se controlan con una sola variable de entorno:

- `RUN_CONCURRENCY_TESTS=diagnostic`
  - Ejecuta test diagnóstico (no estricto).
- `RUN_CONCURRENCY_TESTS=strict`
  - Ejecuta diagnóstico + test estricto.
- Sin variable
  - Los tests de concurrencia se omiten (flujo normal).

## Comandos (PowerShell)

### 1) Suite normal completa (sin concurrencia)

```powershell
python.exe manage.py test -v 2 --keepdb
```

### 2) Suite completa + concurrencia diagnóstico

```powershell
$env:RUN_CONCURRENCY_TESTS='diagnostic'; python.exe manage.py test -v 2 --keepdb; Remove-Item Env:RUN_CONCURRENCY_TESTS -ErrorAction SilentlyContinue
```

### 3) Suite completa + concurrencia strict

```powershell
$env:RUN_CONCURRENCY_TESTS='strict'; python.exe manage.py test -v 2 --keepdb; Remove-Item Env:RUN_CONCURRENCY_TESTS -ErrorAction SilentlyContinue
```

### 4) Solo tests de accounts

```powershell
python.exe manage.py test apps.accounts -v 2 --keepdb
```

### 5) Solo test de concurrencia diagnóstico

```powershell
$env:RUN_CONCURRENCY_TESTS='diagnostic'; python.exe manage.py test apps.accounts.tests.TemporaryConcurrencyRegistrationTests -v 2 --keepdb; Remove-Item Env:RUN_CONCURRENCY_TESTS -ErrorAction SilentlyContinue
```

### 6) Solo test de concurrencia strict

```powershell
$env:RUN_CONCURRENCY_TESTS='strict'; python.exe manage.py test apps.accounts.tests.StrictConcurrencyRegistrationTests -v 2 --keepdb; Remove-Item Env:RUN_CONCURRENCY_TESTS -ErrorAction SilentlyContinue
```

## Interpretación rápida de resultados

- `OK (skipped=...)` es normal si hay tests de deuda/opt-in desactivados.
- Si ejecutas con `RUN_CONCURRENCY_TESTS='strict'`, el test estricto puede fallar mientras no se haya hardenizado el registro para evitar `500` en carrera.

## Próximo paso recomendado

Cuando se implemente el hardening de concurrencia en registro:

1. Dejar verde `StrictConcurrencyRegistrationTests`.
2. Quitar `skip` del test de security debt (`tenant` sobre detalle de edificio ajeno).
3. Mantener los comandos de este documento como guía operativa.
