# Studio Batch Uploader — instrucciones del proyecto

Web app interna (Flask) para subir varios videos a Studio Seedtag asociados a un
ticket y devolver los links de preview. Independiente del bot `csv-automation`.

## Reglas duras (NO negociables)
- **NUNCA borrar** nada de Jira ni de Studio Seedtag. Solo crear/adjuntar.
- Antes de tocar un ticket, **validar que sea del proyecto correcto** (ej. key
  empieza con `SDS-`). La tool acepta cualquier link que pegue el usuario.
- Credenciales (JWT de Studio, API token de Jira) **nunca** al git ni al
  frontend. Viven server-side, por sesión de usuario.
- `.env` fuera del control de versiones (ver `.gitignore`).

## Auth
- Studio: cookie `seedtag_jwt` (JWT ~30 días). Modelo elegido: **por usuario**.
  Resolver primero si hay token/OAuth por usuario; si no, JWT pegado por persona,
  guardado en la sesión server-side.
- Login a la app: SSO del equipo (Google Workspace).

## Convenciones de trabajo (heredadas de csv-automation)
- Antes de reiniciar / dar por bueno un cambio en un .py:
  `python3 -c "import ast; ast.parse(open('app/app.py').read()); print('AST OK')"`
- Cambios chicos y verificables, un paso a la vez, commit por paso.
- Identidad git: usar `git -c user.name="..." -c user.email="..."` si el entorno
  no la autodetecta.

## El core ya existe
`reference/studio_api.py` es el cliente real de Studio (autocontenido, solo
`requests`). NO reimplementar la integración con Studio: usar ese cliente.
Ver `reference/INTEGRATION.md` para el cómo. Punto de entrada:
`StudioAPIClient(...).process_video_to_creative(...)` → devuelve `preview_url`.

## Stack
Flask + requests. Frontend dark Seedtag (Instrument Sans/Serif, coral #FF6B7C).
Lote en background con progreso por archivo (no requests bloqueantes).
