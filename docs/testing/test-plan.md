# Test Plan – Backend (US1–US7)

## Objectiu
Validar el correcte funcionament del sistema d’autenticació i gestió d’usuaris:
registre, login, logout, perfil i gestió de rols.

## Abast
Aquest pla cobreix:
- US1 – Registre
- US2 – Login
- US3 – Logout
- US4 – Rol inicial
- US5 – Canvi de rol
- US6 – Edició de perfil
- US7 – Visualització de perfil

## Tipus de proves
- Tests automatitzats (Django TestCase / API tests)
- Proves manuals d’API (Postman)
- Verificació de persistència (DBeaver)
- Validació d’entorn (Docker)
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
- autenticació
- permisos
- gestió de sessions

## Criteris d’acceptació
Una funcionalitat es considera correcta si:
- retorna codis HTTP adequats
- valida correctament errors
- persisteix dades a PostgreSQL
- passa els tests automatitzats
- no té migracions pendents (`makemigrations --check --dry-run`)
- passa els checks de CI
- té evidència documentada de la seva validació