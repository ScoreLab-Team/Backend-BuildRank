# Matriz de permisos (RBAC) y criterio de acceso por edificio (ABAC)

## 1. Objetivo y alcance

Este documento describe la implementación de control de acceso del backend del proyecto BuildRank, basada en:

- **RBAC (Role-Based Access Control)**, con permisos diferenciados por rol.
- **ABAC (Attribute-Based Access Control)**, con validación de acceso por vinculación a edificio.

La descripción se presenta por endpoint y refleja el comportamiento implementado actualmente en los módulos `accounts` y `buildings`.

---

## 2. Roles definidos en el sistema

- **Inquilino** (`tenant`)
- **Administrador de Finca / Propietario** (`owner`)
- **Administrador del Sistema** (`admin`)

El modelo de perfil (`Profile`) asocia cada usuario a uno de estos roles.

---

## 3. Matriz de permisos RBAC por endpoint

### 3.1. Módulo `api/accounts/`

| Endpoint | Método | Inquilino (`tenant`) | Admin. Finca (`owner`) | Admin. Sistema (`admin`) | Implementación |
|---|---|---:|---:|---:|---|
| `/api/accounts/register/` | `POST` | ✅ | ✅ | ✅ | Público (`AllowAny`). El registro con rol `admin` se rechaza. |
| `/api/accounts/login/` | `POST` | ✅ | ✅ | ✅ | Público (`AllowAny`). Emisión de `access` y `refresh`. |
| `/api/accounts/refresh/` | `POST` | ✅ | ✅ | ✅ | Renovación de token vía SimpleJWT. |
| `/api/accounts/logout/` | `POST` | ✅ | ✅ | ✅ | Requiere autenticación (`IsAuthenticated`). |
| `/api/accounts/me/` | `GET` | ✅ | ✅ | ✅ | Requiere autenticación (`IsAuthenticated`). |
| `/api/accounts/me/edificis/` | `GET` | ✅ | ✅ | ✅ | Devuelve edificios según rol: residente vinculado, cartera de admin finca o vista global de admin sistema. |
| `/api/accounts/habitatges/{ref_cadastral}/assignar-resident/` | `PATCH` | ❌ | ✅ | ✅ | Permiso `IsAdminFinca` (owner/admin) + validación ABAC por edificio. |
| `/api/accounts/edificis/{id_edifici}/assignar-admin/` | `PATCH` | ❌ | ❌ | ✅ | Permiso exclusivo `IsAdminSistema`. |

### 3.2. Módulo `api/buildings/`

La configuración global de DRF establece autenticación obligatoria (`IsAuthenticated`) por defecto, excepto en endpoints que declaran explícitamente `AllowAny`.

| Endpoint | Método | Inquilino (`tenant`) | Admin. Finca (`owner`) | Admin. Sistema (`admin`) | Implementación |
|---|---|---:|---:|---:|---|
| `/api/buildings/edificis/` | `GET` | ✅ | ✅ | ✅ | Autenticado por política global. |
| `/api/buildings/edificis/` | `POST` | ✅ | ✅ | ✅ | Autenticado por política global. |
| `/api/buildings/edificis/{pk}/` | `GET` | ✅ | ✅ | ✅ | Autenticado por política global. |
| `/api/buildings/edificis/{pk}/` | `PUT/PATCH` | ✅ | ✅ | ✅ | Autenticado por política global. |
| `/api/buildings/carrers/autocomplete/` | `GET` | ✅ | ✅ | ✅ | Autenticado por política global. |
| `/api/buildings/habitatges/` y `/api/buildings/habitatges/{id}/` | CRUD | ✅ | ✅ | ✅ | Autenticado por política global. |
| `/api/buildings/dades_energetiques/` y `.../{id}/` | CRUD | ✅ | ✅ | ✅ | Autenticado por política global. |
| `/api/buildings/localitzacions/` y `.../{id}/` | CRUD | ✅ | ✅ | ✅ | Endpoint configurado con `AllowAny` en el `ViewSet`. |

---

## 4. Criterio ABAC por edificio

### A. Atributo de vinculación directa

**Regla lógica:** `permitir_acceso IF (usuario.edificio_id == recurso.edificio_id)`

**Aplicación implementada:**
- En `ABACMixin.check_edifici_access`, para rol residente (`tenant`) se valida que el usuario esté vinculado al edificio mediante `habitatges_on_resideix`.

### B. Atributo de cartera de gestión

**Regla lógica:** `permitir_acceso IF (recurso.edificio_id IN usuario.cartera_gestion)`

**Aplicación implementada:**
- En `ABACMixin.check_edifici_access`, para rol `owner` se comprueba que el edificio pertenezca a `edificis_administrats`.

### C. Atributo de similitud (Twin Building)

**Regla lógica:**
`permitir_contacto IF (edificio_A.tipologia == edificio_B.tipologia AND edificio_A.zona == edificio_B.zona)`

**Aplicación implementada:**
- En `ABACMixin.check_twin_building_access`, se valida igualdad de tipología y zona climática entre dos edificios.

---

## 5. Implementación técnica

### 5.1. Autenticación

- El backend utiliza **JWT** con `JWTAuthentication`.
- La configuración de SimpleJWT establece ciclos de `access` y `refresh`, rotación de refresh tokens y blacklist.
- Los endpoints de autenticación (`register`, `login`, `refresh`) son públicos según el flujo establecido.

### 5.2. Capa de servicio y validación de acceso

- Los permisos por rol se definen con clases DRF (`IsAdminSistema`, `IsAdminFinca`, `IsAuthenticated`).
- La validación ABAC por edificio se aplica a través de `ABACMixin` antes de ejecutar operaciones sensibles vinculadas a edificios.

### 5.3. Auditoría de seguridad

- Las denegaciones de acceso ABAC se registran en `AccessDenialLog`.
- El registro incluye usuario, rol, acción, motivo, IP y marca temporal.
- También se dispone de auditoría de sesión/token mediante `TokenLoginLog` para login/logout/revocación/expiración.

---

## 6. Síntesis

El proyecto incorpora un modelo de control de acceso combinado **RBAC + ABAC** con definición de roles, restricciones por atributo de edificio y trazabilidad de incidentes de seguridad. La matriz de permisos queda formalizada por endpoint y el criterio ABAC se concreta en reglas de vinculación directa, cartera de gestión y similitud de Twin Building.
