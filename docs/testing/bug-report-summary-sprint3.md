# Bug report summary Sprint 3

| ID | Severitat | Àrea | Descripció | Estat | Responsable | Retest |
|---|---|---|---|---|---|---|
| BUG-001 | Low | Chat / Test config | Durant els tests de chat apareixen logs de GetStream amb `api_key not valid`, però els tests passen. Probablement cal mockejar o desactivar crides externes en entorn de test. | Open | Backend QA | Pending |
| QA-STG-001 | Medium | Staging / Virtech | La branca feature/staging-virtech no està actualitzada amb Desenvolupament. La validació específica de docker-compose.virtech.yml i configuració real de staging queda pendent. | Open | DevOps / Backend | Pending |
