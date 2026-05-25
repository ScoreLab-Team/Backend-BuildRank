# Accounts QA Summary - Sprint 3

## Scope

Aquest resum cobreix la QA backend de l'Epic 1 per al modul `accounts`: autenticacio, usuaris, rols, perfil, password reset, permisos RBAC/ABAC, estats de compte i sessions/token JWT.

Branca revisada: `qa/backend-dia3-sonar-performance-data`.

## Execucio de proves

Comandos executats abans de generar aquest document:

| Comando | Resultat |
| --- | --- |
| `docker compose exec web python manage.py check` | OK |
| `docker compose exec web python manage.py makemigrations --check --dry-run` | OK, `No changes detected` |
| `docker compose exec web python manage.py test apps.accounts -v 2` | OK, 102 tests executats |
| `docker compose exec web coverage run manage.py test apps.accounts` | OK |
| `docker compose exec web coverage report` | Coverage global reportada: 61% |

## Cobertura funcional observada

Els tests d'`apps.accounts` cobreixen els fluxos principals de l'Epic 1:

- Registre d'usuaris i validacions de contrasenya.
- Login amb JWT, logout i revocacio de tokens refresh.
- Limitacio de sessions actives i proves de concurrencia per login/registre/actualitzacio d'email.
- Endpoints `me`, perfil, avatar i canvi de dades basiques de compte.
- Assignacio i actualitzacio de rols permesos.
- Permisos RBAC i ABAC per perfils d'usuari, incloent casos 401/403.
- Gestio d'estat de compte per admin de sistema: bloqueig, desbloqueig, suspensio i reactivacio.
- Password reset: sol.licitud sense enumeracio d'usuaris, confirmacio amb token valid/invalid, mismatch de password i revocacio de sessions actives.
- Google OAuth amb mocks de verificacio de token, alta/login i validacio de rol.
- Casos especifics de verificacio pendent d'admin de finca.

## Conclusions de QA

El paquet `apps.accounts` queda en estat verd per a les proves automatitzades executades en aquesta branca. No hi ha canvis pendents de migracions i el `manage.py check` no reporta errors de configuracio del projecte.

La cobertura global del projecte es mante al 61%. Aquesta xifra no implica cobertura completa de l'Epic 1, pero combinada amb els 102 tests d'`accounts` dona una base raonable per validar els fluxos critics d'autenticacio, permisos i gestio d'usuaris.

## Decisions

- Acceptar la QA automatitzada d'`apps.accounts` per Sprint 3 amb els resultats disponibles.
- No bloquejar per performance per falta de metriques quantitatives executades en aquesta ronda; queda documentat al resum de performance.
- Mantenir com a criteri de regressio que `manage.py check`, `makemigrations --check --dry-run` i `test apps.accounts` continuin en verd abans de merge.
- Tractar qualsevol canvi futur en autenticacio, rols, password reset o revocacio de tokens com a area de risc alt i requerir proves especifiques.

## Riscos i pendents

- Coverage global del 61%: suficient com a senyal general, pero millorable si es vol elevar el llindar de qualitat del backend complet.
- No s'ha documentat cap prova E2E manual completa contra frontend en aquesta execucio.
- No s'han executat proves de carrega o benchmark real per endpoints d'accounts en aquesta ronda.
