# Guía de configuración (Nginx + Gunicorn)

## Requisitos previos

- Haber activado el entorno virtual (`.venv`)
- Estar en la rama **Desenvolupament** con el PR#41 integrado
- Tener Docker Desktop y asegurar que en settings está activado:
  - `Use the WSL 2 based engine`

---

## 1) Levantar Docker

Desde la raíz del proyecto:

```bash
docker compose up --build -d
```

Comprobar estado:

```bash
docker compose ps
```

---

## 2) Variables de entorno de Django (BD)

En el archivo `.env`, verifica algo como:

```env
DEBUG=True
ENABLE_DEBUG_TOOLBAR=True
DB_HOST=db
DB_PORT=5432
DB_NAME=buildrank
DB_USER=buildrank_user
DB_PASSWORD=buildrank_pass
```

---

## 3) Configurar estáticos para conservar Django Admin

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py createsuperuser
```

---

## 4) Entrar en Django Administration

En el navegador:

- `localhost`
- o `127.0.0.1`

Debería redirigir a:

http://localhost/admin/

---

## Logs y componentes en Docker

Puedes ver los logs en Docker Desktop:

- `db`: base de datos Postgres
- `web`: código Python (DRF) + Gunicorn
- `nginx`: proxy inverso Nginx

Más detalles en:

`docker-compose.yml`

---

## Comandos útiles

### Logs y diagnóstico

```bash
docker compose logs -f web
docker compose logs -f nginx
docker compose logs -f db
```

### Operación diaria

Levantar:

```bash
docker compose up -d
```

Parar conservando datos:

```bash
docker compose down
```

Parar y borrar volúmenes (elimina la DB de desarrollo):

```bash
docker compose down -v
```

### Problema común

Si el admin aparece sin CSS:

```bash
docker compose exec web python manage.py collectstatic --noinput
docker compose restart nginx
```

---
