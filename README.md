# Studio Batch Uploader

Aplicacion interna para subir videos CTV en lote a Studio Seedtag, asociarlos a
un ticket Jira `SDS-XXXX` y devolver previews listas para revisar.

## Que incluye

- Backend Flask con jobs en segundo plano y persistencia SQLite en `tmp/jobs.db`.
- Cliente real de Studio via GraphQL reutilizado desde `reference/studio_api.py`.
- Integracion Jira tolerante a fallos para leer pais/categoria y comentar el reporte final.
- UI web con drag and drop, estado en vivo via SSE e historial de subidas.
- Dockerfile y configuracion de Firebase Hosting para enrutar a Cloud Run.

## Estructura

```text
app/
  app.py              Backend Flask, endpoints y worker de subida
  database.py         Persistencia local SQLite
  jira_client.py      Cliente Jira REST API v2
  app_test.py         Tests unitarios
  templates/index.html
reference/
  studio_api.py       Cliente Studio de produccion
  INTEGRATION.md      Notas de integracion
```

## Arranque local

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app/app.py
```

La app queda en `http://127.0.0.1:8088` por defecto.

## Variables clave

- `FLASK_SECRET_KEY`: secreto de sesion Flask.
- `STUDIO_JWT_COOKIE`: JWT de Studio solo para desarrollo local. En uso normal,
  cada usuario lo pega desde la UI y queda en su sesion.
- `JIRA_EMAIL` y `JIRA_API_TOKEN`: habilitan lectura/comentarios en Jira.
- `JIRA_PROJECT_KEY`: por defecto `SDS`; el backend rechaza otros proyectos.
- `TMP_DIR`: carpeta de temporales y base SQLite.

## Tests

```bash
venv/bin/python -m unittest discover -s app -p "*_test.py"
```

## Despliegue

El repo ya trae `Dockerfile`, `firebase.json` y notas de despliegue en
`FIREBASE_NOTES.md`.

Pendiente operativo:

- Activar billing en el proyecto Firebase/GCP `decoded-theme-461808-d3`.
- Desplegar Cloud Run como `seedtag-studio-uploader` en `us-central1`.
- Conectar Firebase Hosting a Cloud Run.
- Opcional: integrar Firebase Auth real para Google Workspace SSO.
