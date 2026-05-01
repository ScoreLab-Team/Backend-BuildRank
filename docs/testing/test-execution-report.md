# Test Execution Report – Accounts Backend i Buildings Backend

## Executor
Martí Borràs  
Mireia Brufau  

## Branca
testing-us1-us7  
feature/testing  

## Àmbit
- **Mòdul Accounts:** US1, US2, US3, US4, US5, US6 i US7  
- **Mòdul Buildings (gestió i permisos):** US10, US11, US12, US14, US19, US20  
- **Mòdul Simulacions:** US29 i US30  

## Comandes executades
```bash
# Validacions de sistema i base de dades
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run

# Tests i Coverage - Mòdul Accounts
docker compose exec web python manage.py test apps.accounts
docker compose exec web coverage run manage.py test apps.accounts
docker compose exec web coverage report --include="apps/accounts/*"

# Tests i Coverage - Mòdul Buildings
docker compose exec web python manage.py test apps.buildings
docker compose exec web coverage run manage.py test apps.buildings
docker compose exec web coverage report --include="apps/buildings/*"
```

## Resultats
- **manage.py check:** OK  
- **makemigrations --check --dry-run:** No changes detected  

### Mòdul Accounts
- **Tests executats (apps.accounts):** 55  
- **Tests correctes:** 55  
- **Tests skipped:** 2  
- **Coverage (apps.accounts):** 89%

### Mòdul Buildings (simulacions)
- **Tests executats (apps.buildings):** 106  
- **Tests correctes:** 106  
- **Tests skipped:** 0
- **Coverage (apps.buildings):** 84%
- **Coverage específic (engine.py):** 99%


## Validacions realitzades
### Django
- Validació de configuració correcta del projecte  
- No s’han detectat errors de sistema  

### Docker
- Entorn aixecat correctament amb docker compose  
- Execució de comandes dins del contenidor sense errors  

### Postman
S’han validat manualment els endpoints:

- `POST /register/`
- `POST /login/`
- `POST /logout/`
- `GET /me/`
- `PATCH /me/`
- `PATCH /me/role/`

Verificant:
- Codis HTTP correctes  
- Format de resposta JSON  
- Gestió d’errors  

Execució d'una simulació amb millores d'aïllament i fotovoltaica des de l'emulador. 
S'ha verificat la recepció correcta del POST i el càlcul de resultats en temps real.

### DBeaver
S’ha verificat la persistència de:

- Usuaris  
- Perfils  
- Rols  
- Logs d’autenticació  

Confirmant coherència entre API i base de dades PostgreSQL.

S'ha confirmat que les simulacions es guarden correctament amb tots els seus ítems i valors calculats a la taula buildings_simulaciomillora.

## Incidències
No s’han detectat incidències crítiques durant l’execució de les proves.

## Conclusions
La funcionalitat corresponent a les US1–US7 (registre, autenticació, gestió de rols i perfil) i les US29-US30 (Simulacions Energètiques) es considera estable.

El sistema backend:
- Passa tots els tests automatitzats  
- No presenta errors de configuració  
- No té migracions pendents  
- Manté una cobertura del 89% en l’app accounts i 99% en el motor de simulació 
- Valida correctament els fluxos d’autenticació i permisos  

Per tant, es considera que aquestes funcionalitats compleixen els criteris de qualitat definits i poden integrar-se al sistema sense risc de regressió.