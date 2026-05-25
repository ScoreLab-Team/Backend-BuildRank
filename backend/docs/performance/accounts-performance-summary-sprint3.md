# Accounts Performance Summary - Sprint 3

## Scope

Aquest document resumeix l'estat de performance backend per l'Epic 1 (`accounts`): autenticacio, usuaris, rols, perfil, password reset, permisos i gestio de sessions.

Branca revisada: `qa/backend-dia3-sonar-performance-data`.

## Resultats disponibles

No s'ha executat cap benchmark quantitatiu ni prova de carrega formal per `apps.accounts` en aquesta ronda. Per tant, aquest document no fixa latencies, throughput, percentils, consum de CPU/memoria ni temps de resposta exactes.

Validacions relacionades executades:

| Comando | Resultat |
| --- | --- |
| `docker compose exec web python manage.py check` | OK |
| `docker compose exec web python manage.py makemigrations --check --dry-run` | OK, `No changes detected` |
| `docker compose exec web python manage.py test apps.accounts -v 2` | OK, 102 tests executats |
| `docker compose exec web coverage run manage.py test apps.accounts` | OK |
| `docker compose exec web coverage report` | Coverage global reportada: 61% |

## Senyals de performance coberts indirectament

Les proves automatitzades inclouen escenaris que redueixen risc funcional en punts sensibles de performance i concurrencia:

- Registre concurrent amb mateix email sense retorns 500.
- Logins simultanis amb limit de sessions actives.
- Actualitzacio concurrent d'email sense retorns 500.
- Revocacio de tokens refresh en logout, password reset, bloqueig i suspensio d'usuari.
- Consultes d'usuaris amb `select_related("profile")` en endpoints administratius, segons implementacio actual.

Aquests resultats no substitueixen una prova de carrega. Només indiquen que els fluxos de concurrencia coberts pels tests no han fallat funcionalment.

## Conclusions prudents

L'estat actual es pot considerar apte per QA funcional de Sprint 3, pero la performance real queda pendent de validacio manual o automatitzada especifica. No hi ha evidencia en aquesta execucio de regressions evidents com errors 500 en escenaris concurrents coberts, pero tampoc hi ha dades suficients per afirmar objectius de latencia o capacitat.

## Pendents

- Pending: smoke manual de performance sobre endpoints principals d'accounts en entorn desplegat o entorn Docker local estable.
- Pending: benchmark basic de login, registre, `me`, actualitzacio de perfil i password reset request/confirm.
- Pending: prova de carrega curta amb concurrencia controlada per login i registre.
- Pending: capturar metriques reals abans de definir llindars de Sprint o release.

## Recomanacio QA

No bloquejar el merge exclusivament per performance mentre no hi hagi criteris quantitatius acordats. Si el release requereix garantia operativa, executar com a minim un smoke manual amb temps observats i una prova curta de concurrencia abans de tancar l'Epic 1.
