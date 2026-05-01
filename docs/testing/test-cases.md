# Test Cases – Accounts Backend (US1–US7)

| ID | US | Tipus | Endpoint | Test automatitzat | Resultat esperat | Estat |
|---|---|---|---|---|---|---|
| TC-ACC-001 | US1 | API | POST /register/ | test_register_success_creates_user_profile_and_default_role | 201 + usuari i perfil creats amb rol per defecte | Pass |
| TC-ACC-002 | US1 | API | POST /register/ | test_register_success_with_explicit_owner_role | 201 + usuari creat amb rol owner | Pass |
| TC-ACC-003 | US1 | API | POST /register/ | test_register_rejects_duplicate_email | 400 + email duplicat rebutjat | Pass |
| TC-ACC-004 | US1 | API | POST /register/ | test_register_rejects_password_mismatch | 400 + passwords no coincidents | Pass |
| TC-ACC-005 | US1 | API | POST /register/ | test_register_rejects_password_without_letters | 400 + password invàlida | Pass |
| TC-ACC-006 | US1 | API | POST /register/ | test_register_rejects_password_without_digits | 400 + password invàlida | Pass |
| TC-ACC-007 | US1 | Seguretat | POST /register/ | test_register_throttle_5_per_hour | 429 + límit de peticions aplicat | Pass |
| TC-ACC-008 | US2 | API | POST /login/ | test_login_success_returns_tokens_user_and_creates_audit_log | 200 + tokens + log creat | Pass |
| TC-ACC-009 | US2 | API | POST /login/ | test_login_rejects_invalid_credentials | 401 + credencials incorrectes | Pass |
| TC-ACC-010 | US2 | Seguretat | POST /login/ | test_login_session_limit_blacklists_oldest_refresh_token | Token antic invalidat | Pass |
| TC-ACC-011 | US2 | Seguretat | POST /login/ | test_login_throttle_3_per_minute | 429 + límit de peticions | Pass |
| TC-ACC-012 | US3 | API | POST /logout/ | test_logout_success_revokes_refresh_and_updates_audit_log | 200 + refresh revocat | Pass |
| TC-ACC-013 | US3 | API | POST /logout/ | test_logout_rejects_invalid_refresh_token | 400 + refresh invàlid | Pass |
| TC-ACC-014 | US3 | Seguretat | POST /logout/ | test_logout_then_refresh_reuse_fails | 401 + token no reutilitzable | Pass |
| TC-ACC-015 | US4 | API | POST /register/ | test_register_success_creates_user_profile_and_default_role | Rol inicial assignat | Pass |
| TC-ACC-016 | US5 | API | PATCH /me/role/ | test_authenticated_user_can_change_role_to_tenant | 200 + rol canviat | Pass |
| TC-ACC-017 | US5 | API | PATCH /me/role/ | test_authenticated_user_can_change_role_to_owner | 200 + rol canviat | Pass |
| TC-ACC-018 | US5 | Permisos | PATCH /me/role/ | test_authenticated_user_cannot_change_role_to_admin | 403 + accés denegat | Pass |
| TC-ACC-019 | US5 | Permisos | PATCH /me/role/ | test_unauthenticated_user_cannot_change_role | 401 + no autenticat | Pass |
| TC-ACC-020 | US6 | API | PATCH /me/ | test_authenticated_user_can_patch_own_profile | 200 + perfil actualitzat | Pass |
| TC-ACC-021 | US6 | API | PATCH /me/ | test_authenticated_user_can_patch_own_account | 200 + compte actualitzat | Pass |
| TC-ACC-022 | US6 | API | PUT /me/ | test_authenticated_user_can_put_own_account | 200 + compte reemplaçat | Pass |
| TC-ACC-023 | US6 | API | PATCH /me/ | test_update_account_rejects_duplicate_email | 400 + email duplicat | Pass |
| TC-ACC-024 | US6 | Seguretat | PATCH /me/ | test_update_account_ignores_role_field | Rol no modificable | Pass |
| TC-ACC-025 | US7 | API | GET /me/ | test_authenticated_user_can_get_own_profile | 200 + perfil retornat | Pass |
| TC-ACC-026 | US7 | API | GET /me/ | test_me_returns_current_user_profile_data | Dades coherents | Pass |
| TC-ACC-027 | US7 | Permisos | GET /me/ | test_me_requires_authentication | 401 + no autenticat | Pass |
| TC-ACC-028 | US7 | Seguretat | GET /me/ | test_me_with_tampered_access_token_fails | 401 + token invàlid | Pass |
| TC-ACC-029 | US7 | Seguretat | GET /me/ | test_me_with_expired_access_token_fails | 401 + token expirat | Pass |
| TC-BE-ACC-001 | – | API | GET /me/ | Superuser creat amb `createsuperuser` | `is_staff=true`, `is_superuser=true`, `is_system_admin=true` | Pass |
| TC-BE-ACC-002 | – | API | GET /me/ | Usuari amb `profile.role="admin"` sense permisos de superuser | `role="admin"`, `is_system_admin=false` | Pass |
| TC-BE-ACC-003 | – | API | POST /login/ | Superuser creat amb `createsuperuser` | Retorna `access` i `refresh` | Pass |


## Test Cases – Buildings & Simulations (US29–US30)

| ID | US | Tipus | Component | Test automatitzat | Resultat esperat | Estat |
|---|---|---|---|---|---|---|
| TC-BLD-01 | US29 | Integració | `engine.py` | `test_score_base_amb_historial_bhs` | Càlcul basat en l'últim score real de la BD | Pass |
| TC-BLD-02 | US29 | Integració | `engine.py` | `test_dades_base_amb_habitatges` | Estalvi calculat sobre dades reals d'habitatge | Pass |
| TC-BLD-03 | US29 | Integració | `engine.py` | `test_inferir_quantitats_per_totes_unitats` | Assignació de quantitat segons unitat (m2, kWp...) | Pass |
| TC-SYS-01 | US30 | Sistema | API + App | Manual (Flux complet) | Simulació guardada correctament a PostgreSQL | Pass |


## Test Cases – Temporades (Seasons)

### SeasonManager (unitaris)

| ID | Tipus | Classe de test | Test automatitzat | Resultat esperat | Estat |
|---|---|---|---|---|---|
| TC-SEA-MGR-001 | Unitari | `EstatTemporadaManagerTest` | `test_temporada_creada_en_estat_pendent` | Estat inicial = PENDENT, `activa=False` | Pass |
| TC-SEA-MGR-002 | Unitari | `EstatTemporadaManagerTest` | `test_iniciar_temporada_pendent` | Estat = ACTIVA, `activa=True` | Pass |
| TC-SEA-MGR-003 | Unitari | `EstatTemporadaManagerTest` | `test_iniciar_temporada_activa_falla` | ValueError si ja activa | Pass |
| TC-SEA-MGR-004 | Unitari | `EstatTemporadaManagerTest` | `test_iniciar_temporada_tancada_falla` | ValueError si tancada | Pass |
| TC-SEA-MGR-005 | Unitari | `EstatTemporadaManagerTest` | `test_iniciar_quan_ja_existeix_activa_falla` | ValueError si ja existeix una altra activa | Pass |
| TC-SEA-MGR-006 | Unitari | `EstatTemporadaManagerTest` | `test_tancar_temporada_activa` | Estat = TANCADA, `activa=False` | Pass |
| TC-SEA-MGR-007 | Unitari | `EstatTemporadaManagerTest` | `test_tancar_temporada_pendent_falla` | ValueError si pendent | Pass |
| TC-SEA-MGR-008 | Unitari | `EstatTemporadaManagerTest` | `test_tancar_temporada_tancada_falla` | ValueError si ja tancada | Pass |
| TC-SEA-MGR-009 | Unitari | `EstatTemporadaManagerTest` | `test_is_active_temporada_activa_dins_rang` | `is_active` = True | Pass |
| TC-SEA-MGR-010 | Unitari | `EstatTemporadaManagerTest` | `test_is_active_temporada_pendent` | `is_active` = False | Pass |
| TC-SEA-MGR-011 | Unitari | `EstatTemporadaManagerTest` | `test_is_active_temporada_tancada` | `is_active` = False | Pass |
| TC-SEA-MGR-012 | Unitari | `SeasonManagerExtraTest` | `test_create_season` | `create_season` crea temporada en estat PENDENT | Pass |
| TC-SEA-MGR-013 | Unitari | `SeasonManagerExtraTest` | `test_is_active_activa_fora_de_rang` | `is_active` = False si dates expirades | Pass |

### Temporada API REST

| ID | Tipus | Endpoint | Test automatitzat | Resultat esperat | Estat |
|---|---|---|---|---|---|
| TC-SEA-API-001 | API | POST /seasons/ | `test_admin_pot_crear_temporada` | 201 + estat=PENDENT | Pass |
| TC-SEA-API-002 | Permisos | POST /seasons/ | `test_usuari_no_admin_no_pot_crear_temporada` | 403 | Pass |
| TC-SEA-API-003 | Permisos | POST /seasons/ | `test_no_autenticat_no_pot_crear_temporada` | 401 | Pass |
| TC-SEA-API-004 | API | GET /seasons/ | `test_usuari_autenticat_pot_llistar_temporades` | 200 | Pass |
| TC-SEA-API-005 | API | GET /seasons/{id}/ | `test_usuari_autenticat_pot_veure_detall` | 200 + camps `estat` i `activa` presents | Pass |
| TC-SEA-API-006 | API | POST /seasons/{id}/iniciar/ | `test_admin_pot_iniciar_temporada_pendent` | 200 + estat=ACTIVA, `activa=True` | Pass |
| TC-SEA-API-007 | API | POST /seasons/{id}/iniciar/ | `test_iniciar_temporada_activa_retorna_400` | 400 + camp `error` | Pass |
| TC-SEA-API-008 | API | POST /seasons/{id}/iniciar/ | `test_iniciar_temporada_tancada_retorna_400` | 400 | Pass |
| TC-SEA-API-009 | API | POST /seasons/{id}/iniciar/ | `test_iniciar_quan_ja_hi_ha_activa_retorna_400` | 400 | Pass |
| TC-SEA-API-010 | Permisos | POST /seasons/{id}/iniciar/ | `test_usuari_no_admin_no_pot_iniciar` | 403 | Pass |
| TC-SEA-API-011 | API | POST /seasons/{id}/tancar/ | `test_admin_pot_tancar_temporada_activa` | 200 + estat=TANCADA, `activa=False` | Pass |
| TC-SEA-API-012 | API | POST /seasons/{id}/tancar/ | `test_tancar_temporada_pendent_retorna_400` | 400 + camp `error` | Pass |
| TC-SEA-API-013 | API | POST /seasons/{id}/tancar/ | `test_tancar_temporada_tancada_retorna_400` | 400 | Pass |
| TC-SEA-API-014 | Permisos | POST /seasons/{id}/tancar/ | `test_usuari_no_admin_no_pot_tancar` | 403 | Pass |
| TC-SEA-API-015 | Permisos | GET /seasons/ | `test_no_autenticat_no_pot_llistar` | 401 | Pass |
| TC-SEA-API-016 | Permisos | GET /seasons/{id}/ | `test_no_autenticat_no_pot_veure_detall` | 401 | Pass |
| TC-SEA-API-017 | API | PATCH /seasons/{id}/ | `test_admin_pot_actualitzar_temporada` | 200 + dades actualitzades | Pass |
| TC-SEA-API-018 | Permisos | PATCH /seasons/{id}/ | `test_no_admin_no_pot_actualitzar` | 403 | Pass |
| TC-SEA-API-019 | API | DELETE /seasons/{id}/ | `test_admin_pot_eliminar_temporada` | 204 | Pass |
| TC-SEA-API-020 | Permisos | DELETE /seasons/{id}/ | `test_no_admin_no_pot_eliminar` | 403 | Pass |

### Accions d'admin de Django (TemporadaAdmin)

| ID | Tipus | Acció | Test automatitzat | Resultat esperat | Estat |
|---|---|---|---|---|---|
| TC-SEA-ADM-001 | Admin | `action_iniciar` | `test_action_iniciar_success` | Estat = ACTIVA + missatge success | Pass |
| TC-SEA-ADM-002 | Admin | `action_iniciar` | `test_action_iniciar_error` | Missatge error si ja activa | Pass |
| TC-SEA-ADM-003 | Admin | `action_iniciar` | `test_action_iniciar_mixed` | Missatges success i error en queryset mixt | Pass |
| TC-SEA-ADM-004 | Admin | `action_tancar` | `test_action_tancar_success` | Estat = TANCADA + missatge success | Pass |
| TC-SEA-ADM-005 | Admin | `action_tancar` | `test_action_tancar_error` | Missatge error si pendent | Pass |
| TC-SEA-ADM-006 | Admin | `action_tancar` | `test_action_tancar_mixed` | Missatges success i error en queryset mixt | Pass |


## Test Cases – Lligues i Rànquings (US21–US25, US28)

| ID | US | Tipus | Endpoint | Test automatitzat | Resultat esperat | Estat |
|---|---|---|---|---|---|---|
| TC-LGU-001 | US21 | Unitari | – | `test_ranking_global_includes_all_segments` | Ranking global inclou tots els segments | Pass |
| TC-LGU-002 | US28 | Unitari | – | `test_ranking_segment_group_a` | Segment A conté exactament els edificis del grup A | Pass |
| TC-LGU-003 | US28 | Unitari | – | `test_ranking_segment_group_b` | Segment B conté exactament l'edifici del grup B | Pass |
| TC-LGU-004 | US23 | API | GET /leagues/{id}/ranking/?group=X | `test_api_segmented_ranking` | 200 + 2 resultats filtrats per grup | Pass |
| TC-LGU-005 | US23 | API | GET /leagues/{id}/ranking/?group=999 | `test_ranking_invalid_group_returns_404` | 404 per grup inexistent | Pass |
| TC-LGU-006 | US25 | API | GET /leagues/{id}/posicio_edifici/?segment=true | `test_ranking_segmentado_auto` | 200, `segmentat=True`, grup detectat automàticament | Pass |
| TC-LGU-007 | US25 | API | GET /leagues/{id}/posicio_edifici/ | `test_ranking_sin_segmentacion` | 200, `segmentat=False` | Pass |
