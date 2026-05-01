# Test Execution Report – Accounts Backend

## Executor
Martí Borràs

## Branca
testing-us1-us7

## Àmbit
US1, US2, US3, US4, US5, US6 i US7.

## Comandes executades

```bash
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test apps.accounts
docker compose exec web coverage run manage.py test apps.accounts
docker compose exec web coverage report --include="apps/accounts/*"
```

## Resultats

- **manage.py check:** OK  
- **makemigrations --check --dry-run:** No changes detected  
- **Tests executats (apps.accounts):** 52  
- **Tests correctes:** 52  
- **Tests skipped:** 2  
- **Coverage (apps.accounts):** 88%

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

### DBeaver
S’ha verificat la persistència de:

- Usuaris  
- Perfils  
- Rols  
- Logs d’autenticació  

Confirmant coherència entre API i base de dades PostgreSQL.

## Incidències

No s’han detectat incidències crítiques durant l’execució de les proves.

## Conclusions

La funcionalitat corresponent a les US1–US7 (registre, autenticació, gestió de rols i perfil) es considera estable.

El sistema:
- Passa tots els tests automatitzats  
- No presenta errors de configuració  
- No té migracions pendents  
- Manté una cobertura del 88% en l’app accounts  
- Valida correctament els fluxos d’autenticació i permisos  

Per tant, es considera que aquestes funcionalitats compleixen els criteris de qualitat definits i poden integrar-se al sistema sense risc de regressió.