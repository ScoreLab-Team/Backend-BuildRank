# Accounts Data Quality - Sprint 3

## Scope

Aquest document recull criteris i conclusions de qualitat de dades per l'Epic 1 backend (`accounts`): usuaris, autenticacio, rols, perfil, password reset, permisos, estat de compte i tokens.

Branca revisada: `qa/backend-dia3-sonar-performance-data`.

## Validacions executades

| Comando | Resultat |
| --- | --- |
| `docker compose exec web python manage.py check` | OK |
| `docker compose exec web python manage.py makemigrations --check --dry-run` | OK, `No changes detected` |
| `docker compose exec web python manage.py test apps.accounts -v 2` | OK, 102 tests executats |
| `docker compose exec web coverage run manage.py test apps.accounts` | OK |
| `docker compose exec web coverage report` | Coverage global reportada: 61% |

## Criteris de qualitat revisats

- Integritat de model: `User` i `Profile` mantenen una relacio 1:1 i els tests treballen amb perfil associat.
- Rols: els rols permesos es validen amb choices i els tests cobreixen assignacio, restriccions i permisos.
- Passwords: registre i reset validen coincidencia, complexitat i token valid/invalid.
- Tokens: logout, password reset i canvis d'estat de compte contemplen revocacio de refresh tokens.
- Estat de compte: bloqueig, suspensio, desbloqueig i reactivacio es validen amb canvis persistits al perfil.
- Privadesa en password reset: la sol.licitud no retorna `uid` ni `token` a l'API i evita enumeracio d'usuaris.
- Concurrencia: proves especifiques cobreixen duplicats de registre, limit de sessions i actualitzacio d'email.
- Migracions: `makemigrations --check --dry-run` confirma que no hi ha divergencia entre models i migracions.

## Conclusions

La qualitat de dades per `accounts` queda validada a nivell de QA automatitzada de Sprint 3. Els resultats disponibles indiquen que no hi ha migracions pendents, que les validacions principals d'identitat i rols funcionen, i que els fluxos sensibles de token/password reset tenen proves de regressio.

Les conclusions son prudents: no s'ha fet una auditoria manual de base de dades productiva ni una reconciliacio de dades reals. Per tant, aquest document avalua el comportament del codi i de les proves automatitzades, no l'estat d'un dataset de produccio.

## Decisions de QA

- Acceptar la qualitat de dades de l'Epic 1 per Sprint 3 amb els tests actuals en verd.
- Considerar obligatori repetir `makemigrations --check --dry-run` si es modifiquen models, serializers o camps de perfil.
- Considerar obligatoris tests especifics per qualsevol canvi en rols, estats de compte, revocacio de tokens o password reset.
- No introduir canvis funcionals en aquesta tasca; aquest document nomes registra l'estat de QA.

## Pendents i recomanacions

- Pending: smoke manual contra un entorn amb dades representatives per verificar coherencia visual/API de perfil, rol i estat de compte.
- Pending: revisar dades reals o fixtures representatives si es vol certificar absencia de duplicats historics, perfils orfes o rols antics.
- Recomanat: mantenir fixtures o factories estables per usuaris amb rols `owner`, `tenant`, `admin` i superuser.
