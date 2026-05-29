# Kickoff — Studio Batch Uploader

Web app interna para subir varios videos a Studio Seedtag de una, asociados a un
ticket, devolviendo los links de preview. Proyecto **nuevo e independiente** del
bot de la cola 1597 (`csv-automation`).

---

## Qué hace (scope acotado)

El usuario:
1. Arrastra varios videos (caso típico: 10–15 muy similares, CTV).
2. Pega el link de un ticket.
3. La app, **por cada archivo**: sube a Studio → crea el creative → obtiene el
   link de preview → (opcional) lo adjunta al ticket.
4. Devuelve la lista de links.

**Lo que NO hace** (a propósito, para no recrear el bot grande):
- No parsea el form de Jira, no hace routing CTV/OW.
- No confirma por Slack.
- No procesa la cola 1597.
- Es solo *subir + crear creative + devolver link*.

---

## Arquitectura recomendada

- **Backend:** Flask (mismo stack que el dashboard de `csv-automation` → menos
  fricción si después se integran).
- **Frontend:** página única, drag&drop de archivos + campo para el link del
  ticket. Estilo dark Seedtag (Instrument Sans/Serif + coral `#FF6B7C`).
- **Job por lote:** son 10–15 videos y cada upload tarda ~30s+. NO hagas un
  request bloqueante. Procesá en background (thread/cola) con progreso por
  archivo: ⏳ subiendo → ✓ link / ✗ error. El front hace polling de estado.
- **Historial:** registro de lo subido (quién, cuándo, ticket, links) →
  reemplaza la idea de "carpeta de ya subidos" sin mover archivos físicos.

---

## El punto difícil: sesión de Studio POR USUARIO

Decisión tomada: atribución real por persona. Es la parte de **mayor riesgo**,
resolvela PRIMERO (spike) antes de construir lo demás.

Cómo funciona la auth de Studio hoy (ver `reference/studio_api.py`):
- Studio usa una cookie `seedtag_jwt` (JWT con expiry ~30 días).
- El JWT se saca a mano del navegador (DevTools → Application → Cookies →
  `seedtag_jwt`) y se pasa al cliente.

Opciones para "por usuario", de más simple a más limpia:
1. **(v1 pragmática)** Cada usuario pega su propio JWT una vez. La app lo guarda
   en la sesión del usuario (server-side, nunca en el front) y avisa cuándo
   vence. Reusás tal cual el mecanismo de `StudioAPIClient(jwt_cookie=...)`.
2. **(ideal)** Si Studio expone API tokens u OAuth por usuario → sin DevTools,
   sin expiración manual. **Verificá esto en el spike**, cambia todo el diseño.

> Login a la web app: usá el SSO del equipo (Google Workspace) para identificar
> a la persona. La credencial de Studio es aparte de ese login.

---

## Reglas de seguridad (heredadas + nuevas)

- **JAMÁS borrar** nada de Jira ni de Studio. Solo crear/adjuntar.
- A diferencia del bot viejo (que solo mira la cola 1597), esta tool acepta
  **cualquier link de ticket** → **validá que el ticket sea del proyecto
  correcto (ej. `SDS-*`)** antes de tocar nada.
- `.env` / JWTs / credenciales nunca al git. El JWT vive server-side por sesión.

---

## Orden de construcción sugerido

1. **Spike de auth de Studio** — ¿token/OAuth por usuario o JWT pegado?
   (Bloquea todo lo demás.)
2. Probar `reference/studio_api.py` con un JWT real: subir 1 video y obtener el
   `preview_url`. (Ver `reference/INTEGRATION.md`.)
3. Adjuntar al ticket (con validación de proyecto SDS).
4. Web app: login + form de upload de **un** archivo.
5. Lote: varios archivos con progreso en background.
6. Historial + manejo de errores por archivo.

---

## Preguntas a resolver al arrancar

- ¿Studio tiene API token / OAuth por usuario, o seguimos con JWT pegado?
- ¿Dónde se hostea? (Mac/servidor interno vs. cloud.)
- ¿Adjuntar al ticket es obligatorio u opcional (a veces solo quieren el link)?
- ¿Qué country/category default usar? (`process_video_to_creative` los acepta;
  ver mapeos `COUNTRY_MAP`/category en `studio_api.py`.)
