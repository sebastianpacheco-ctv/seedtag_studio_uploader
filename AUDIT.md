# Auditoría — Studio Batch Uploader

Auditoría con 3 subagentes en paralelo (seguridad, backend, frontend/i18n) + verificación
manual de los hallazgos de mayor impacto. Fecha: 2026-05-29.

Alcance: `app/app.py`, `app/database.py`, `app/jira_client.py`, `app/templates/index.html`,
config de despliegue. El cliente `reference/studio_api.py` se trató como dependencia dada.

Resumen: **3 CRÍTICOS, 8 ALTOS, 7 MEDIOS, ~10 BAJOS.** Lo bueno: `.env` NO está trackeado
(solo `.env.example`), y el escapado XSS en el frontend es sólido (`escapeHtml` aplicado en
todos los sinks dinámicos). Lo serio está en **auth y configuración de despliegue**.

---

## 🔴 CRÍTICOS

### C1 — SSO falso: cualquiera obtiene sesión de Seedtag
`app/app.py:84-93` — `/api/login` es un POST sin autenticación que setea
`session["user_email"]` incondicionalmente. No hay verificación de Google. Un `curl -X POST
/api/login` da identidad "logueada" a cualquiera. El SSO es 100% teatro en el frontend.
**Fix:** OIDC real de Google (`authlib`), validar `id_token` (firma/`aud`/`exp`), forzar
`hd == "seedtag.com"`. Hasta entonces, gate de `@login_required` en todos los `/api/*`.

### C2 — `FLASK_SECRET_KEY` con fallback hardcodeado → forja de sesión
`app/app.py:32` — `os.getenv("FLASK_SECRET_KEY", "dev-only-secret-key-12345")`. Si la env no
está seteada (el Dockerfile/firebase no la setean), las cookies se firman con un secreto
público conocido → cualquiera forja una sesión válida (incluido `studio_jwt`, `user_email`).
**Fix:** fail-closed — exigir la env en producción; generar con `secrets.token_hex(32)`.

### C3 — `FLASK_DEBUG` por defecto `True` → RCE por consola Werkzeug
`app/app.py:415` — `os.getenv("FLASK_DEBUG", "True")`. Cualquier corrida fuera del contenedor
levanta con debug on → consola interactiva de Werkzeug = RCE si es alcanzable. El Dockerfile
lo mitiga (gunicorn + `FLASK_DEBUG=False`), pero el default debe ser seguro.
**Fix:** default `"False"`.

---

## 🟠 ALTOS

### A1 — Sin CSRF + cookies de sesión sin flags
`app/app.py:31-32, 84-161` — Ningún token anti-CSRF en POSTs (`/api/upload`, `/api/set-jwt`).
`/api/set-jwt` permite plantar un JWT de Studio en la sesión de una víctima. Cookie sin
`Secure`/`SameSite` explícitos. **Fix:** `flask-wtf` CSRFProtect o header `X-Requested-With`
verificado server-side; `app.config` con `SESSION_COOKIE_SECURE/HTTPONLY/SAMESITE="Lax"`.

### A2 — Errores de Studio reflejados verbatim al cliente y persistidos en DB/UI
`app/app.py:140,142,352,358` — `str(e)` de excepciones de `requests`/Studio va al navegador y
se guarda en `job_items.msg` (que la UI renderiza). Puede filtrar URLs internas / detalle de
auth. **Fix:** `log.exception` server-side, mensaje genérico al cliente.

### A3 — Sin límites de tamaño/tipo/cantidad en upload → DoS / disco lleno
`app/app.py:175-199` — No hay `MAX_CONTENT_LENGTH`, ni cap de archivos, ni validación de
extensión server-side (el `accept="video/*"` es cosmético). `/tmp` en Cloud Run es
memory-backed → OOM. **Fix:** `MAX_CONTENT_LENGTH`, allowlist `{.mp4,.mov,.webm}`, cap de
cantidad, cleanup en `finally`.

### A4 — JWT expirado: fuga de temp files + items colgados en "queued"
`app/app.py:331-377` — En `StudioJWTExpiredError` hace `break` del loop: los items restantes
quedan en `queued` para siempre, el job se marca `done`, y sus temp files nunca se borran.
**Fix:** antes del `break`, marcar los `queued` restantes como `error` y borrar sus temp files
(o cleanup en `finally`).

### A5 — SSE busy-poll a SQLite 1/s por 300s, retiene un thread, sin detectar desconexión
`app/app.py:226-257` — Cada `/stream` ocupa un thread del worker pool hasta 300s, poleando la
DB cada segundo y contendiendo el `db_lock` con el worker real. Sin manejo de desconexión del
cliente. Pocas pestañas → agotamiento de threads. **Fix:** mover a polling client-side de
`/api/job/<id>` (el worker ya persiste cada cambio), o terminar el loop al desconectar.

### A6 — `except (..., Exception)` reintenta fallos no-idempotentes → posibles creatives duplicados
`app/app.py:346-359` — El `except` ancho reintenta 3× cualquier error, incluso bugs propios y
`StudioAPIError` no transitorios. `process_video_to_creative` **no es idempotente** (sube +
crea creative), así que reintentar puede duplicar creatives en Studio. **Fix:** reintentar solo
`requests.exceptions.RequestException`; el resto → error inmediato sin retry.

### A7 — `localStorage` sin guard en el top del script → app muerta en modo privado
`app/templates/index.html:1147` — `localStorage.getItem(...)` en la resolución inicial de
`currentLang`. En Safari Private / storage bloqueado por política, lanza y aborta **todo** el
bloque `<script>` → la app queda sin interactividad (ni drop zone, ni upload, ni toggle).
**Fix:** helpers `safeGet`/`safeSet` con try/catch.

### A8 — Fallback `STUDIO_JWT_COOKIE` por env compartido entre todos los usuarios
`app/app.py:55-57` — Viola la regla dura "JWT por usuario". Si la env está en prod, todos (y
los callers sin auth de C1) suben bajo un único Studio. **Fix:** habilitar el fallback solo en
dev (`if app.debug` / flag explícita), nunca en Cloud Run.

---

## 🟡 MEDIOS

### M1 — Endpoints de lectura sin auth ni filtro por dueño
`app/app.py:145-158, 218-264` — `/api/jira-detect` (oracle de enumeración de tickets SDS con el
token del servidor), `/api/history` y `/api/job/<id>` sin sesión ni filtro `user_email`:
cualquiera ve los tickets/emails de todos. **Fix:** `@login_required` + filtro por `user_email`.

### M2 — SQLite sin WAL/timeout, conexiones no cerradas, sin índice
`app/database.py:18-21` — `with get_db_connection() as conn:` commitea pero **no cierra** la
conexión (a diferencia de archivos) → fuga de conexión en cada llamada (1/s por stream SSE). Sin
WAL → `database is locked` bajo carga. Sin índice en `job_items.job_id`. **Fix:**
`with closing(...)`, `PRAGMA journal_mode=WAL`, `timeout=30`, `CREATE INDEX idx_job_items_job_id`.

### M3 — Contador de progreso cuenta "processing" como completado
`app/templates/index.html:1726-1728` y `app/app.py:374` — La UI muestra "N/N completados"
mientras Studio aún procesa (30-60s). `all_done` también marca el job `done` con items en
`processing`. **Fix:** contar solo `done`/`error` como terminal.

### M4 — Jobs zombie "running" tras reinicio (sin barrido de recuperación)
`app/app.py:191`, `database.py` — Si el proceso muere mid-job (scale-to-zero, OOM, deploy), el
job queda `running, done=0` para siempre y el SSE polea 300s en vano. **Fix:** en `init_db()`,
`UPDATE jobs SET status='interrupted', done=1 WHERE done=0`.

### M5 — El reloader de debug mata jobs en vuelo
`app/app.py:415` — Con debug on (default), editar código recarga y mata los daemon threads
mid-upload sin cleanup. **Fix:** `use_reloader=False` y/o el default seguro de C3.

### M6 — `/api/set-jwt` reporta errores de red como "JWT inválido" (400)
`app/app.py:120,141-142` — Un `ConnectionError` durante `ping()` se reporta como auth error,
diciéndole al usuario que su JWT está mal cuando Studio está caído. **Fix:** separar
`RequestException` → 502.

### M7 — Sweep de i18n incompleto
`app/templates/index.html` — Strings visibles fuera del sistema i18n: "Google SSO" (líneas 939,
1553-1554, además no se traduce al cambiar idioma), headers `<th>Ticket` (1078) y `<th>Videos`
(1081), y el seed "0/0 completados" (1058, se ve en EN antes del primer update). **Fix:** rutear
por `data-i18n`/`t()` y agregar claves a ambos diccionarios.

---

## 🟢 BAJOS (selección)

- **L1** `app/templates/index.html:255-258, 930-933` — Toggle de idioma sin `aria-pressed`,
  estado solo por color, y blanco sobre coral ~2.3:1 (falla WCAG AA). Fix: `aria-pressed`,
  `role="group"`, texto negro sobre coral (~9:1).
- **L2** `app/templates/index.html:962` — JWT en `type="text"` sin `autocomplete="off"` (~30
  días de vida). Fix: `type="password"`, `autocomplete="off"`, limpiar tras vincular.
- **L3** `app/jira_client.py:55,109` — Loguea `r.text[:300]` (cuerpo de Jira). Fix: solo status
  + ticket_key.
- **L4** `app/app.py:307-309` — `import time/random/requests` dentro del loop de retry. Fix:
  mover al top.
- **L5** `app/database.py:129` — `get_history` devuelve `done` como int; `get_job` como bool.
  Contrato inconsistente. Fix: normalizar a bool.
- **L6** `app/templates/index.html:1032-1036` — Drop zone es `<div onclick>` sin `tabindex`/
  `role`/keydown → no accesible por teclado. Fix: `tabindex="0"`, `role="button"`, handler
  Enter/Space.
- **L7** `app/templates/index.html:1738` — `href` de preview escapado pero sin validar esquema
  (`javascript:` sobreviviría). Fix: validar `^https?://`.
- **L8** `app/templates/index.html:1114-1133` — Nombre/email personal hardcodeado en el modal
  SSO, visible para todos. Fix: render desde `/api/auth-status`.
- **L9** `app/templates/index.html:1380-1384` — `setLanguage` re-fetchea auth+history en cada
  toggle (2 round-trips + flicker). Fix: re-render desde cache.

---

## Plan de fixes sugerido

**Tier 1 — Quick wins seguros (sin decisiones de arquitectura):**
C3 (debug default), A3 (límites upload), A4 (cleanup/estado items), A6 (retry acotado),
A7 (localStorage guard), M2 (DB closing/WAL/índice), M3 (contador), M4 (sweep zombie),
M6 (error red), M7 (i18n), L1-L7 (a11y, password input, logs, imports, bool, scheme).

**Tier 2 — Hardening de config (bajo riesgo, leve cambio de comportamiento):**
C2 (secret fail-closed), A1 (cookie flags + CSRF), A8 (gate env JWT a dev), M1 (auth en lecturas).

**Tier 3 — Arquitectura (requiere decisión):**
C1 (Google OIDC real) — es el cambio grande; hoy el SSO es intencionalmente simulado.
