"""
Studio Batch Uploader — Backend Flask Application.
Manages Google SSO simulation, Studio JWT verification, background batch uploads,
SQLite history persistence, and Jira issue automation.
"""
import os
import re
import sys
import uuid
import threading
from pathlib import Path

from flask import Flask, request, jsonify, render_template, session

# Add reference/ directory to python path to import the real Studio client.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "reference"))
from studio_api import (  # noqa: E402
    StudioAPIClient,
    StudioVideoNotReadyError,
    StudioJWTExpiredError,
)

# Import our custom database and Jira client layers
import database
from jira_client import JiraClient

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-secret-key-12345")

TMP = Path(os.getenv("TMP_DIR", "./tmp"))
TMP.mkdir(parents=True, exist_ok=True)
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "SDS")

# Initialize SQLite database schema
database.init_db()


# ── Helpers ──────────────────────────────────────────────────────────────────
def ticket_key_from_link(link: str) -> str | None:
    """Extrae la key (ej. SDS-1234) de un link o texto de ticket y valida el
    proyecto. Devuelve None si no es del proyecto permitido."""
    m = re.search(r"\b([A-Z][A-Z0-9]+)-(\d+)\b", link or "")
    if not m:
        return None
    key = m.group(0)
    if not key.startswith(PROJECT_KEY + "-"):
        return None  # regla de seguridad: solo el proyecto permitido
    return key


def get_user_studio_jwt() -> str | None:
    """JWT de Studio del usuario actual. De la sesión o del env (para desarrollo)."""
    return session.get("studio_jwt") or os.getenv("STUDIO_JWT_COOKIE")


# ── Rutas ──────────────────────────────────────────────────────────────────--
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/login")
def login():
    """Simula Google Workspace SSO para el equipo."""
    session["user_email"] = "sebastian.pacheco@seedtag.com"
    session["user_name"] = "Sebastian Pacheco"
    return jsonify({
        "ok": True,
        "email": session["user_email"],
        "name": session["user_name"]
    })


@app.post("/api/logout")
def logout():
    """Limpia la sesión de SSO y JWT."""
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/auth-status")
def auth_status():
    """Retorna el estado de autenticación actual (SSO y Studio JWT)."""
    jwt = get_user_studio_jwt()
    # Si hay JWT en sesión, intentamos verificarlo en background o simplemente retornamos los datos guardados
    return jsonify({
        "sso_user": session.get("user_email"),
        "sso_name": session.get("user_name"),
        "studio_user": session.get("studio_user_email"),
        "studio_name": session.get("studio_user_name"),
        "has_jwt": bool(jwt)
    })


@app.post("/api/set-jwt")
def set_jwt():
    """Valida el JWT provisto contra Studio y lo guarda en la sesión del usuario."""
    jwt = (request.get_json(force=True, silent=True) or {}).get("jwt", "").strip()
    if not jwt:
        return jsonify({"ok": False, "error": "El JWT no puede estar vacío"}), 400

    try:
        # Spike de Auth: Instanciar y verificar que el JWT es válido y no está expirado
        client = StudioAPIClient(jwt_cookie=jwt)
        user_info = client.ping()  # Lanza excepción si no es válido

        # Guardar en sesión
        session["studio_jwt"] = jwt
        session["studio_user_email"] = user_info.get("email")
        session["studio_user_name"] = f"{user_info.get('name', '')} {user_info.get('surname', '')}".strip()

        return jsonify({
            "ok": True,
            "email": session["studio_user_email"],
            "name": session["studio_user_name"]
        })
    except StudioJWTExpiredError as e:
        return jsonify({"ok": False, "error": f"El JWT ingresado está expirado: {e}"}), 401
    except Exception as e:
        return jsonify({"ok": False, "error": f"Error de autenticación con Studio: {str(e)}"}), 400


@app.get("/api/jira-detect/<ticket_key>")
def jira_detect(ticket_key):
    """Consulta Jira en segundo plano para obtener Operator Entity e Industry."""
    key = ticket_key_from_link(ticket_key)
    if not key:
        return jsonify({"ok": False, "error": "Clave de ticket inválida"}), 400

    jira = JiraClient()
    fields = jira.get_issue_fields(key)
    return jsonify({
        "ok": True,
        "country": fields.get("country"),
        "category": fields.get("category")
    })


@app.post("/api/upload")
def upload():
    """Recibe N archivos + ticket link, arranca un job en background con SQLite persistence."""
    jwt = get_user_studio_jwt()
    if not jwt:
        return jsonify({"ok": False, "error": "No hay un JWT de Studio válido y activo"}), 401

    # Validaciones de Jira
    link = request.form.get("ticket_link", "")
    ticket_key = ticket_key_from_link(link)
    if not ticket_key:
        return jsonify({"ok": False,
                        "error": f"Link de ticket inválido o fuera del proyecto {PROJECT_KEY} (SDS-XXXX)"}), 400

    files = request.files.getlist("videos")
    if not files or len(files) == 0 or (len(files) == 1 and files[0].filename == ''):
        return jsonify({"ok": False, "error": "No se seleccionaron archivos de video"}), 400

    # Obtener parámetros de País y Categoría
    country = request.form.get("country", "auto")
    category = request.form.get("category", "auto")

    # Identificación del usuario de SSO o Studio
    user_email = session.get("user_email") or session.get("studio_user_email") or "usuario@seedtag.com"

    job_id = uuid.uuid4().hex[:12]
    job_dir = TMP / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Crear el Job en la Base de Datos SQLite
    database.create_job(job_id, ticket_key, user_email, status="running")

    # Guardar cada archivo y agregarlo a job_items
    for f in files:
        dest = job_dir / f.filename
        f.save(str(dest))
        database.add_job_item(job_id, f.filename, str(dest), status="queued")

    # Arrancar hilo worker en background
    t = threading.Thread(
        target=_run_job,
        args=(job_id, jwt, ticket_key, country, category, user_email),
        daemon=True
    )
    t.start()

    return jsonify({
        "ok": True,
        "job_id": job_id,
        "ticket": ticket_key,
        "count": len(files)
    })


@app.get("/api/job/<job_id>")
def job_status(job_id):
    """Consulta el estado del job y sus items desde SQLite."""
    job = database.get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Job no encontrado"}), 404
    return jsonify({"ok": True, **job})


@app.get("/api/history")
def history():
    """Retorna la lista de uploads recientes desde SQLite."""
    rows = database.get_history(limit=50)
    return jsonify({"ok": True, "history": rows})


# ── Worker ─────────────────────────────────────────────────────────────────--
def _run_job(job_id: str, jwt: str, ticket_key: str, country: str, category: str, user_email: str):
    """
    Worker que se ejecuta en segundo plano.
    Procesa secuencialmente cada video subiendo a Studio, esperando a que se procese,
    creando el creative y actualizando SQLite. Al terminar, agrega un comentario en Jira.
    """
    job = database.get_job(job_id)
    if not job:
        return

    # Inicializar clientes
    studio = StudioAPIClient(jwt_cookie=jwt)
    jira = JiraClient()

    # Si se seleccionó "Auto-detectar", consultar Jira antes de procesar
    detected_country = None
    detected_category = None
    if country == "auto" or category == "auto":
        fields = jira.get_issue_fields(ticket_key)
        detected_country = fields.get("country")
        detected_category = fields.get("category")

    actual_country = detected_country if country == "auto" else country
    actual_category = detected_category if category == "auto" else category

    # Mapear País y Categoría
    mapped_country = StudioAPIClient.map_country(actual_country) if actual_country else None
    mapped_category = StudioAPIClient.map_category(actual_category) if actual_category else None

    # Procesar cada archivo
    for item in job["items"]:
        filename = item["filename"]
        filepath = Path(item["path"])

        database.update_job_item(job_id, filename, status="uploading")

        try:
            # Flujo end-to-end de Studio
            sres = studio.process_video_to_creative(
                file_path=filepath,
                ticket_title=filepath.stem,
                country=mapped_country,
                category=mapped_category,
                initial_wait=10,  # 10s wait antes del primer check
                retry_wait=10,   # 10s entre reintentos
                max_retries=15    # Total ~160s máx (muy razonable para CTV)
            )

            preview_url = sres["preview_url"]
            database.update_job_item(job_id, filename, status="done", url=preview_url)

        except StudioVideoNotReadyError as nre:
            database.update_job_item(
                job_id, filename, status="processing",
                msg=f"Sigue procesando en Studio (video_id={nre.video_id})."
            )
        except StudioJWTExpiredError:
            database.update_job_item(
                job_id, filename, status="error",
                msg="JWT de Studio expirado. Por favor, renuévalo en la interfaz."
            )
        except Exception as e:
            database.update_job_item(
                job_id, filename, status="error",
                msg=str(e)
            )

        # Limpiar archivo temporal local una vez subido/fallado
        try:
            if filepath.exists():
                filepath.unlink()
        except Exception as err:
            print(f"No se pudo eliminar el archivo temporal {filepath}: {err}")

    # Verificar si hubo al menos un éxito para el reporte de Jira
    refreshed_job = database.get_job(job_id)
    any_done = any(it["status"] == "done" for it in refreshed_job["items"])
    all_done = all(it["status"] in ("done", "processing") for it in refreshed_job["items"])

    job_status_str = "done" if all_done else "error"
    database.update_job_status(job_id, status=job_status_str, done=True)

    # Limpiar directorio de job si está vacío
    try:
        job_dir = TMP / job_id
        if job_dir.exists() and not any(job_dir.iterdir()):
            job_dir.rmdir()
    except Exception:
        pass

    # Postear comentario en Jira si hay al menos un preview generado
    if any_done and jira.enabled:
        comment_lines = []
        for it in refreshed_job["items"]:
            if it["status"] == "done":
                comment_lines.append(f"| {it['filename']} | *COMPLETADO* | [Ver Vista Previa|{it['url']}] |")
            elif it["status"] == "processing":
                comment_lines.append(f"| {it['filename']} | _PROCESANDO_ | {it['msg']} |")
            else:
                comment_lines.append(f"| {it['filename']} | {{color:red}}ERROR{{color}} | {it['msg']} |")

        comment_table = "\n".join(comment_lines)
        comment_text = (
            f"h3. Studio Batch Uploader Report 🚀\n\n"
            f"Se ha completado la subida de videos en lote para este ticket.\n\n"
            f"|| Archivo || Estado || Vista Previa / Detalle ||\n"
            f"{comment_table}\n\n"
            f"_Subido por: {user_email}_"
        )
        jira.add_comment(ticket_key, comment_text)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    # Escuchar en 0.0.0.0 para contenedores y adaptarse al puerto dinámico de Cloud Run (PORT)
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", os.getenv("APP_PORT", "8088")))
    debug_mode = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(host=host, port=port, debug=debug_mode)
