# US48 — Moderació de contingut (missatges i comportament)

## Tasca 1: Definició d'accions de moderació i estats de contingut

---

## 1. Tipus de canals de xat

BuildRank disposa de dos tipus de canals de xat gestionats via **GetStream**:

| Tipus de canal | ID format | Accés |
|---|---|---|
| Comunitari d'edifici | `building_{idEdifici}` | Tots els membres de l'edifici (administrador de finca, propietaris i llogaters del pis) |
| Twin Building | `twin_group_{groupId}_admins` | Únicament administradors de finca i propietaris que gestionen edificis del grup |

---

## 2. Estats de contingut

### 2.1. Estats d'un missatge

| Estat | Identificador | Descripció |
|---|---|---|
| **Visible** | `visible` | Estat per defecte. El missatge és accessible a tots els membres del canal. |
| **Reportat** | `flagged` | Un o més usuaris han reportat el missatge. Pendent de revisió per un moderador. Continua visible fins que el moderador actua. |
| **Pendent de moderació automàtica** | `moderated_pending` | El missatge ha estat capturat per filtres automàtics de GetStream (contingut ofensiu, spam). Pot estar ocult temporalment mentre es revisa. |
| **Ocult** | `hidden` | Un moderador ha ocult el missatge (soft-delete). Deixa de ser visible per als membres, però el registre es conserva per auditoria. |
| **Eliminat** | `deleted` | El missatge ha estat eliminat de manera permanent per un moderador o per l'autor. No és recuperable. GetStream substitueix el contingut per un marcador. |

**Diagrama de transicions d'un missatge:**

```
visible ──── (report) ──────────► flagged ──── (revisat: ok) ──────────► visible
   │                                  │
   │                                  └── (revisat: infracció) ─────► hidden ──► deleted
   │
   └── (filtre auto) ──► moderated_pending ─── (aprovat) ──────────► visible
                                              └── (rebutjat) ──────► hidden ──► deleted
```

### 2.2. Estats d'un usuari respecte a un canal

| Estat | Identificador | Descripció |
|---|---|---|
| **Actiu** | `active` | Estat per defecte. L'usuari pot llegir i enviar missatges. |
| **Advertit** | `warned` | L'usuari ha rebut una advertència formal. Pot seguir usant el canal, però el sistema registra l'avís. |
| **Silenciat** | `muted` | L'usuari pot llegir el canal però no pot enviar missatges durant el període de silenciament. GetStream aplica `mute_user` natiu. |
| **Expulsat del canal** | `channel_banned` | L'usuari ha estat expulsat d'un canal concret. Perd l'accés a aquell canal. No afecta altres canals. |
| **Expulsat globalment** | `global_banned` | L'usuari ha estat expulsat de tots els canals de la plataforma. Acció reservada exclusivament a l'administrador de sistema. |
| **Shadow banned** | `shadow_banned` | L'usuari envia missatges que ell veu com enviats, però que no són visibles per a la resta de membres. Acció reservada exclusivament a l'administrador de sistema. |

**Diagrama de transicions d'un usuari:**

```
active ──── (advertència) ──────► warned ─────────────────────────────► active (si es resol)
  │                                  │
  │                                  └── (reincidència) ──► muted ──► active (fi silenciament)
  │                                                            │
  │                                                            └── (greu) ──► channel_banned
  │
  └── (molt greu / sistèmic) ──── [només admin sistema] ──────────────► global_banned
  │
  └── (abús continuat) ─────────── [només admin sistema] ──────────────► shadow_banned
```

---

## 3. Accions de moderació

### 3.1. Accions sobre missatges

| Acció | Identificador | Qui pot executar-la | Efecte sobre el missatge | Reversible |
|---|---|---|---|---|
| **Reportar missatge** | `flag_message` | Qualsevol membre del canal | `visible` → `flagged` | Sí (el moderador pot desestimar el report) |
| **Ocultar missatge** | `hide_message` | Administrador de finca (del seu edifici), admin sistema | `flagged` / `visible` → `hidden` | Sí |
| **Eliminar missatge** | `delete_message` (propi) | L'autor del missatge | `* → deleted` | No |
| **Eliminar missatge d'altre** | `delete_message` (altri) | Administrador de finca (del seu edifici), admin sistema | `* → deleted` | No |
| **Restaurar missatge** | `restore_message` | Administrador de finca (del seu edifici), admin sistema | `hidden` → `visible` | — |
| **Desestimar report** | `dismiss_flag` | Administrador de finca (del seu edifici), admin sistema | `flagged` → `visible` | — |

### 3.2. Accions sobre usuaris

| Acció | Identificador | Qui pot executar-la | Efecte sobre l'usuari | Reversible |
|---|---|---|---|---|
| **Advertir usuari** | `warn_user` | Administrador de finca (dins el seu edifici), admin sistema | `active` → `warned` | Sí |
| **Silenciar usuari** | `mute_user` | Administrador de finca (dins el seu edifici), admin sistema | `active` / `warned` → `muted` | Sí (`unmute_user`) |
| **Dessilenciar usuari** | `unmute_user` | Administrador de finca (dins el seu edifici), admin sistema | `muted` → `active` | — |
| **Expulsar del canal** | `ban_from_channel` | Administrador de finca (del seu edifici), admin sistema | `* → channel_banned` | Sí (`unban_from_channel`) |
| **Readmetre al canal** | `unban_from_channel` | Administrador de finca (del seu edifici), admin sistema | `channel_banned` → `active` | — |
| **Expulsió global** | `global_ban` | **Administrador de sistema únicament** | `* → global_banned` | Sí (`global_unban`) |
| **Aixecar expulsió global** | `global_unban` | **Administrador de sistema únicament** | `global_banned` → `active` | — |
| **Shadow ban** | `shadow_ban` | **Administrador de sistema únicament** | `* → shadow_banned` | Sí (`shadow_unban`) |
| **Aixecar shadow ban** | `shadow_unban` | **Administrador de sistema únicament** | `shadow_banned` → `active` | — |

---

## 4. Matriu de permisos de moderació per rol

| Acció | Llogater (`TENANT`) | Propietari (`OWNER`) | Adm. de finca (`ADMIN`) | Adm. de sistema (`is_superuser`) |
|---|:---:|:---:|:---:|:---:|
| `flag_message` | ✅ | ✅ | ✅ | ✅ |
| `hide_message` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `delete_message` (propi) | ✅ | ✅ | ✅ | ✅ |
| `delete_message` (d'altre) | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `restore_message` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `dismiss_flag` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `warn_user` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `mute_user` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `unmute_user` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `ban_from_channel` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `unban_from_channel` | ❌ | ❌ | ✅ (propi edifici) | ✅ |
| `global_ban` | ❌ | ❌ | ❌ | ✅ |
| `global_unban` | ❌ | ❌ | ❌ | ✅ |
| `shadow_ban` | ❌ | ❌ | ❌ | ✅ |
| `shadow_unban` | ❌ | ❌ | ❌ | ✅ |

> **Criteri ABAC per a l'administrador de finca:** Les accions marcades com "propi edifici" es validen comprovant que l'usuari és el `administradorFinca` de l'edifici al qual pertany el canal (`validate_building_channel_access`, implementat a `chat/services.py`). Un administrador de finca no pot moderar canals d'edificis que no administra.

> **Propietari i llogater com a membres:** Tant el propietari com el llogater accedeixen al canal comunitari de l'edifici a través del seu pis (`Habitatge.usuari`). No tenen cap capacitat de moderació sobre el canal; únicament poden reportar missatges i eliminar els seus propis.

> **Canals Twin Building:** En els canals de tipus twin building, les accions de moderació segueixen les mateixes regles. L'accés es valida via `validate_twin_channel_access` (implementat a `chat/services.py`), que comprova que l'usuari és administrador de finca o propietari d'un edifici del grup comparable.

---

## 5. Correspondència amb primitives de GetStream

Les accions de moderació de BuildRank es mapegen sobre les crides natives de la SDK de GetStream:

| Acció BuildRank | Primitiva GetStream |
|---|---|
| `flag_message` | `client.flag(target_message_id)` |
| `hide_message` / `restore_message` | `channel.update_message(message_id, {...})` amb camp de metadades d'estat |
| `delete_message` | `channel.delete_message(message_id)` |
| `mute_user` | `client.mute_user(target_id, user_id, timeout=N)` |
| `unmute_user` | `client.unmute_user(target_id, user_id)` |
| `ban_from_channel` | `channel.ban_user(target_id, ...)` |
| `unban_from_channel` | `channel.unban_user(target_id)` |
| `global_ban` | `client.ban_user(target_id, ...)` |
| `global_unban` | `client.unban_user(target_id)` |
| `shadow_ban` | `client.ban_user(target_id, shadow=True, ...)` |
| `shadow_unban` | `client.unban_user(target_id)` |

---

## 6. Consideracions de disseny

### 6.1. Traçabilitat i auditoria

Tota acció de moderació ha de quedar registrada per complir amb NFR-SEC-ISO-03 (traçabilitat d'accions sensibles). El registre mínim per acció és:

| Camp | Descripció |
|---|---|
| `moderator_id` | ID de l'usuari que executa l'acció |
| `moderator_role` | Rol de l'executor (`ADMIN`, `is_superuser`) |
| `target_user_id` o `target_message_id` | Recurs afectat |
| `channel_id` | Canal on s'ha produït l'acció |
| `action` | Identificador de l'acció executada |
| `reason` | Motiu proporcionat (opcional però recomanat) |
| `timestamp` | Data i hora de l'acció |
| `previous_state` / `new_state` | estats abans i després de l'acció |

### 6.2. Limitacions del MVP (Sprint 3)

- La moderació automàtica via filtres de GetStream (profanity filter, AI moderation) queda fora de l'abast del MVP. Les accions manuals cobreixen els casos bàsics.
- L'estat `warned` no té persistència pròpia a la base de dades de Django en aquesta primera iteració; s'implementa com a metadada de l'usuari a GetStream.
- La moderació dels canals Twin Building per part de l'administrador de finca és possible tècnicament, però queda pendent de validació de requisits durant el Sprint 3.

### 6.3. Criteris d'aplicació

- Un missatge `flagged` **no s'oculta automàticament**: cal acció manual del moderador. Això evita censura automàtica no justificada (NFR-SAFE-ISO-01).
- El `shadow_ban` és una mesura excepcional exclusiva de l'administrador de sistema. La seva existència no s'ha de revelar a l'usuari afectat.
- Expulsar un usuari del canal (`channel_banned`) **no elimina** els missatges ja enviats. La decisió d'eliminar-los és independent i requereix una acció explícita.
- L'administrador de finca actua sempre en l'àmbit dels edificis que administra. No pot prendre accions de moderació en canals d'edificis d'altres administradors.

---

## 7. Relació amb altres documents

- [Matriu de permisos RBAC/ABAC](./matriz-permisos-rbac-abac.md) — model d'autorització general del sistema.
- [Test suite overview](./test-suite-overview.md) — cobertura de tests actual.
- Implementació base del xat: `backend/apps/chat/services.py`, `backend/apps/chat/views.py`.
