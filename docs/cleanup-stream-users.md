# Limpieza de usuarios sobrantes en GetStream

## Problema

GetStream utiliza soft-delete por defecto: al eliminar un usuario desde el dashboard, el ID queda reservado permanentemente y no puede reutilizarse. Si el sistema intenta sincronizar un usuario Django con ese ID, GetStream lo rechaza.

Esto puede ocurrir si se han creado usuarios de prueba en GetStream accidentalmente (por tests que usaban credenciales reales, o por usuarios creados manualmente).

## Solución

El comando `cleanup_stream_users` detecta qué usuarios existen en GetStream pero no en Django, y los elimina con **hard-delete**, que libera el ID definitivamente.

Solo afecta a usuarios con el patrón `user_<número>`, que es el formato que usa la aplicación (`apps/chat/services.py: get_stream_user_id`). Cualquier otro usuario en GetStream no se toca.

## Tipos de eliminación en GetStream

| Tipo | Qué hace | ID reutilizable | Reversible |
|---|---|---|---|
| **Soft-delete** (dashboard) | Marca el usuario como eliminado | No | Sí, con `reactivate_user` |
| **Hard-delete** (`--delete`) | Elimina permanentemente | Sí | No |

> **Nota técnica:** La librería `stream-chat-python` serializa los booleanos Python como `"True"` (mayúscula), pero GetStream espera `"true"` (minúscula). Si se pasan booleanos Python, GetStream los ignora y hace soft-delete silenciosamente. El comando pasa strings explícitos `"true"` para evitar este problema.

## Uso

### 1. Dry-run (recomendado primero)

Lista los usuarios sobrantes sin tocar nada:

```bash
docker compose exec web python manage.py cleanup_stream_users
```

### 2. Reactivar usuarios soft-deleted

Si ya se han eliminado usuarios por error desde el dashboard (o con una versión anterior del comando), se pueden recuperar:

```bash
docker compose exec web python manage.py cleanup_stream_users --reactivate
```

> **Limitación:** GetStream excluye los usuarios eliminados de `query_users`, así que el comando solo puede reactivar usuarios que aún aparezcan en los resultados (estado activo o desactivado). Los usuarios en estado **deleted** son invisibles a la API de consulta.
>
> Para estos casos, los usuarios eliminados son inofensivos: no aparecen en ninguna consulta, no afectan a usuarios reales, y si algún usuario Django real obtiene el mismo ID en el futuro, `services.py` los reactivará automáticamente via `reactivate_user` (ver [services.py:57-66](../backend/apps/chat/services.py)).

### 3. Hard-delete definitivo

Elimina permanentemente los usuarios sobrantes y libera sus IDs:

```bash
docker compose exec web python manage.py cleanup_stream_users --delete
```

> Hard-delete también elimina los mensajes de esos usuarios en los canales (`mark_messages_deleted=true`). Para usuarios de prueba esto es el comportamiento esperado.

El comando incluye un delay de 100ms entre eliminaciones para respetar el rate-limit de GetStream.

Requiere que `STREAM_API_KEY` y `STREAM_API_SECRET` estén configurados (no funciona con `settings_test.py`).

## Prevención

Los tests ya no generan usuarios reales en GetStream:

- `manage.py test` usa automáticamente `config/settings_test.py`, que establece `STREAM_API_KEY=""` — el signal `sync_profile_to_stream` detecta que Stream no está configurado y no hace ninguna llamada.
- Los tests que necesitan claves no-vacías (como `ModerationPermissionTests`) mockean `apps.chat.services.sync_user_to_stream` en el `setUp` para evitar peticiones de red.
