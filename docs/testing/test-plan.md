# Test Plan – Backend (US1–US7, US21–US25, US28–US30, Temporades)

## Objectiu
Validar el correcte funcionament del sistema d'autenticació i gestió d'usuaris, edificis, simulacions energètiques, gestió de temporades i rànquings de lligues.

## Abast
Aquest pla cobreix:
- US1 – Registre
- US2 – Login
- US3 – Logout
- US4 – Rol inicial
- US5 – Canvi de rol
- US6 – Edició de perfil
- US7 – Visualització de perfil
- US21 – Ranking general d'edificis
- US22 – Ranking individual d'edifici
- US23 – Rànquing per categoria
- US24 – Evolució temporal d'edifici
- US25 – Evolució per temporades
- US28 – Ranking segmentat per grup comparable
- US29 – Motor de simulació d'estalvi energètic (Engine)
- US30 – Persistència i gestió de simulacions multi-millora
- Gestió de Temporades (`seasons`) – cicle de vida PENDENT → ACTIVA → TANCADA

## Tipus de proves
- Tests automatitzats (Django TestCase / APITestCase)
- Tests d'integració (motor de simulació amb BD real)
- Tests unitaris de managers i lògica de negoci
- Proves manuals d'API (Postman)
- Verificació de persistència (DBeaver)
- Validació d'entorn (Docker)
- Validació automàtica en CI

## Eines
- Django TestCase / APITestCase
- Docker Compose
- Postman
- DBeaver
- coverage.py
- GitHub Actions (CI)

## Estratègia
El testing es basa en una estratègia incremental i basada en risc, prioritzant:
- autenticació i permisos
- gestió de sessions i rols
- cicle de vida de temporades (transicions d'estat)

Per al mòdul de simulacions, s'aplica una estratègia de proves d'integració reals.
L'engine de càlcul es valida utilitzant dades reals instanciades en base de dades per garantir la precisió de les fórmules matemàtiques en un entorn idèntic al de producció.

Per al mòdul de temporades, es validen les transicions d'estat (`PENDENT → ACTIVA → TANCADA`) tant a nivell de manager (tests unitaris) com a nivell d'API REST i accions d'admin de Django.

## Criteris d'acceptació
Una funcionalitat es considera correcta si:
- retorna codis HTTP adequats
- valida correctament errors i transicions invàlides
- persisteix dades a PostgreSQL
- passa els tests automatitzats
- no té migracions pendents (`makemigrations --check --dry-run`)
- passa els checks de CI
- té evidència documentada de la seva validació
