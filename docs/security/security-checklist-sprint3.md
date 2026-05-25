# Security checklist Sprint 3

## Autenticació

- [ ] Els endpoints sensibles requereixen token.
- [ ] Login retorna tokens correctes.
- [ ] Refresh token funciona segons política definida.
- [ ] Logout/blacklist funciona si aplica.
- [ ] Recuperació de contrasenya no enumera comptes.

## Autorització

- [ ] Sense token retorna 401.
- [ ] Rol incorrecte retorna 403/404.
- [ ] Manipulació d'idEdifici queda bloquejada.
- [ ] Owner/tenant no veu edificis aliens.
- [ ] Admin finca només gestiona edificis que li corresponen.
- [ ] Admin finca amb verificació pendent no accedeix a edificis no aprovats.
- [ ] Superuser/admin sistema queda diferenciat d'admin finca.
- [ ] Votacions no permeten accions no autoritzades.
- [ ] Un usuari no pot votar dues vegades si aplica.

## Exposició de dades

- [ ] El mapa no exposa emails.
- [ ] El mapa no exposa habitatges.
- [ ] El mapa no exposa documents.
- [ ] Endpoints generals no retornen dades personals innecessàries.
- [ ] Errors no exposen stacktrace en entorn no-debug.

## Configuració

- [ ] DEBUG revisat.
- [ ] ALLOWED_HOSTS revisat.
- [ ] CORS revisat.
- [ ] Secrets fora del repositori.
- [ ] Media files fora de Git.
