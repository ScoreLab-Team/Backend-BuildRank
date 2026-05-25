# Test execution report Sprint 3

## Informació general

Data: 25/05/2026
Branca: Desenvolupament
Entorn: Backend local amb Docker Compose
Objectiu: Regressió backend principal abans d'integrar nous canvis de frontend.

## Resultats

| ID | Comanda | Resultat | Observacions |
|---|---|---|---|
| BE-001 | docker compose up -d --build | OK | Contenidors aixecats correctament. |
| BE-002 | docker compose exec web python manage.py check | OK | Sense issues. |
| BE-003 | docker compose exec web python manage.py makemigrations --check --dry-run | OK | Sense migracions pendents. |
| BE-004 | docker compose exec web python manage.py test apps.accounts -v 2 | OK | 102 tests OK. |
| BE-005 | docker compose exec web python manage.py test apps.buildings -v 2 | OK | 251 tests OK. |
| BE-006 | docker compose exec web python manage.py test apps.verification -v 2 | OK | 85 tests OK. |
| BE-007 | docker compose exec web python manage.py test apps.leagues apps.participations apps.seasons -v 2 | OK | 98 tests OK. |
| BE-008 | docker compose exec web python manage.py test apps.community -v 2 | OK | 30 tests OK. |
| BE-009 | docker compose exec web python manage.py test apps.chat -v 2 | OK | 154 tests OK. Hi ha logs no bloquejants de GetStream. |
| BE-010 | docker compose exec web python manage.py test -v 2 | OK | 751 tests OK. |
| BE-011 | docker compose exec web coverage report -m | OK | Cobertura global backend: 91% sobre 13.483 statements. |

## Incidències / observacions

| ID | Severitat | Àrea | Descripció | Estat |
|---|---|---|---|---|
| BUG-001 | Low | Chat / Test config | Durant alguns tests de chat apareixen logs de GetStream amb `api_key not valid`, però els tests finalitzen correctament en OK. S'ha de considerar mockejar o desactivar la sincronització externa durant tests. | Open |

## Conclusió

La regressió backend principal queda superada. No s'han detectat errors Blocker ni High. El backend es considera estable per continuar amb coverage, revisió de qualitat, performance/k6 i posterior integració frontend.


## Nota sobre staging

La regressió i coverage documentats en aquest informe corresponen a l'entorn local Docker Compose sobre Desenvolupament. La validació específica de Virtech queda pendent perquè la branca feature/staging-virtech no estava actualitzada amb els últims canvis de Desenvolupament.
