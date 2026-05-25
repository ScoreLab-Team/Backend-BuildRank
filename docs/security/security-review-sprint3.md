
## Nota sobre Virtech / staging

Aquesta revisió correspon a l'entorn local amb Docker Compose sobre la branca de QA derivada de Desenvolupament.
La branca específica de staging, feature/staging-virtech, no estava actualitzada amb els últims canvis de Desenvolupament en el moment d'aquesta revisió.
Per tant, la validació específica de Virtech queda pendent i s'haurà de fer després d'actualitzar o reconciliar feature/staging-virtech amb Desenvolupament.
La revisió de Virtech haurà d'incloure docker-compose.virtech.yml, secrets, DEBUG, ALLOWED_HOSTS, CORS, CSRF, HTTPS, cookies secure, GetStream i migracions.
