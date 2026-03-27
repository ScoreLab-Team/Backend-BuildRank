# BuildRank Backend

Backend de **BuildRank**, una plataforma orientada a promoure un ús més responsable i sostenible de l’energia als edificis.

Aquest repositori conté la part servidor del projecte. El backend s’encarrega de gestionar la lògica de negoci, l’autenticació, els permisos, la persistència de dades i l’exposició de l’API que consumeix el frontend.

---

## Què és aquest projecte

BuildRank és un sistema pensat per ajudar a gestionar i entendre millor l’estat energètic dels edificis, facilitar-ne el seguiment i donar suport a funcionalitats com la consulta d’informació, la comparació, les millores i altres serveis associats a la plataforma.

En termes pràctics, el backend és la capa que:

- exposa una API REST perquè el frontend pugui operar
- valida les dades que arriben al sistema
- autentica usuaris i controla permisos
- consulta, crea i actualitza informació persistent
- aplica la lògica interna del projecte

Dit d’una manera simple: si el frontend és la part visual que veu l’usuari, el backend és la part que decideix, comprova, processa i guarda la informació.

---

## Tecnologies principals

- **Python**
- **Django**
- **Django REST Framework**
- **JWT (SimpleJWT)**
- **PostgreSQL**
- **Docker**
- **django-cors-headers**

---

## Funcionalitats generals del backend

Aquest backend està pensat per donar suport, entre d’altres, a necessitats com:

- registre i autenticació d’usuaris
- control d’accés segons rol i context
- consulta d’informació pròpia de l’usuari autenticat
- gestió de dades relacionades amb edificis, habitatges i informació associada
- validació i persistència de dades del sistema
- base per a futures funcionalitats de càlcul, comparació, informes i evolució del producte

---

## Rols del sistema

A nivell funcional, el sistema treballa amb aquests rols principals:

- **admin**: administrador de finca
- **owner**: propietari
- **tenant**: llogater

Els permisos no depenen només del nom del rol, sinó també del context de cada acció. Això vol dir que dues persones amb el mateix rol no necessàriament tindran accés als mateixos recursos si no estan vinculades al mateix edifici o àmbit de gestió.

### Administració interna de Django

A banda dels rols funcionals de l’aplicació, el projecte també permet crear un **administrador del sistema** mitjançant Django amb la comanda:

```bash
python manage.py createsuperuser
```

Aquest usuari és el superusuari d’administració interna de Django i serveix per accedir al panell d’administració i a capacitats avançades de gestió del sistema.

---

## Autenticació

L’autenticació es basa en **JWT**.

Quan un usuari inicia sessió correctament, el backend retorna els tokens necessaris perquè el frontend pugui continuar fent peticions autenticades.

En les rutes protegides, el frontend ha d’enviar el token d’accés a la capçalera de la petició:

```http
Authorization: Bearer <token_access>
```

---

## API

Aquest backend exposa una API REST per ser consumida des del frontend i, si cal, des d’altres serveis del projecte.

### Exemples d’operacions habituals

- registre d’usuari
- inici de sessió
- refresc de token
- tancament de sessió
- consulta de l’usuari autenticat
- consulta i gestió de recursos del domini

> Nota: les rutes i els endpoints poden evolucionar amb el projecte. Aquest README descriu el funcionament general del repositori i la manera de començar a treballar-hi.

---

## Requisits previs

Abans de començar, convé tenir instal·lat:

- **Python 3**
- **pip**
- **Docker Desktop**
- opcionalment, **DBeaver** si vols inspeccionar la base de dades de manera gràfica

> En el flux local del projecte, **PostgreSQL no s’instal·la nativament al sistema**. La manera recomanada de treballar és aixecar la base de dades dins d’un contenidor Docker.

---

## Onboarding ràpid per a una persona nova

La seqüència recomanada és aquesta:

1. clonar el repositori
2. crear i activar un entorn virtual
3. instal·lar dependències
4. aixecar PostgreSQL amb Docker
5. configurar el fitxer `.env`
6. aplicar migracions
7. crear superusuari si cal
8. arrencar el backend amb `runserver`

---

## Posada en marxa en local

### 1. Clonar el repositori

```bash
git clone <URL_DEL_REPOSITORI>
cd <NOM_DEL_REPOSITORI>
```

### 2. Entrar a la carpeta correcta del backend

Situa’t a la carpeta on viu el fitxer `manage.py`.

Per exemple, si el projecte encapsula Django dins d’una carpeta específica:

```bash
cd backend
```

### 3. Crear un entorn virtual

```bash
python -m venv .venv
```

### 4. Activar-lo

#### Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

#### Linux / macOS

```bash
source .venv/bin/activate
```

### 5. Instal·lar dependències

```bash
pip install -r requirements.txt
```

---

## Base de dades local amb Docker

En aquest projecte, la forma recomanada d’aixecar PostgreSQL en local és amb Docker. Això ajuda a reduir diferències entre ordinadors, facilita reinicis nets i fa que l’entorn sigui més reproduïble per a tot l’equip.

### 5.1. Comprovar Docker

Amb Docker Desktop obert, comprova que Docker està disponible:

```bash
docker --version
docker compose version
```

### 5.2. Crear una carpeta per a la base local

Pots fer-ho dins del projecte o en una carpeta separada. Per exemple:

```bash
mkdir buildrank-local-db
cd buildrank-local-db
```

### 5.3. Crear el fitxer `compose.yaml`

Dins d’aquesta carpeta, crea un fitxer anomenat `compose.yaml` amb aquest contingut:

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

Aquesta configuració:

- descarrega i executa `postgres:16`
- crea una base de dades anomenada `buildrank`
- crea l’usuari `buildrank_user`
- exposa PostgreSQL al port `5432`
- manté un volum persistent perquè les dades no es perdin si s’atura el contenidor

### 5.4. Aixecar PostgreSQL

Des de la carpeta on tens el `compose.yaml`:

```bash
docker compose up -d
```

### 5.5. Verificar que està funcionant

```bash
docker ps
docker logs buildrank-postgres
```

Si tot ha anat bé, ja tens PostgreSQL executant-se en local dins Docker.

### 5.6. Reiniciar o resetear la base

Aturar mantenint les dades:

```bash
docker compose down
```

Tornar-la a aixecar:

```bash
docker compose up -d
```

Reinici net esborrant també el volum i, per tant, les dades locals:

```bash
docker compose down -v
docker compose up -d
```

> Fes servir `down -v` només si realment vols començar de zero.

### 5.7. Problema típic de ports

Si el port `5432` ja està ocupat al teu ordinador, pots canviar el mapeig a:

```yaml
ports:
  - "5433:5432"
```

En aquest cas, recorda que després també hauràs d’usar `DB_PORT=5433` al fitxer `.env`.

---

## Configuració del fitxer `.env`

Crea un fitxer `.env` amb una configuració semblant a aquesta:

```env
DB_NAME=buildrank
DB_USER=buildrank_user
DB_PASSWORD=buildrank_pass
DB_HOST=127.0.0.1
DB_PORT=5432
DEBUG=True
ENABLE_DEBUG_TOOLBAR=False
```

Si has canviat el port del `compose.yaml` a `5433`, aquí també hauràs d’indicar `DB_PORT=5433`.

---

## Preparar Django

### Aplicar migracions

```bash
python manage.py migrate
```

### Crear un superusuari

```bash
python manage.py createsuperuser
```

### Arrencar el servidor de desenvolupament

```bash
python manage.py runserver
```

Per defecte, el backend quedarà disponible a:

```text
http://127.0.0.1:8000/
```

---

## Comandes útils

### Comprovar la configuració del projecte

```bash
python manage.py check
```

### Generar migracions noves

```bash
python manage.py makemigrations
```

### Aplicar migracions

```bash
python manage.py migrate
```

### Executar tests

```bash
python manage.py test
```

### Obrir la shell de Django

```bash
python manage.py shell
```

### Crear un superusuari

```bash
python manage.py createsuperuser
```

### Comandes útils de Docker

```bash
docker --version
docker compose version
docker compose up -d
docker ps
docker logs buildrank-postgres
docker compose down
docker compose down -v
```

---

## DBeaver (opcional)

Si vols mirar la base de dades amb una eina gràfica, pots connectar-te amb DBeaver amb aquests valors:

- **Host**: `localhost`
- **Port**: `5432`  
  (o `5433` si has canviat el mapeig)
- **Database**: `buildrank`
- **Username**: `buildrank_user`
- **Password**: `buildrank_pass`

---

## Tests i qualitat

El projecte incorpora proves per validar parts importants del backend, especialment aquelles relacionades amb:

- autenticació
- permisos
- accés segons rol o context
- operacions sensibles sobre recursos del sistema

A més, el repositori està pensat per encaixar amb un flux de treball basat en **branches**, **Pull Requests** i comprovacions automàtiques abans d’integrar canvis.

---

## Flux de treball recomanat

Una forma habitual de treballar sobre aquest repositori és:

1. crear una branca de treball
2. fer els canvis necessaris
3. provar el codi en local
4. executar les validacions necessàries
5. pujar la branca al repositori remot
6. obrir una Pull Request

---

## Bones pràctiques

- no pugis el fitxer `.env` al repositori
- no pugis secrets, credencials ni claus
- revisa migracions abans de compartir canvis
- executa tests quan toquis lògica rellevant
- documenta els canvis importants si afecten el comportament del sistema
- intenta mantenir una separació clara entre autenticació, permisos i lògica del domini

---

## Resum ràpid

Si ets nou al projecte, queda’t amb aquesta idea:

- **Django** és el framework principal del backend
- **Django REST Framework** construeix l’API
- **JWT** s’utilitza per autenticar usuaris
- **PostgreSQL** desa les dades
- **Docker** és la forma recomanada d’aixecar PostgreSQL en local
- **`createsuperuser`** serveix per crear l’administrador del sistema
- els rols funcionals principals de l’aplicació són **admin**, **owner** i **tenant**

---

## Llicència

Aquest projecte s’utilitza en el context acadèmic i de desenvolupament de BuildRank / ScoreLab. Si més endavant es defineix una llicència formal per al repositori, es podrà afegir aquí.