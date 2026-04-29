# Importació manual del CSV CEE

El fitxer `cee.csv` no s’inclou al repositori perquè és massa gran i prové d’un dataset open data simplificat/normalitzat per a l’entorn de desenvolupament i demo.

Aquest enfocament permet treballar amb dades reals sense dependre d’un endpoint extern, millorant la reproductibilitat, el testing i la robustesa del sistema.

## Copiar el CSV al contenidor

Si el fitxer és a Descàrregues de Windows:

```powershell
docker compose cp "$env:USERPROFILE\Downloads\cee.csv" web:/app/cee.csv
```
## Aplicar migracions
```powershell
docker compose exec web python manage.py migrate
```
## Validar sense escriure dades
```powershell
docker compose exec web python manage.py importar_cee /app/cee.csv --limit 50 --dry-run
```
## Importar una mostra petita
```powershell
docker compose exec web python manage.py importar_cee /app/cee.csv --limit 50
```
## Importar per tandes
```powershell
docker compose exec web python manage.py importar_cee /app/cee.csv --limit 1000
docker compose exec web python manage.py importar_cee /app/cee.csv --limit 1000 --offset 1000
```
## Notes de disseny

Les dades CEE s’utilitzen com a font auxiliar inicial. La prioritat funcional del sistema és:

1. dades introduïdes per l’usuari
2. dades open data CEE
3. estat de dades insuficients