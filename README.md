# BuildRank Backend

Backend de **BuildRank**, una plataforma orientada a promoure un ús més responsable i sostenible de l’energia als edificis.

Aquest repositori conté la part servidor del projecte. El backend gestiona la lògica de negoci, l’autenticació, els permisos, la persistència de dades i l’exposició de la API que consumeix el frontend.

---

## Què és BuildRank

BuildRank és un sistema pensat per ajudar a gestionar i entendre millor l’estat energètic dels edificis. Permet consultar informació, comparar edificis, calcular indicadors, simular millores i donar suport a funcionalitats associades a la plataforma.

En termes pràctics, el backend és la capa que:

- exposa una API REST perquè el frontend pugui operar
- valida les dades que arriben al sistema
- autentica usuaris i controla permisos
- consulta, crea i actualitza informació persistent
- aplica la lògica interna del projecte
- calcula o dona suport a mètriques del domini
- integra funcionalitats de millores i simulacions
- prepara serveis que poden ser consumits per altres equips

Dit d’una manera simple: si el frontend és la part visual que veu l’usuari, el backend és la part que decideix, comprova, processa i guarda la informació.

---

## Tecnologies principals

- **Python**
- **Django**
- **Django REST Framework**
- **JWT amb SimpleJWT**
- **PostgreSQL**
- **Docker**
- **Docker Compose**
- **Nginx**
- **Gunicorn**
- **django-cors-headers**
- **GitHub Actions**
- **DBeaver**
- **Postman**

---

## Arquitectura general

El flux principal del sistema és:

```text
Frontend Flutter
→ Nginx
→ Gunicorn
→ Django REST Framework
→ PostgreSQL
```

En l’arquitectura actual amb Docker i Nginx, el frontend no parla directament amb Gunicorn ni amb PostgreSQL. El frontend envia peticions HTTP a Nginx. Nginx les redirigeix cap al backend Django executat amb Gunicorn. Django aplica permisos, validacions i lògica de negoci. PostgreSQL desa la informació persistent.

---

## Funcionalitats generals del backend

Aquest backend dona suport a funcionalitats com:

- registre d’usuaris
- login i logout
- autenticació amb JWT
- refresh de tokens
- consulta de l’usuari autenticat
- gestió de perfils
- rols diferenciats
- control d’accés segons rol i context
- alta i consulta d’edificis
- localitzacions i autocompletat de carrers
- dades energètiques
- classificació energètica estimada
- Building Health Score
- rànquing i posicionament
- catàleg de millores
- motor de simulació
- simulacions preview
- millores implementades
- base per a validacions, auditoria i administració

Algunes funcionalitats poden estar en estat parcial o en evolució segons la branca i l’estat del sprint.

---

## Rols del sistema

A nivell funcional, el sistema treballa amb aquests rols principals:

- **admin**: administrador de finca o rol amb capacitats de gestió
- **owner**: propietari
- **tenant**: llogater

Els permisos no depenen només del nom del rol. També depenen del context de cada acció. Això vol dir que dues persones amb el mateix rol no necessàriament tenen accés als mateixos recursos si no estan vinculades al mateix edifici o àmbit de gestió.

---

## Administració interna de Django

A banda dels rols funcionals de l’aplicació, el projecte permet crear un superusuari de Django:

```bash
python manage.py createsuperuser
```

Si es treballa amb Docker Compose:

```bash
docker compose exec web python manage.py createsuperuser
```

Aquest usuari serveix per accedir al panell intern de Django Admin i gestionar dades del sistema en entorns de desenvolupament o staging.

---

## Autenticació

L’autenticació es basa en **JWT**.

Quan un usuari inicia sessió correctament, el backend retorna els tokens necessaris perquè el frontend pugui continuar fent peticions autenticades.

En les rutes protegides, el frontend ha d’enviar el token d’accés a la capçalera:

```http
Authorization: Bearer <access_token>
```

El sistema també disposa d’endpoint de refresh i logout.

---

## Endpoints principals

Les rutes poden evolucionar amb el projecte, però actualment el frontend centralitza aquests endpoints a `api_config.dart`.

### Accounts i autenticació

```text
POST /api/accounts/register/
POST /api/accounts/login/
POST /api/accounts/refresh/
POST /api/accounts/logout/
GET  /api/accounts/me/
GET  /api/accounts/me/edificis/
```

### Buildings

```text
GET  /api/buildings/carrers/autocomplete/
GET  /api/buildings/localitzacions/
GET  /api/buildings/edificis/
POST /api/buildings/edificis/
GET  /api/buildings/edificis/<idEdifici>/
```

### Millores i simulacions

```text
GET  /api/buildings/millores/
POST /api/buildings/edificis/<idEdifici>/simulacions/preview/
GET  /api/buildings/edificis/<idEdifici>/simulacions/
GET  /api/buildings/edificis/<idEdifici>/millores-implementades/
```

---

## Requisits previs

Abans de començar, convé tenir instal·lat:

- **Git**
- **Python 3**
- **pip**
- **Docker Desktop** o **Docker Engine**
- **Docker Compose**
- opcionalment, **DBeaver**
- opcionalment, **Postman**

En el flux actual del projecte, PostgreSQL no s’ha d’instal·lar necessàriament de manera nativa. La forma recomanada és utilitzar Docker.

---

## Onboarding ràpid

La seqüència recomanada actual és:

1. clonar el repositori
2. situar-se a la branca `Desenvolupament`
3. crear o revisar el fitxer `.env`
4. aixecar els serveis amb Docker Compose
5. aplicar migracions
6. crear superusuari si cal
7. executar tests o checks
8. comprovar que Nginx respon
9. provar endpoints amb Postman o frontend
10. obrir Pull Request quan el canvi estigui validat

---

## Clonar el repositori

```bash
git clone <URL_DEL_REPOSITORI_BACKEND>
cd <NOM_DEL_REPOSITORI_BACKEND>
```

Situar-se a la branca d’integració:

```bash
git checkout Desenvolupament
git pull
```

Entrar a la carpeta on viu `manage.py`, si el projecte està dins d’una subcarpeta:

```bash
cd backend
```

---

## Configuració amb Docker Compose

El flux recomanat és aixecar el backend amb Docker Compose.

```bash
docker compose up -d --build
```

Aquesta comanda construeix i aixeca els serveis en segon pla.

Serveis principals:

```text
db      → PostgreSQL
web     → Django / Gunicorn
nginx   → entrada HTTP del sistema
```

Comprovar l’estat:

```bash
docker compose ps
```

Consultar logs:

```bash
docker compose logs -f db
docker compose logs -f web
docker compose logs -f nginx
```

Aturar els serveis mantenint dades:

```bash
docker compose down
```

Aturar i eliminar volums locals:

```bash
docker compose down -v
```

Utilitza `down -v` només si vols començar de zero i perdre les dades locals.

---

## Fitxer `.env`

El backend necessita un fitxer `.env` amb la configuració de l’entorn. Aquest fitxer no s’ha de pujar al repositori si conté secrets o credencials.

Exemple orientatiu per a Docker Compose:

```env
DEBUG=True
SECRET_KEY=<SECRET_LOCAL>

DB_NAME=buildrank
DB_USER=buildrank_user
DB_PASSWORD=buildrank_pass
DB_HOST=db
DB_PORT=5432

ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,10.0.2.2,nattech.fib.upc.edu

CORS_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1,http://10.0.2.2,http://nattech.fib.upc.edu:40400
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1,http://10.0.2.2,http://nattech.fib.upc.edu:40400

ENABLE_DEBUG_TOOLBAR=False
```

Quan Django s’executa dins de Docker Compose, `DB_HOST` normalment ha de ser:

```env
DB_HOST=db
```

Si s’executa Django directament al sistema amb `runserver` i PostgreSQL està en Docker exposat al host, pot caldre:

```env
DB_HOST=127.0.0.1
```

---

## Preparar Django dins de Docker

Aplicar migracions:

```bash
docker compose exec web python manage.py migrate
```

Crear superusuari:

```bash
docker compose exec web python manage.py createsuperuser
```

Recollir estàtics si s’utilitza Nginx:

```bash
docker compose exec web python manage.py collectstatic --noinput
```

Comprovar configuració:

```bash
docker compose exec web python manage.py check
```

---

## Provar que el backend respon

Si Nginx està exposat al port HTTP local:

```bash
curl -I http://localhost
```

Si Nginx està exposat a un altre port, per exemple `8080`:

```bash
curl -I http://localhost:8080
```

Comprovar admin:

```bash
curl -I http://localhost/admin/
```

---

## Execució local alternativa sense Nginx

També es pot executar el backend directament amb entorn virtual i `runserver`. Aquest mode és útil per depurar, però no representa el flux complet amb Nginx i Gunicorn.

Crear entorn virtual:

```bash
python -m venv .venv
```

Activar-lo a Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Activar-lo a Linux o macOS:

```bash
source .venv/bin/activate
```

Instal·lar dependències:

```bash
pip install -r requirements.txt
```

Aplicar migracions:

```bash
python manage.py migrate
```

Crear superusuari:

```bash
python manage.py createsuperuser
```

Arrencar servidor de desenvolupament:

```bash
python manage.py runserver
```

Per defecte quedarà disponible a:

```text
http://127.0.0.1:8000/
```

Si es prova el frontend Flutter contra aquest mode des de l’emulador Android, cal usar:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

---

## Base de dades local amb Docker només PostgreSQL

Si no vols aixecar tot el stack i només vols PostgreSQL en Docker, pots crear un `compose.yaml` auxiliar:

```yaml
services:
  db:
    image: postgres:16
    container_name: buildrank-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: buildrank
      POSTGRES_USER: buildrank_user
      POSTGRES_PASSWORD: buildrank_pass
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data

volumes:
  pg_data:
```

Aixecar PostgreSQL:

```bash
docker compose up -d
```

En aquest cas, si Django corre fora de Docker, el `.env` hauria d’utilitzar:

```env
DB_HOST=127.0.0.1
DB_PORT=5432
```

Si el port `5432` està ocupat, pots canviar el mapeig a:

```yaml
ports:
  - "5433:5432"
```

i després posar:

```env
DB_PORT=5433
```

---

## DBeaver

Per inspeccionar PostgreSQL amb DBeaver:

Si PostgreSQL està exposat al host:

```text
Host: localhost
Port: 5432
Database: buildrank
Username: buildrank_user
Password: buildrank_pass
```

Si has canviat el port a `5433`, utilitza `5433`.

---

## Tests i qualitat

El projecte incorpora proves per validar parts importants del backend.

Àrees prioritàries:

- autenticació
- tokens
- permisos
- rols
- accés segons edifici o context
- validacions de dades
- models i serializers
- edificis
- dades energètiques
- simulacions
- millores
- migracions

Executar tests principals:

```bash
docker compose exec web python manage.py test apps.accounts apps.buildings
```

O bé, sense Docker:

```bash
python manage.py test apps.accounts apps.buildings
```

Si `coverage` està instal·lat dins del contenidor:

```bash
docker compose exec web coverage run manage.py test apps.accounts apps.buildings
docker compose exec web coverage report
docker compose exec web coverage xml
```

Si apareix aquest error:

```text
coverage: executable file not found in $PATH
```

vol dir que `coverage` no està instal·lat dins del contenidor. Cal afegir-lo a `requirements.txt` o executar només `python manage.py test`.

---

## Migracions

Les migracions formen part de la història real de la base de dades. No s’han d’eliminar ni reescriure sense revisar-ne l’impacte.

Comandes útils:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py showmigrations
```

Sense Docker:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
```

Bones pràctiques amb migracions:

- revisar-les abans de fer commit
- no eliminar migracions ja compartides sense acord de l’equip
- comprovar que s’apliquen en una base neta
- incloure-les a la Pull Request si s’han canviat models
- validar que el frontend continua rebent els camps esperats

---

## CORS i CSRF

Com que el frontend pot executar-se des d’un emulador Android, un mòbil físic o staging, és important configurar correctament CORS i CSRF.

Casos habituals:

```text
http://10.0.2.2
http://192.168.1.13
http://nattech.fib.upc.edu:40400
```

Si el frontend mostra errors de CORS o CSRF, cal revisar:

```env
CORS_ALLOWED_ORIGINS=...
CSRF_TRUSTED_ORIGINS=...
ALLOWED_HOSTS=...
```

També cal comprovar si el frontend està apuntant al port correcte. Amb Docker + Nginx, el frontend normalment parla amb Nginx i no amb `:8000`.

---

## Staging a Virtech

Virtech és l’entorn de staging del projecte. Serveix per validar el backend en una màquina compartida i accessible externament.

Flux conceptual:

```text
Internet
→ nattech.fib.upc.edu:40400
→ VM BuildRank
→ port intern 8080
→ Nginx
→ Gunicorn
→ Django REST Framework
→ PostgreSQL
```

Accés SSH:

```bash
ssh alumne@nattech.fib.upc.edu -p 22040
```

Carpeta recomanada del projecte:

```bash
cd /opt/buildrank/app
```

Aixecar staging:

```bash
docker-compose -f docker-compose.virtech.yml up -d --build
```

Aplicar migracions:

```bash
docker-compose -f docker-compose.virtech.yml exec web python manage.py migrate
```

Recollir estàtics:

```bash
docker-compose -f docker-compose.virtech.yml exec web python manage.py collectstatic --noinput
```

Veure serveis:

```bash
docker-compose -f docker-compose.virtech.yml ps
```

Veure logs:

```bash
docker-compose -f docker-compose.virtech.yml logs -f web
docker-compose -f docker-compose.virtech.yml logs -f nginx
docker-compose -f docker-compose.virtech.yml logs -f db
```

Provar des de la VM:

```bash
curl -I http://localhost:8080
curl -I http://localhost:8080/admin/
```

Provar des de fora:

```text
http://nattech.fib.upc.edu:40400
```

---

## Problemes habituals

### El backend no respon

Comprova serveis:

```bash
docker compose ps
```

Consulta logs:

```bash
docker compose logs -f web
docker compose logs -f nginx
```

### El Django Admin apareix sense CSS

Executa:

```bash
docker compose exec web python manage.py collectstatic --noinput
docker compose restart nginx
```

### Les migracions fallen

Comprova estat:

```bash
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py migrate
```

### El frontend no connecta

Revisa:

- que Nginx està aixecat
- que el frontend apunta a la URL correcta
- que `ALLOWED_HOSTS` inclou el host necessari
- que CORS i CSRF estan configurats
- que no s’està usant `:8000` quan el flux és Docker + Nginx

### El port 5432 està ocupat

Canvia el port exposat de PostgreSQL o atura el servei que ocupa el port.

### El port 80 està ocupat

Si Nginx local o un altre servei ocupa el port, cal aturar-lo o canviar el mapeig de ports del compose.

---

## Flux de treball recomanat amb Git

1. actualitzar `Desenvolupament`
2. crear branca pròpia
3. fer els canvis
4. provar en local
5. executar tests o checks
6. revisar migracions
7. fer commit
8. pujar branca
9. obrir Pull Request

Exemple:

```bash
git checkout Desenvolupament
git pull
git switch -c feature/nom-del-canvi
git add .
git commit -m "feat: descripció breu del canvi"
git push -u origin feature/nom-del-canvi
```

No s’hauria de fer push directe a `main`.

---

## Bones pràctiques

- no pujar `.env`
- no pujar secrets, credencials ni claus
- revisar migracions abans de fer commit
- executar tests quan es toqui lògica rellevant
- comprovar que Docker Compose aixeca correctament
- documentar canvis importants de configuració
- mantenir clara la separació entre local i staging
- no exposar PostgreSQL públicament
- fer servir Nginx com a entrada en el flux Docker
- revisar CORS i CSRF quan canviï la URL del frontend
- relacionar Pull Requests amb tasques o User Stories de Taiga

---

## Resum ràpid

Si ets nou al projecte, queda’t amb aquesta idea:

- **Django** és el framework principal del backend
- **Django REST Framework** construeix la API
- **JWT** s’utilitza per autenticar usuaris
- **PostgreSQL** desa les dades
- **Docker Compose** aixeca els serveis
- **Nginx** és la porta d’entrada HTTP
- **Gunicorn** executa Django en un entorn més realista
- **Django Admin** serveix per administració interna
- **DBeaver** ajuda a inspeccionar la base de dades
- **Postman** ajuda a provar endpoints
- els rols funcionals principals són **admin**, **owner** i **tenant**
- la branca d’integració funcional és **Desenvolupament**

---

## Llicència

Aquest projecte s’utilitza en el context acadèmic i de desenvolupament de BuildRank / ScoreLab. Si més endavant es defineix una llicència formal per al repositori, es podrà afegir aquí.
