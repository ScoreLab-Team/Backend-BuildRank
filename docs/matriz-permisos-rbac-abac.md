# Matriz de permisos (RBAC) y criterio de acceso por edificio (ABAC)

## 1. Objetivo y alcance

Este documento define el modelo de control de acceso de BuildRank diferenciando dos ámbitos:

- **Ámbito APP (API funcional):** controlado por RBAC + ABAC.
- **Ámbito Plataforma (Django Administration):** controlado por `is_staff` / `is_superuser`.

Política global: **por defecto, denegar**.

---

## 2. Roles oficiales del sistema

### 2.1. Roles funcionales de la aplicación (RBAC APP)

- **tenant**: residente/inquilino con acceso mínimo a su contexto.
- **owner**: propietario con acceso a sus inmuebles.
- **admin_finca**: administrador operativo de finca dentro de su cartera.

> Estos tres roles son los únicos que participan en la matriz RBAC/ABAC de endpoints de negocio.

### 2.2. Rol de sistema (fuera del RBAC APP)

- **admin_sistema**: rol de plataforma delegado a Django Administration.

Este rol **no forma parte** de la matriz RBAC funcional de la APP. Su gestión se realiza mediante:

- `is_staff` para acceso al panel de administración.
- `is_superuser` para privilegios globales de sistema.

---

## 3. Principios de autorización

1. **RBAC (quién puede):** permisos por rol funcional (`tenant`, `owner`, `admin_finca`).
2. **ABAC (sobre qué puede):** validación de pertenencia/vinculación al recurso (edificio, vivienda, dato energético).
3. **Deny by default:** si una operación no está explícitamente permitida, se responde `403`.
4. **Separación de ámbitos:** lo funcional se autoriza en API; lo técnico/global se autoriza en Django Admin.

---

## 4. Matriz RBAC/ABAC del ámbito APP

### 4.1. Criterio ABAC por rol (APP)

- **tenant**: solo recursos donde exista relación directa con su vivienda/residencia.
- **owner**: solo recursos de inmuebles/viviendas que sean de su propiedad.
- **admin_finca**: solo recursos de edificios bajo su gestión administrativa.

### 4.2. Matriz por recurso y operación (APP)

| Recurso APP           | Operación           | tenant | owner | admin_finca | ABAC requerido | Notas                                             |
| --------------------- | ------------------- | :----: | :---: | :---------: | :------------: | ------------------------------------------------- |
| Perfil propio         | `GET /me`           |   ✅   |  ✅   |     ✅      |       No       | Solo datos del usuario autenticado                |
| Perfil propio         | `PATCH /me`         |   ✅   |  ✅   |     ✅      |       No       | Solo campos permitidos                            |
| Edificios             | `GET LIST`          |  ✅\*  | ✅\*  |    ✅\*     |       Sí       | Filtrado por relación al edificio                 |
| Edificios             | `GET DETAIL`        |  ✅\*  | ✅\*  |    ✅\*     |       Sí       | Solo si el edificio está en su ámbito             |
| Edificios             | `POST`              |   ❌   |  ❌   |    ✅\*     |       Sí       | Solo para edificios dentro de su gestión definida |
| Edificios             | `PATCH/PUT`         |   ❌   | ✅\*  |    ✅\*     |       Sí       | Solo en su ámbito                                 |
| Edificios             | `DELETE`            |   ❌   |  ❌   |    ✅\*     |       Sí       | Restringido a su ámbito y política operativa      |
| Viviendas             | `GET LIST`          |  ✅\*  | ✅\*  |    ✅\*     |       Sí       | Filtrado por edificio/vivienda vinculada          |
| Viviendas             | `GET DETAIL`        |  ✅\*  | ✅\*  |    ✅\*     |       Sí       | Solo en su ámbito                                 |
| Viviendas             | `POST`              |   ❌   | ✅\*  |    ✅\*     |       Sí       | Solo en edificios autorizados                     |
| Viviendas             | `PATCH/PUT`         |   ❌   | ✅\*  |    ✅\*     |       Sí       | Solo en edificios autorizados                     |
| Viviendas             | `DELETE`            |   ❌   | ✅\*  |    ✅\*     |       Sí       | Solo en edificios autorizados                     |
| Datos energéticos     | `GET LIST`          |  ✅\*  | ✅\*  |    ✅\*     |       Sí       | Filtrado por edificio autorizado                  |
| Datos energéticos     | `GET DETAIL`        |  ✅\*  | ✅\*  |    ✅\*     |       Sí       | Solo en su ámbito                                 |
| Datos energéticos     | `POST`              |   ❌   | ✅\*  |    ✅\*     |       Sí       | Solo en edificios autorizados                     |
| Datos energéticos     | `PATCH/PUT`         |   ❌   | ✅\*  |    ✅\*     |       Sí       | Solo en edificios autorizados                     |
| Datos energéticos     | `DELETE`            |   ❌   | ✅\*  |    ✅\*     |       Sí       | Solo en edificios autorizados                     |
| Catálogos (lectura)   | `GET`               |   ✅   |  ✅   |     ✅      |       No       | Catálogo no sensible                              |
| Catálogos (escritura) | `POST/PATCH/DELETE` |   ❌   |  ❌   |     ✅      |    Opcional    | Según política de mantenimiento                   |

**Leyenda:**

- ✅ = Permitido
- ❌ = Denegado
- ✅\* = Permitido con validación ABAC previa

---

## 5. Ámbito Django Administration (Plataforma)

### 5.1. Regla de gobierno

El rol **admin_sistema** se trata como capacidad de plataforma y se administra únicamente con Django Admin.

| Ámbito                | Rol                          | Mecanismo                   | Alcance                                  |
| --------------------- | ---------------------------- | --------------------------- | ---------------------------------------- |
| Django Administration | admin_sistema                | `is_staff` / `is_superuser` | Operaciones técnicas/globales de sistema |
| API funcional APP     | tenant / owner / admin_finca | RBAC + ABAC                 | Operaciones de negocio                   |

### 5.2. Política de separación

- Usuarios funcionales (`tenant`, `owner`, `admin_finca`) **no requieren** acceso a Django Admin.
- El acceso a Django Admin se concede solo a perfiles de operación técnica.
- Las operaciones de backoffice no sustituyen las reglas ABAC de la API de negocio.

---

## 6. Reglas ABAC de referencia (APP)

### A) tenant

`permitir IF usuario está vinculado a la vivienda/recurso solicitado`

### B) owner

`permitir IF recurso.edificio pertenece al propietario autenticado`

### C) admin_finca

`permitir IF recurso.edificio pertenece a la cartera de edificios administrados`

### D) Denegación por defecto

`denegar IF no existe permiso RBAC explícito o falla ABAC`

---

## 7. Implementación recomendada en DRF

- `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`.
- Permisos por acción (`get_permissions`) para RBAC funcional.
- `get_queryset` filtrado por ABAC para `LIST`.
- Validación explícita en `retrieve/update/destroy/create` para evitar bypass por ID directo.
- Registro de denegaciones y acciones críticas en auditoría.

---

## 8. Síntesis ejecutiva

BuildRank opera con **3 roles funcionales de aplicación** (`tenant`, `owner`, `admin_finca`) bajo esquema **RBAC + ABAC** en la API de negocio, y un **rol adicional de plataforma** (`admin_sistema`) delegado a **Django Administration**. Esta separación evita mezclar privilegios técnicos con permisos funcionales y refuerza el principio de mínimo privilegio.
