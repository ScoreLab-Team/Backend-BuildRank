# Test Plan – Backend (US1–US7, US10–US20, US21–US25, US28–US30, Temporades)

## Objectiu
Validar el correcte funcionament del sistema d'autenticació i gestió d'usuaris, edificis, control d'accés, simulacions energètiques, càlcul de mètriques, gestió de temporades i rànquings.

---

## Abast

### Autenticació i usuaris
- US1 – Registre  
- US2 – Login  
- US3 – Logout  
- US4 – Rol inicial  
- US5 – Canvi de rol  
- US6 – Edició de perfil  
- US7 – Visualització de perfil  

### Control d’accés i seguretat
- US10 – Control d’accés segons rol (ABAC, permisos, IDOR)

### Gestió d’edificis
- US11 – Alta manual d’edifici  
- US12 – Introducció manual de dades estructurals  
- US14 – Visualització de la fitxa detallada d’edifici  
- US19 – Edició de dades d’edifici per usuaris autoritzats  
- US20 – Eliminació o desactivació d’edifici  

### Mètriques i càlculs
- US16 – Building Health Score  
- US15 – Classificació energètica estimada  

### Qualitat de dades
- US18 – Nivell de verificació  

### Rànquings i anàlisi
- US21 – Ranking general d’edificis  
- US22 – Ranking individual d’edifici  
- US23 – Rànquing per categoria  
- US24 – Evolució temporal d’edifici  
- US25 – Evolució per temporades  
- US28 – Ranking segmentat per grup comparable  

### Simulacions energètiques
- US29 – Motor de simulació d’estalvi energètic (Engine)  
- US30 – Persistència i gestió de simulacions multi-millora  

### Temporades
- Gestió de Temporades (`seasons`)
  - PENDENT → ACTIVA → TANCADA  

---

## Tipus de proves
- Tests automatitzats (Django TestCase / APITestCase)  
- Tests d’integració (simulacions, score i classificació amb BD real)  
- Tests unitaris (managers, serveis i lògica de negoci)  
- Proves manuals d’API (Postman)  
- Verificació de persistència (DBeaver)  
- Validació d’entorn (Docker)  
- Validació automàtica en CI  

---

## Eines
- Django TestCase / APITestCase  
- Docker Compose  
- Postman  
- DBeaver  
- coverage.py  
- GitHub Actions (CI)  

---

## Estratègia

El testing es basa en una estratègia incremental i basada en risc.

### 1. Autenticació i gestió d’usuaris
- Validació de registre, login i logout  
- Assignació i canvi de rols  
- Gestió de perfil  

### 2. Control d’accés i seguretat (crític)
- Estratègia **deny by default**  
- Validació de permisos per rol i atribut (ABAC)  
- Relació Usuari–Edifici  

Inclou:
- Respostes correctes (200)  
- Accés denegat (403)  
- Tests d’IDOR  

### 3. Gestió d’edificis i dades
- Creació (POST), consulta (GET) i actualització (PATCH/PUT)  
- Validacions server-side  
- Integritat referencial  

### 4. Càlculs i mètriques
- Building Health Score (US16):
  - càlcul correcte  
  - persistència  
  - versionat  
  - recalcul automàtic  

- Classificació energètica (US15):
  - coherència del model  
  - consistència dels resultats  

### 5. Qualitat de dades
- Nivell de verificació  
- Restriccions per rol  
- Coherència de dades  

### 6. Simulacions energètiques
- Tests d’integració amb BD real  
- Validació del motor de càlcul  
- Persistència multi-millora  

### 7. Rànquings i anàlisi
- Generació de rànquings  
- Segmentació  
- Evolució temporal  

### 8. Temporades
- Validació del cicle de vida:
  - PENDENT → ACTIVA → TANCADA  
- Tests de managers, API i admin  

### 9. Cicle de vida d’edificis
- Edició controlada (US19)  
- Eliminació/desactivació (US20)  

---

## Casos clau a validar

### Autenticació
- Registre correcte → 201  
- Login correcte → 200  
- Credencials incorrectes → 401  

### Control d’accés (US10)
- Accés autoritzat → 200  
- Accés no autoritzat → 403  
- Intent IDOR → 403  

### Edificis (US11–US12)
- Dades vàlides → 201 / 200  
- Camps buits → 400  
- Valors fora de rang → 400  

### Fitxa d’edifici (US14)
- Usuari vinculat → 200  
- Usuari no vinculat → 403  

### Building Health Score (US16)
- Càlcul correcte  
- Casos límit  
- Recalcul automàtic  

### Classificació energètica (US15)
- Resultats coherents  
- Persistència correcta  

### Verificació (US18)
- Actualització autoritzada → 200  
- No autoritzada → 403  

### Edició (US19)
- Usuari autoritzat → 200  
- Usuari no autoritzat → 403  

### Eliminació/desactivació (US20)
- Admin → correcte  
- Usuari normal → 403  
- Dades consistents  

### Simulacions (US29–US30)
- Execució correcta  
- Persistència correcta  
- Multi-millora funcional  

### Temporades
- Transicions vàlides → 200  
- Transicions invàlides → error  

---

## Criteris d’acceptació

Una funcionalitat es considera correcta si:

- retorna codis HTTP adequats (200, 201, 400, 401, 403)  
- valida errors i restriccions correctament  
- aplica control d’accés (rol + atribut)  
- persisteix dades a PostgreSQL  
- manté coherència de dades  
- recalcula mètriques quan correspon  
- passa els tests automatitzats  
- no té migracions pendents (`makemigrations --check --dry-run`)  
- passa CI  
- té evidència documentada de validació  