# Performance summary Sprint 3

## Informació general

Data: 25/05/2026  
Branca: qa/backend-performance-k6-sprint3  
Base: Desenvolupament actualitzat  
Entorn: Backend local amb Docker Compose + Nginx  
Eina: Grafana k6 via Docker  
Base URL usada per k6: `http://host.docker.internal` amb header `Host: localhost`

## Context

Abans d'executar k6 es va detectar un `502 Bad Gateway` en accedir via Nginx. La causa no era Django ni `ALLOWED_HOSTS`, sinó que Nginx mantenia resolta una IP antiga del contenidor `web` després de recrear-lo. Es va solucionar recreant/reiniciant Nginx.

Després de recrear Nginx, els endpoints protegits van passar de `502` a `401 Unauthorized`, que és el comportament esperat sense token.

## Tests executats

| ID | Script | Tipus | Resultat | Observacions |
|---|---|---|---|---|
| PERF-001 | `backend-smoke-unauth.js` | Smoke no autenticat | OK | Valida Nginx + backend + endpoints protegits sense token. |
| PERF-002 | `debug-auth-status.js` | Debug autenticat | OK | Confirma login 200, token i codis reals dels endpoints. |
| PERF-003 | `backend-authenticated-smoke.js` | Smoke autenticat repetitiu 1 VU / 30s | Parcial | Sense 401 ni 5xx, però algunes respostes fora de 200/403/404, probablement throttling/rate limit. |
| PERF-004 | `backend-authenticated-functional-smoke.js` | Smoke funcional autenticat 1 iteració | OK | Login + endpoints principals autenticats funcionen correctament. |

## Resultats principals

### PERF-001 — Smoke no autenticat

| Mètrica | Resultat |
|---|---:|
| VUs | 5 |
| Durada | 30s |
| Requests | 568 |
| Checks | 100% |
| Failed requests | 0.00% |
| p95 | 27.88ms |
| Resultat | Acceptat |

### PERF-003 — Smoke autenticat repetitiu

| Mètrica | Resultat |
|---|---:|
| VUs | 1 |
| Durada | 30s |
| Checks | 98.52% |
| Failed requests | 5.88% |
| p95 | 41.45ms |
| 401 | No detectats pels checks |
| 5xx | No detectats pels checks |
| Resultat | Acceptat amb observació |

Observació: el test repetitiu autenticat amb un únic usuari pot activar throttling o respostes controlades fora de 200/403/404. No s'observen errors d'autenticació ni errors de servidor.

### PERF-004 — Smoke funcional autenticat

| Mètrica | Resultat |
|---|---:|
| VUs | 1 |
| Iteracions | 1 |
| Requests | 6 |
| Checks | 100% |
| Failed requests | 0.00% |
| p95 | 360.53ms |
| Resultat | Acceptat |

## Endpoints inclosos

### No autenticat

- `/api/accounts/me/`
- `/api/buildings/edificis/`
- `/api/seasons/`
- `/api/leagues/`

### Autenticat

- `/api/accounts/login/`
- `/api/accounts/me/`
- `/api/accounts/me/edificis/`
- `/api/buildings/edificis/`
- `/api/seasons/`
- `/api/leagues/`

Es va retirar `/api/accounts/me/role/` del test GET perquè retorna `405 Method Not Allowed`; per tant, no era adequat per a aquest smoke.

## Conclusions

Els tests de performance inicials indiquen que el backend local, servit via Nginx, respon de manera estable i amb latències baixes en escenaris de smoke.

No s'han detectat errors 5xx ni problemes d'autenticació en els tests finals acceptats. El comportament observat en el test autenticat repetitiu es documenta com a possible efecte de throttling/rate limit, no com a caiguda del backend.

## Decisions

- Els scripts k6 es versionen com a evidència i base de futures proves.
- Els logs k6 es guarden com a evidència de QA.
- Per una prova de càrrega autenticada més realista caldria crear múltiples usuaris de test o ajustar explícitament el throttling per entorn de performance.
- No es farà càrrega contra GetStream en aquesta fase; el xat real amb GetStream queda per prova d'integració específica.
