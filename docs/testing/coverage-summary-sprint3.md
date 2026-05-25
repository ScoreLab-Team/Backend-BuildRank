# Coverage summary Sprint 3

## Informació general

Data: 25/05/2026
Branca: Desenvolupament
Entorn: Backend local amb Docker Compose
Eina: coverage.py 7.14.0

## Resultat global

| Mètrica | Resultat |
|---|---:|
| Tests executats | 751 |
| Statements analitzats | 13.483 |
| Statements no coberts | 1.249 |
| Cobertura global backend | 91% |
| Resultat | Acceptat |

## Evidències generades

- docs/testing/logs/backend-coverage-report.txt
- docs/testing/coverage/coverage.xml
- docs/testing/coverage/coverage.json

## Àrees amb cobertura baixa o millorable

- apps/accounts/management/commands/cleanup_expired_tokens.py: 0%. Comanda de manteniment.
- apps/buildings/management/commands/seed_carrers_barcelona.py: 0%. Script de seed.
- apps/buildings/management/commands/seed_millores.py: 0%. Script de seed.
- apps/chat/management/commands/cleanup_stream_users.py: 0%. Comanda operativa de GetStream.
- apps/chat/management/commands/configure_getstream.py: 0%. Comanda operativa de GetStream.
- apps/chat/management/commands/sync_users_to_stream.py: 0%. Comanda operativa de GetStream.
- apps/buildings/services/segmentator.py: 0%. Servei auxiliar no exercitat directament.
- apps/buildings/services/building_lookup.py: 13%. Servei auxiliar.
- apps/verification/services/ocr.py: 23%. Servei amb dependència OCR/externa.
- apps/leagues/views.py: 48%. Vistes amb branques pendents de cobertura.
- apps/participations/services.py: 50%. Servei curt amb branques pendents.
- apps/buildings/permissions.py: 59%. Permisos coberts funcionalment via API, però amb branques internes no cobertes directament.

## Interpretació

La cobertura global del backend és del 91%, amb 13.483 statements analitzats i 1.249 statements no coberts. És un resultat alt per a una release candidata d'MVP, especialment perquè la suite completa passa amb 751 tests.

Les àrees amb cobertura baixa corresponen principalment a comandes de manteniment, scripts de seed, integracions externes o branques defensives. No s'han detectat gaps crítics que bloquegin la release candidata.

## Decisió de qualitat

La cobertura es considera suficient per continuar amb revisió de seguretat/configuració, performance/k6, SonarQube i posterior integració frontend.

