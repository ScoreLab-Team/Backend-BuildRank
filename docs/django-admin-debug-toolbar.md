# Django administration & debug toolbar

## Requisitos previos

- Haber creado un entorno virtual (`.venv`).
- Tener el repositorio actualizado con la rama `Desenvolupament` (como mínimo incluyendo el pull request #22).

---

## Configuración

### 1. Instalar dependencias

Desde la raíz del proyecto:

```bash
pip install -r backend/requirements.txt
```

### 2. Entrar en la carpeta del proyecto Django

```bash
cd backend
```

### 3. Levantar el servidor

```bash
python manage.py runserver
```

---

### 4. Acceder al Django administration

Se puede acceder desde el navegador con:

- http://127.0.0.1:8000
- http://localhost:8000

---

### 5. Crear un usuario administrador

Abrir otro terminal (con el entorno virtual activo y dentro de `backend`) y ejecutar:

```bash
python manage.py createsuperuser
```

Se solicitarán los siguientes datos:
- Email
- Contraseña (dos veces)

---

### 6. Login

Acceder al panel de administración de Django e iniciar sesión con las credenciales creadas.

---

### 7. Activar Django Debug Toolbar

Crear un archivo `.env` en la carpeta `backend` con el siguiente contenido:

```env
DEBUG=True
ENABLE_DEBUG_TOOLBAR=TRUE
```

Pasos adicionales:
1. Guardar los cambios.
2. Detener el servidor (`Ctrl + C`).
3. Volver a iniciarlo:

```bash
python manage.py runserver
```

4. Recargar la página.

Aparecerá el botón **DJDT** a la derecha. Hacer clic para abrir la barra lateral.

---

## Funcionalidades

### /admin

- **Accounts (Profiles, Users)**:
  - Añadir usuarios
  - Cambiar roles
  - Gestionar privilegios

- **Buildings (Dades energetiques, edificis, habitatges, localitzacions)**:
  - Añadir, modificar o eliminar registros sin usar SQL
  - Compatible con DBeaver (los cambios se reflejan en ambos)

---

### Toolbar

- **History**:
  - Ver requests realizados al servidor

- **SQL**:
  - Ver consultas SQL ejecutadas en la base de datos
