# BuildRank Backend

Backend de **BuildRank**, una plataforma orientada a promoure un ús més responsable i sostenible de l’energia als edificis mitjançant dades, rànquings, simulacions de millores, verificació documental, comunitat i suport a la presa de decisions.

Aquest repositori conté la part servidor del projecte. El backend exposa l’API REST consumida pel frontend, gestiona autenticació i permisos, persisteix les dades, aplica la lògica de negoci i dona suport als processos de desplegament, qualitat i validació tècnica del sistema.

---

## Què és BuildRank

BuildRank és una plataforma pensada per ajudar propietaris, llogaters, administradors de finca i administradors del sistema a entendre millor l’estat energètic dels edificis i promoure millores sostenibles.

El backend s’encarrega de:

- autenticar usuaris i gestionar tokens
- controlar permisos segons rol i vinculació real amb edificis o habitatges
- gestionar edificis, habitatges, localitzacions i dades energètiques
- importar i normalitzar dades d’open data
- calcular classificacions, indicadors i informació energètica
- donar suport a rànquings, temporades i lligues
- gestionar simulacions de millores energètiques
- validar millores implementades i actualitzar puntuacions
- gestionar votacions internes i funcionalitats comunitàries
- donar suport a xat i canals vinculats a edificis o edificis comparables
- gestionar verificacions documentals amb suport OCR/IA
- servir fitxers media com avatars i documents pujats
- exposar una API preparada per ser consumida pel frontend Flutter/Web

Dit d’una manera simple: el frontend és la capa visible i el backend és la capa que valida, decideix, processa, protegeix i guarda la informació.

---

## Estat actual del projecte

La branca principal d’integració funcional és:

```text
Desenvolupament
```

La branca utilitzada per al desplegament de staging a Virtech és:

```text
feature/staging-virtech
```

La branca `main` es reserva per a una versió final o estable quan `Desenvolupament` hagi estat revisada, netejada i validada.

---

## Tecnologies principals

- **Python 3.12**
- **Django**
- **Django REST Framework**
- **JWT amb SimpleJWT**
- **PostgreSQL**
- **Redis**
- **Celery**
- **Ollama**
- **Nginx**
- **Gunicorn**
- **Docker**
- **Docker Compose**
- **django-cors-headers**
- **drf-spectacular**
- **GitHub Actions**
- **SonarCloud**
- **Coverage.py**
- **DBeaver**
- **Postman**

---

## Arquitectura general

En entorn Docker/staging, el flux principal és:

```text
Frontend Flutter/Web
→ Nginx
→ Gunicorn
→ Django REST Framework
→ PostgreSQL
```

A més, el sistema pot utilitzar serveis auxiliars:

```text
Redis
→ suport a tasques asíncrones i serveis interns

Celery Worker
→ execució de tasques en segon pla

Ollama
→ suport a processos d’extracció o verificació documental assistits per IA
```

En staging, Nginx és el punt d’entrada HTTP. Serveix el frontend web, redirigeix les rutes `/api/` i `/admin/` cap a Django/Gunicorn, serveix fitxers estàtics i també exposa `/media/` per a avatars i documents pujats.

---

## Serveis Docker principals

En el desplegament complet de Virtech, el `docker-compose.virtech.yml` treballa amb aquests serveis:

```text
db              PostgreSQL
redis           Redis
ollama          Ollama
web             Django + Gunicorn
celery_worker   Celery worker
nginx           Nginx
```

En entorn local, el `docker compose` pot variar segons la configuració disponible, però la idea és mantenir un entorn semblant al de staging sempre que sigui possible.

---

## Estructura funcional del backend

Les apps principals del backend inclouen:

```text
apps/accounts         autenticació, perfils, rols i gestió d’usuaris
apps/buildings        edificis, habitatges, dades energètiques, simulacions i millores
apps/seasons          temporades i cicle de competició
apps/leagues          lligues, categories i snapshots de rànquing
apps/participations   participació d’edificis en lligues i temporades
apps/community        votacions internes i funcionalitats comunitàries
apps/chat             integració de xat i canals entre usuaris/edificis
apps/notifications    notificacions internes
apps/verification     verificació documental i suport OCR/IA
apps/audit            auditoria i traçabilitat d’accions
config                configuració principal de Django
```

---

## Rols del sistema

El sistema diferencia tres rols funcionals principals:

```text
admin   administrador de finca
owner   propietari
tenant  llogater
```

A més, Django també pot tenir usuaris `staff` o `superuser` per a administració interna.

Els permisos no depenen només del rol. També depenen del context. Per exemple, un administrador de finca només pot gestionar edificis sobre els quals té assignació efectiva, i un propietari o llogater només pot veure dades dels habitatges o edificis amb els quals està vinculat.

---

## Autenticació

L’autenticació principal es basa en **JWT**.

Quan un usuari inicia sessió correctament, el backend retorna tokens d’accés i refresh. Les peticions autenticades han d’incloure:

```http
Authorization: Bearer <access_token>
```

Endpoints habituals:

```text
POST /api/accounts/register/
POST /api/accounts/login/
POST /api/accounts/refresh/
POST /api/accounts/logout/
GET  /api/accounts/me/
GET  /api/accounts/me/edificis/
```

També hi ha suport per autenticació OAuth amb Google, segons la configuració d’entorn disponible.

---

## Funcionalitats principals

El backend dona suport a:

- registre i login d’usuaris
- gestió de perfils i avatars
- rols funcionals i control d’accés
- panell d’administració de Django
- edificis, habitatges i localitzacions
- autocompletat de carrers
- importació i normalització de dades open data
- dades energètiques d’habitatges i edificis
- classificació energètica estimada o oficial
- Building Health Score i puntuacions energètiques
- mapes i consulta d’edificis amb coordenades
- rànquings, lligues i temporades
- evolució històrica i snapshots de rànquing
- catàleg de millores energètiques
- simulacions preview i simulacions persistides
- votacions sobre simulacions de millora
- acreditació i validació de millores implementades
- insígnies i badges
- votacions comunitàries
- notificacions
- canals de xat vinculats a edificis i edificis comparables
- verificació documental amb extracció assistida
- auditoria d’accions sensibles

---

## Endpoints principals

Les rutes poden evolucionar, però alguns endpoints representatius són:

### Accounts

```text
POST /api/accounts/register/
POST /api/accounts/login/
POST /api/accounts/refresh/
POST /api/accounts/logout/
GET  /api/accounts/me/
PATCH /api/accounts/me/
GET  /api/accounts/me/edificis/
```

### Buildings

```text
GET  /api/buildings/edificis/
POST /api/buildings/edificis/
GET  /api/buildings/edificis/<idEdifici>/
PATCH /api/buildings/edificis/<idEdifici>/
GET  /api/buildings/edificis/mapa/
GET  /api/buildings/edificis/cerca/
GET  /api/buildings/carrers/autocomplete/
```

### Habitatges i dades energètiques

```text
GET   /api/buildings/edificis/<idEdifici>/habitatges/
GET   /api/buildings/edificis/<idEdifici>/dades_energetiques/
PATCH /api/buildings/edificis/<idEdifici>/me/habitatge/<referenciaCadastral>/
```

### Simulacions i millores

```text
GET  /api/buildings/millores/
POST /api/buildings/edificis/<idEdifici>/simulacions/preview/
GET  /api/buildings/edificis/<idEdifici>/simulacions/
POST /api/buildings/edificis/<idEdifici>/simulacions/
POST /api/buildings/edificis/<idEdifici>/simulacions/<simulacio_id>/sotmetre-votacio/
POST /api/buildings/edificis/<idEdifici>/votacions-simulacions/<votacio_id>/votar/
POST /api/buildings/edificis/<idEdifici>/simulacions/<simulacio_id>/acreditar-implementacio/
GET  /api/buildings/edificis/<idEdifici>/millores-implementades/
POST /api/buildings/millores-implementades/<id>/validar/
```

### Seasons, leagues i participations

```text
GET  /api/seasons/
POST /api/seasons/
GET  /api/leagues/
GET  /api/participations/
```

### Community, chat i notifications

```text
GET  /api/community/...
POST /api/community/...
GET  /api/chat/...
POST /api/chat/...
GET  /api/notifications/
```

### Verification

```text
GET  /api/verification/
POST /api/verification/
GET  /api/verification/<id>/
POST /api/verification/<id>/review/
```

---

## Requisits previs

Abans de començar, és recomanable tenir instal·lat:

- Git
- Docker Desktop o Docker Engine
- Docker Compose
- Python 3.12, si es vol executar fora de Docker
- DBeaver, opcional
- Postman, opcional

En el flux recomanat, PostgreSQL, Redis, Django i la resta de serveis s’aixequen amb Docker.

---

## Clonar el repositori

```bash
git clone https://github.com/ScoreLab-Team/Backend-BuildRank.git
cd Backend-BuildRank
```

Situar-se a la branca d’integració:

```bash
git switch Desenvolupament
git pull --ff-only origin Desenvolupament
```

---

## Configuració d’entorn

El backend necessita variables d’entorn per funcionar. Els fitxers `.env` amb secrets reals no s’han de pujar al repositori.

Exemple orientatiu per entorn local:

```env
ENVIRONMENT=local
DEBUG=True
SECRET_KEY=change-me-local-only

DB_NAME=buildrank
DB_USER=buildrank_user
DB_PASSWORD=buildrank_pass
DB_HOST=db
DB_PORT=5432

ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0,10.0.2.2,nattech.fib.upc.edu

CORS_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1,http://10.0.2.2,http://nattech.fib.upc.edu:40400
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1,http://10.0.2.2,http://nattech.fib.upc.edu:40400

MEDIA_URL=/media/
MEDIA_ROOT=/app/media

ENABLE_DEBUG_TOOLBAR=False
```

En Docker, normalment:

```env
DB_HOST=db
```

Si Django s’executa directament al sistema i PostgreSQL està en Docker exposat al host:

```env
DB_HOST=127.0.0.1
```

---

## Arrencar el backend amb Docker Compose

Des de l’arrel del repositori:

```bash
docker compose up -d --build
```

Comprovar serveis:

```bash
docker compose ps
```

Veure logs:

```bash
docker compose logs -f web
docker compose logs -f db
docker compose logs -f nginx
```

Executar migracions:

```bash
docker compose exec web python manage.py migrate
```

Recollir estàtics:

```bash
docker compose exec web python manage.py collectstatic --noinput
```

Crear superusuari:

```bash
docker compose exec web python manage.py createsuperuser
```

Comprovar configuració:

```bash
docker compose exec web python manage.py check
```

Aturar serveis mantenint dades:

```bash
docker compose down
```

Aturar serveis i eliminar volums locals:

```bash
docker compose down -v
```

Utilitza `down -v` només si realment vols eliminar les dades locals.

---

## Execució local alternativa sense Docker complet

També es pot executar Django directament amb entorn virtual. Aquest mode és útil per depurar, però no representa el flux complet de staging amb Nginx i Gunicorn.

Entrar a la carpeta del backend:

```bash
cd backend
```

Crear entorn virtual:

```bash
python -m venv .venv
```

Activar-lo a Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Activar-lo a Linux/macOS:

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

Arrencar servidor de desenvolupament:

```bash
python manage.py runserver
```

Disponible per defecte a:

```text
http://127.0.0.1:8000/
```

Si el frontend Flutter Android s’executa en emulador i vol parlar amb el backend local:

```bash
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

---

## Fitxers media i avatars

El backend pot gestionar fitxers pujats pels usuaris, com avatars o documents de verificació.

En staging, aquests fitxers es serveixen amb:

```text
MEDIA_URL=/media/
MEDIA_ROOT=/app/media
```

Nginx ha de tenir una regla equivalent a:

```nginx
location /media/ {
    alias /app/media/;
}
```

Això permet que el frontend pugui carregar URLs de media, per exemple avatars retornats per l’API.

Els fitxers pujats en execució no s’han de versionar al repositori. Per això `.gitignore` exclou directoris com:

```text
backend/documents_millores/
backend/verifications/
```

---

## Tests

Executar tota la suite de tests dins Docker:

```bash
docker compose exec web python manage.py test -v 2
```

Executar apps concretes:

```bash
docker compose exec web python manage.py test apps.accounts apps.buildings -v 2
```

Sense Docker, des de `backend/`:

```bash
python manage.py test -v 2
```

El projecte inclou tests de:

- autenticació i JWT
- permisos RBAC/ABAC
- gestió de perfils i avatars
- edificis i habitatges
- dades energètiques
- importació i normalització open data
- simulacions de millores
- millores implementades
- badges
- rànquings, lligues i temporades
- votacions comunitàries
- xat i moderació
- notificacions
- verificació documental
- auditoria

---

## Coverage i SonarCloud

El projecte utilitza **coverage.py** i **SonarCloud** per controlar qualitat.

El workflow de SonarCloud:

- aixeca l’entorn backend amb Docker Compose
- executa la suite de tests completa
- genera `coverage.xml`
- ajusta el mapping del coverage generat dins Docker
- executa l’anàlisi de SonarCloud
- valida el Quality Gate

Comandes equivalents dins Docker:

```bash
docker compose exec web coverage run --source=apps,config manage.py test -v 2
docker compose exec web coverage report
docker compose exec web coverage xml -o coverage.xml
```

Si apareix:

```text
coverage: executable file not found in $PATH
```

vol dir que `coverage` no està instal·lat dins del contenidor.

Si SonarCloud mostra warnings relacionats amb paths com `/app`, cal revisar el mapping del `coverage.xml` generat dins Docker.

---

## Migracions

Les migracions representen la història real de la base de dades i s’han de tractar amb cura.

Comandes útils:

```bash
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate
docker compose exec web python manage.py showmigrations
```

Bones pràctiques:

- revisar migracions abans de fer commit
- no eliminar migracions ja compartides sense acord de l’equip
- comprovar que s’apliquen en una base neta
- incloure migracions a la PR si s’han modificat models
- validar que el frontend continua rebent els camps esperats

---

## CORS i CSRF

Com que el frontend pot executar-se des d’un navegador, un emulador Android, un mòbil físic o staging, cal configurar bé:

```env
ALLOWED_HOSTS=...
CORS_ALLOWED_ORIGINS=...
CSRF_TRUSTED_ORIGINS=...
```

Casos habituals:

```text
http://localhost
http://127.0.0.1
http://10.0.2.2
http://nattech.fib.upc.edu:40400
```

Amb Docker + Nginx, el frontend normalment ha de parlar amb Nginx, no directament amb `:8000`.

---

## Staging a Virtech

Virtech és l’entorn de staging del projecte.

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

La branca de deploy validada per staging és:

```text
feature/staging-virtech
```

Accés SSH:

```bash
ssh alumne@nattech.fib.upc.edu -p 22040
```

Ruta habitual del repositori a la VM:

```bash
cd /opt/buildrank/app/Backend-BuildRank
```

Actualitzar staging:

```bash
git fetch origin
git switch feature/staging-virtech
git reset --hard origin/feature/staging-virtech
```

Validar compose:

```bash
docker-compose -f docker-compose.virtech.yml config > /tmp/buildrank-compose-config.txt && echo "Compose OK"
```

Aixecar staging:

```bash
docker-compose -f docker-compose.virtech.yml up -d --build
```

Veure serveis:

```bash
docker-compose -f docker-compose.virtech.yml ps
```

Executar migracions:

```bash
docker-compose -f docker-compose.virtech.yml exec web python manage.py migrate --noinput
```

Comprovar Django:

```bash
docker-compose -f docker-compose.virtech.yml exec web python manage.py check
```

Veure logs:

```bash
docker-compose -f docker-compose.virtech.yml logs -f web
docker-compose -f docker-compose.virtech.yml logs -f nginx
docker-compose -f docker-compose.virtech.yml logs -f db
```

Validar resposta interna:

```bash
curl -I http://localhost:8080/
curl -I http://localhost:8080/admin/
```

Validar resposta pública:

```text
http://nattech.fib.upc.edu:40400
```

---

## Branques i flux de treball

Flux recomanat:

```text
feature/* o chore/* o docs/*
→ Pull Request
→ Desenvolupament
→ staging/release si cal
→ main quan es tanqui una versió estable
```

Exemple:

```bash
git switch Desenvolupament
git pull --ff-only origin Desenvolupament
git switch -c feature/nom-del-canvi
git add .
git commit -m "feat: descripció breu del canvi"
git push -u origin feature/nom-del-canvi
```

No s’hauria de fer push directe a `main`.

---

## Preparació de release cap a main

Abans de portar `Desenvolupament` cap a `main`, revisar:

- CI verd
- SonarCloud Quality Gate passat
- tests principals executats
- README actualitzat
- `.gitignore` revisat
- cap fitxer generat o local versionat
- secrets fora del repositori
- migracions aplicables des d’una base neta
- frontend i backend alineats
- staging validat si hi ha canvis de deploy

---

## Problemes habituals

### Docker Desktop no està arrencat

En Windows pot aparèixer:

```text
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified
```

Solució: obrir Docker Desktop i esperar que el motor estigui actiu.

### El backend no respon

```bash
docker compose ps
docker compose logs -f web
docker compose logs -f nginx
```

### El Django Admin apareix sense CSS

```bash
docker compose exec web python manage.py collectstatic --noinput
docker compose restart nginx
```

### Les migracions fallen

```bash
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py migrate
```

### El frontend no connecta

Revisar:

- URL base del frontend
- port utilitzat
- Nginx actiu
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`

### Els avatars no carreguen

Comprovar:

- `MEDIA_URL=/media/`
- `MEDIA_ROOT=/app/media`
- volum de media muntat al servei `web`
- volum de media muntat a `nginx`
- regla `location /media/` a Nginx
- que la URL retornada per l’API sigui accessible des del navegador

### Nginx falla amb `unknown directive "upstream"`

Pot passar si `nginx.virtech.conf` té un BOM invisible al principi del fitxer. Cal desar-lo en UTF-8 sense BOM.

### SonarCloud falla per coverage

Revisar:

- que s’executen tots els tests
- que `coverage.xml` existeix
- que el mapping del path dins Docker és correcte
- que el workflow té permisos per modificar el fitxer copiat des del contenidor

---

## Bones pràctiques

- no pujar `.env`
- no pujar secrets ni tokens
- no versionar fitxers generats
- no versionar media/uploads
- no versionar `coverage.xml`, `htmlcov`, `.scannerwork` ni `__pycache__`
- revisar migracions abans de fer commit
- executar tests quan es toqui lògica rellevant
- revisar permisos quan es toquin rols o accessos
- validar CORS/CSRF quan canviï la URL del frontend
- no exposar PostgreSQL públicament
- fer servir Nginx com a entrada del sistema en Docker/staging
- mantenir separades les branques de feature, staging, desenvolupament i main
- relacionar Pull Requests amb tasques o User Stories quan sigui possible

---

## Resum ràpid

Si ets nou al projecte:

- **Django** implementa el backend
- **Django REST Framework** exposa l’API
- **JWT** autentica els usuaris
- **PostgreSQL** desa les dades
- **Redis** i **Celery** donen suport a tasques internes
- **Ollama** dona suport a verificació documental assistida
- **Nginx** és la porta d’entrada HTTP
- **Gunicorn** executa Django en entorn Docker/staging
- **Docker Compose** aixeca l’entorn
- **SonarCloud** valida qualitat i cobertura
- **Virtech** és l’entorn de staging
- **Desenvolupament** és la branca d’integració
- **feature/staging-virtech** és la branca de deploy a Virtech

---

## Llicència

Aquest projecte s’utilitza en el context acadèmic i de desenvolupament de BuildRank / ScoreLab. Si més endavant es defineix una llicència formal per al repositori, es podrà afegir aquí.
