# US51: Auditoría Básica de Actividades

## Descripción

Sistema de registro automático de todas las peticiones HTTP al backend. Cada request queda registrado en la tabla `AuditLog` sin necesidad de modificar los endpoints existentes ni los futuros.

## Arquitectura

### Modelo `AuditLog` (`apps/audit/models.py`)

| Campo | Tipo | Descripción |
|---|---|---|
| `user` | FK nullable | Usuario que hizo la petición (extraído del JWT) |
| `method` | CharField | Método HTTP (`GET`, `POST`, etc.) |
| `endpoint` | CharField | Path normalizado: `/api/buildings/:id/` |
| `resource_type` | CharField | Primer segmento del path: `buildings`, `accounts`… |
| `resource_id` | CharField | ID crudo extraído del path: `123`, `uuid-...` |
| `status_code` | SmallInt | Código de respuesta HTTP |
| `ip_address` | GenericIP | IP del cliente (respeta `X-Forwarded-For`) |
| `user_agent` | CharField | Cabecera `User-Agent` |
| `duration_ms` | PositiveInt | Duración de la petición en milisegundos |
| `timestamp` | DateTimeField | Momento del registro (auto) |

La normalización de paths sustituye IDs enteros y UUIDs por `:id`:
```
/api/buildings/123/millores/7/  →  /api/buildings/:id/millores/:id/
```

### Middleware (`apps/audit/middleware.py`)

Se ejecuta automáticamente para toda petición. Rutas excluidas del log:

- `/admin/`, `/static/`, `/media/`
- `/swagger/`, `/redoc/`, `/schema/`
- `/__debug__/`

El middleware decodifica manualmente el token JWT para obtener el usuario, ya que DRF autentica en la capa de vista, no en el middleware de Django.

Si la escritura del log falla, la excepción se captura silenciosamente para no bloquear la respuesta al cliente.

## API REST

### `GET /api/audit/logs/`

Requiere autenticación con cuenta `is_superuser`.

**Query params de filtrado:**

| Param | Ejemplo | Descripción |
|---|---|---|
| `user_id` | `42` | Logs de un usuario concreto |
| `method` | `DELETE` | Método HTTP |
| `resource_type` | `buildings` | App/recurso |
| `status_code` | `403` | Código de respuesta |
| `from_date` | `2026-05-01` | Desde fecha (ISO 8601) |
| `to_date` | `2026-05-31` | Hasta fecha (ISO 8601) |
| `page` | `2` | Página (50 resultados por página, máx. 200) |

**Ejemplo de respuesta:**

```json
{
  "count": 1234,
  "next": "http://localhost:8000/api/audit/logs/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "user": 5,
      "user_email": "user@example.com",
      "method": "DELETE",
      "endpoint": "/api/buildings/:id/",
      "resource_type": "buildings",
      "resource_id": "123",
      "status_code": 204,
      "ip_address": "192.168.1.1",
      "user_agent": "Mozilla/5.0 ...",
      "duration_ms": 45,
      "timestamp": "2026-05-19T10:30:00Z"
    }
  ]
}
```

## Panel de administración Django

Los logs son accesibles en `/admin/audit/auditlog/` con filtros por método, código de estado y tipo de recurso. La vista es de solo lectura (no se puede crear, editar ni eliminar desde el admin).

## Tests

```bash
docker compose exec web python manage.py test apps.audit
```

Cobertura:
- Normalización de paths (unitarios, sin BD)
- Permisos del endpoint (401 / 403 / 200)
- Filtrado por todos los parámetros disponibles

## Integración con frontend

El frontend consume `GET /api/audit/logs/` con el token JWT del administrador. No necesita crear, editar ni borrar nada — el backend gestiona todo automáticamente.

Campos relevantes para mostrar en la tabla del panel admin:

```
timestamp | user_email | method | endpoint | status_code | ip_address | duration_ms
```
