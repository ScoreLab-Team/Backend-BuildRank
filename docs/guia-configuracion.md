# Guía de configuración (Nginx + Gunicorn + Django)

## Requisitos previos

- Haber activado el entorno virtual (`.venv`)
- Estar en la rama **Desenvolupament** con el PRx integrado
- Tener Docker Desktop y asegurar que en settings está activado:
  - `Use the WSL 2 based engine`

---

## 1) Instalar paquetes

Desde la carpeta `backend`:

```bash
pip install -r requirements.txt
```

---

## 2) Levantar la base de datos en Docker

Desde la raíz del proyecto:

```bash
docker compose up -d db
```

Comprueba que está arriba:

```bash
docker compose ps
```

---

## 3) Variables de entorno de Django (BD)

En el archivo `.env`, verifica algo como:

```env
DEBUG=True
ENABLE_DEBUG_TOOLBAR=True
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=buildrank
DB_USER=buildrank_user
DB_PASSWORD=buildrank_pass
```

---

## 4) Configurar estáticos para conservar Django Admin

```bash
python manage.py migrate
python manage.py collectstatic --noinput
docker compose up --build
```

En otra terminal (desde la carpeta `backend` y con `.venv`):

```bash
docker compose exec web python manage.py createsuperuser
```

---

## 5) Entrar en Django Administration

En el navegador:

- `localhost`
- o `127.0.0.1`

Debería redirigir a:

http://localhost/admin/

### Problema común

Si el admin aparece sin CSS:

```bash
python manage.py collectstatic --noinput
```

---

## Logs y componentes en Docker

Puedes ver los logs en Docker Desktop:

- `db`: base de datos Postgres
- `web`: código Python + Django (DRF) + Gunicorn
- `nginx`: servidor Nginx

Más detalles en:

`docker-compose.yml`
