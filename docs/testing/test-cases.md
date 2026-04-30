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
| TC-BE-ACC-001 | API | `/me/` amb administrador de sistema | Existeix un usuari creat amb `createsuperuser` | Autenticar el superuser i fer `GET /api/accounts/me/` | La resposta retorna `is_staff=true`, `is_superuser=true` i `is_system_admin=true` | Pass |
| TC-BE-ACC-002 | API | `/me/` amb administrador de finca | Existeix un usuari amb `profile.role="admin"` però sense permisos de superuser | Autenticar l’usuari i fer `GET /api/accounts/me/` | La resposta retorna `role="admin"` però `is_system_admin=false` | Pass |
| TC-BE-ACC-003 | API | Login d’administrador de sistema | Existeix un usuari creat amb `createsuperuser` | Fer `POST /api/accounts/login/` amb email i contrasenya correctes | La resposta retorna `access` i `refresh` | Pass |