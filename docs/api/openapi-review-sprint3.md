# OpenAPI review Sprint 3

## Informacio general

Data: 25/05/2026
Branca: qa/backend-openapi-sprint3
Base: Desenvolupament actualitzat
Entorn: Backend local amb Docker Compose
Eina: drf-spectacular

## Objectiu

Generar i revisar l'esquema OpenAPI del backend de BuildRank per validar el contracte API disponible per frontend, proves manuals, documentacio tecnica i futures integracions.

## Comanda executada

docker compose exec web python manage.py spectacular --file openapi-schema.yml --validate

## Fitxers generats

- docs/api/openapi-generation-sprint3.txt
- docs/api/openapi-schema.yml
- docs/api/openapi-review-sprint3.md

## Resultat de generacio

| Metrica | Resultat |
|---|---:|
| Schema generat | Si |
| Mida del schema | 147857 bytes |
| Warnings totals | 197 |
| Warnings unics | 110 |
| Errors totals | 160 |
| Errors unics | 39 |

## Interpretacio

L'esquema OpenAPI es genera, pero drf-spectacular informa de diversos problemes de documentacio automatica. Aquests avisos no indiquen necessariament errors funcionals del backend, sino punts on l'eina no pot inferir correctament serializers, autenticacio, tipus de camps calculats o parametres.

El fitxer generat comenca amb openapi: 3.0.3 i inclou paths del backend, per tant es considera una base valida de contracte API, encara que incompleta o poc precisa en alguns endpoints.

## Categories principals detectades

| Categoria | Exemples | Severitat QA | Decisio |
|---|---|---|---|
| Autenticador custom no documentat | AccountStatusJWTAuthentication sense OpenApiAuthenticationExtension | Medium | Afegir extensio OpenAPI per JWT custom. |
| APIViews sense serializer inferible | LoginView, MeView, ChatTokenView, EmetreVotView, endpoints de moderacio de chat | Medium | Afegir serializer_class o @extend_schema en endpoints principals. |
| Serializers no resolts en ViewSets | EdificiViewSet, HabitatgeViewSet, RankingViewSet, CatalegMilloraViewSet | Medium | Revisar anotacions @extend_schema i evitar strings no resolubles. |
| SerializerMethodField sense tipus explicit | get_heat_risk, get_habitatges, get_num_vots_total, get_ha_votat | Low | Afegir type hints o @extend_schema_field. |
| Path parameters no tipats | id en alguns viewsets, ranking/{id}, millores/{id} | Low/Medium | Anotar parametres amb @extend_schema o tipar rutes. |
| Col·lisions operationId | habitatges_retrieve, edificis_manual_retrieve | Low | Ajustar operation_id en endpoints col·lisionats. |
| Col·lisions enum | camps estat en diferents components | Low | Afegir ENUM_NAME_OVERRIDES si es vol netejar el schema. |

## Endpoints o arees mes afectades

- Accounts: login, logout, me, reset password, assignacions, bloqueig/suspensio d'usuaris i dashboard admin.
- Buildings: edificis, habitatges, millores, ranking, simulacions, votacions de simulacions i endpoints manuals.
- Chat: token, canals, moderacio, bans, mutes, shadowban i canals d'edificis similars.
- Community: emetre vot i serializers amb camps calculats.
- Notifications: llegir notificacio, llegir totes i comptador de no llegides.
- Verification, seasons, leagues, participations i audit: sobretot warning d'autenticador custom.

## Decisio de qualitat

No es considera un blocker de release perque el backend ja ha passat regressio, coverage, k6 i SonarCloud. Tot i aixo, es considera deute tecnic de documentacio API.

Per una millora professional, la prioritat recomanada es:

1. Afegir OpenApiAuthenticationExtension per AccountStatusJWTAuthentication.
2. Documentar amb @extend_schema els endpoints critics d'accounts, buildings, seasons, leagues, community i chat.
3. Afegir type hints o @extend_schema_field als SerializerMethodField principals.
4. Resoldre operationId duplicats i enums si es vol publicar una documentacio API neta.

## Conclusio

La generacio OpenAPI queda documentada i versionada com a evidencia de contracte API del Sprint 3. El schema generat es pot utilitzar com a base, pero no s'ha de considerar una especificacio final completament depurada fins resoldre els warnings principals.
