# Testing i comprovacions del backend

Aquest document recull les comandes principals per validar l’estat del backend abans d’obrir o actualitzar una Pull Request.

## 1. Comprovar migracions i estat general de Django

Abans d’executar tests, és recomanable comprovar que no hi ha migracions pendents, aplicar les migracions i validar la configuració general del projecte.

```powershell
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py migrate --noinput
docker compose exec web python manage.py check
````

**Resultat esperat:**

* `makemigrations --check --dry-run` → no ha de detectar canvis pendents
* `migrate --noinput` → ha d’aplicar totes les migracions sense errors
* `check` → no ha de mostrar problemes de configuració

## 2. Instal·lar coverage dins del contenidor

Si `coverage` no està instal·lat dins del contenidor:

```powershell
docker compose exec web python -m pip install coverage
```

## 3. Executar tests amb coverage

```powershell
docker compose exec web coverage run manage.py test apps.accounts apps.buildings -v 2
```

Aquesta comanda executa els tests de:

* `apps.accounts`
* `apps.buildings`

## 4. Generar resum de cobertura en terminal

```powershell
docker compose exec web coverage report
```

## 5. Generar arxiu XML de coverage

```powershell
docker compose exec web coverage xml
```

Aquest arxiu segueix el mateix format que el CI.

## 6. Generar informe HTML (opcional)

```powershell
docker compose exec web coverage html
```

Permet revisar la cobertura de forma visual.
