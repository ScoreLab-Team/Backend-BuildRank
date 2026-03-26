# Configuración: Limpieza Automática de Tokens Expirados

## Descripción

Se ha implementado un sistema de auditoría de logins/logouts (`TokenLoginLog`) separado de los tokens activos. Además, se debe ejecutar periódicamente (diariamente) la limpieza de tokens expirados:

```bash
python manage.py cleanup_expired_tokens
```

Esto:
1. Marca en `TokenLoginLog` los tokens sin logout que ya han expirado
2. Ejecuta `flushexpiredtokens` para limpiar tablas de `simplejwt` (`OutstandingToken`, `BlacklistedToken`)
3. Reporta el estado

## Automatización en Windows

### Opción 1: Task Scheduler (Recomendado)

1. **Abre Task Scheduler** (búsqueda: "Task Scheduler")

2. **Crea nueva tarea:**
   - Nombre: `Django CleanupExpiredTokens`
   - Descripción: "Limpia tokens expirados de BuildRank cada día a las 2 AM"

3. **General tab:**
   - ✓ Run with highest privileges
   - ✓ Hidden (para que no se vea el CMD)

4. **Triggers tab:**
   - New trigger → Daily
   - Time: 02:00 (madrugada)
   - Repeat every 1 day

5. **Actions tab:**
   - Program: `C:\Windows\System32\cmd.exe`
   - Arguments: `/c cd C:\UPC\PES\Backend-BuildRank\backend && python manage.py cleanup_expired_tokens >> C:\logs\token_cleanup.log 2>&1`
   - Start in: `C:\UPC\PES\Backend-BuildRank\backend`

6. **Conditions & Settings:**
   - ✓ Run task as soon as possible if missed
   - Run for up to completion

7. **Aplica y guarda**

### Opción 2: Script Batch (.bat)

Crea `c:\UPC\PES\Backend-BuildRank\cleanup_tokens.bat`:

```batch
@echo off
cd C:\UPC\PES\Backend-BuildRank\backend
python manage.py cleanup_expired_tokens >> C:\logs\token_cleanup.log 2>&1
```

Luego en Task Scheduler, Actions tab:
- Program: `C:\UPC\PES\Backend-BuildRank\cleanup_tokens.bat`

## Verificación

### Ver logs:
```bash
# En PowerShell:
Get-Content -Path "C:\logs\token_cleanup.log" -Tail 20
```

### Probar manualmente:
```bash
cd c:\UPC\PES\Backend-BuildRank\backend
python manage.py cleanup_expired_tokens
```

Salida esperada:
```
=== Iniciando limpieza de tokens ===
✓ Marcados 3 tokens como expirados en TokenLoginLog
✓ Tokens expirados eliminados de OutstandingToken/BlacklistedToken

=== Limpieza completada ===
Total registros TokenLoginLog: 45
Sesiones activas (sin logout): 2
```

## Configuración Implementada

### Settings:
- **ACCESS_TOKEN_LIFETIME**: 15 minutos (corto → seguridad)
- **REFRESH_TOKEN_LIFETIME**: 7 días (razonable para sesiones)
- **ROTATE_REFRESH_TOKENS**: True (genera nuevo refresh en cada refresco)
- **BLACKLIST_AFTER_ROTATION**: True (revoca anterior)

### Límite de sesiones:
- **Máximo 5 sesiones activas por usuario**
- Al hacer login #6, se revoca automáticamente la sesión más antigua
- Los admins pueden tener hasta 5 también (se puede cambiar en code)

### Tablas BD:

**token_blacklist_outstandingtoken** (SimpleJWT)
- Todos los tokens emitidos (activos + inactivos + expirados)

**token_blacklist_blacklistedtoken** (SimpleJWT)
- Tokens revocados/rotados

**accounts_tokenloginlog** (BuildRank)
- Auditoría de logins/logouts para análisis
- Status: LOGIN, LOGOUT, EXPIRED, REVOKED
- No se borra (histórico completo)

## Lógica de Flujo

```
[LOGIN]
├─ Crea RefreshToken
├─ Extrae JTI
├─ Revoca sesión más antigua si hay 5+
└─ Registra en TokenLoginLog (status=LOGIN)

[LOGOUT]
├─ Valida refresh token
├─ Marca en TokenLoginLog (status=LOGOUT, logout_at=now)
└─ Blacklist en simplejwt

[CLEANUP (diario)]
├─ TokenLoginLog: marca expirados (LOGIN sin logout + pasado exp)
├─ simplejwt: borra OutstandingToken/BlacklistedToken expirados
└─ Log del resultado
```

## Troubleshooting

### Task no se ejecuta:
1. Abre "Task Scheduler" → Historial
2. Busca la tarea `Django CleanupExpiredTokens`
3. See "Last Run Result": 0x0 = OK

### Error "python no encontrado":
- Usa ruta completa: `C:\Users\{tu_usuario}\AppData\Local\Programs\Python\Python312\python.exe manage.py cleanup_expired_tokens`

### No se ve log:
- Crea directorio: `mkdir C:\logs` (en CMD como admin)

## Consulta de Datos

En Django admin (`/admin`):

1. **Auth Tokens Excepcionales**
   - Menu: Accounts → Token Login Logs
   - Filtra por Status, Usuario, Fecha
   - Ver patrones de acceso, duración de sesiones, etc.

2. **Estadísticas**:
   ```python
   from apps.accounts.models import TokenLoginLog
   from django.db.models import Count
   
   # Logins por tipo
   TokenLoginLog.objects.values('status').annotate(Count('id'))
   
   # Sesiones hoy
   from django.utils import timezone
   today = timezone.now().date()
   TokenLoginLog.objects.filter(login_at__date=today).count()
   ```

## Notas

- Los tokens expirados en `OutstandingToken` caducan automáticamente después de su `exp`. La limpieza solo es para liberar espacio en BD.
- `TokenLoginLog` es totalmente separado y nunca se borra (para auditoría/análisis).
- El límite de 5 sesiones se puede cambiar en `apps/accounts/serializers.py`, método `_enforce_session_limit(user, max_sessions=5)`.

---

Documentación creada: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
