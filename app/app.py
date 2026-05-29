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
import json
import time
import random
import requests
from functools import wraps
from pathlib import Path

from flask import Flask, request, jsonify, render_template, session, Response, redirect, url_for
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth

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

# ¿Estamos en modo dev? Se usa para decidir defaults seguros vs. permisivos.
IS_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"

# Secret key: fail-closed en producción. Nunca un default público (C2).
_secret = os.getenv("FLASK_SECRET_KEY")
if not _secret:
    if IS_DEBUG:
        # Solo para desarrollo local; las sesiones no necesitan ser seguras acá.
        _secret = "dev-only-insecure-key-do-not-use-in-prod"
        print("WARNING: FLASK_SECRET_KEY no seteada — usando clave de DEV insegura.")
    else:
        raise RuntimeError(
            "FLASK_SECRET_KEY es obligatoria en producción. "
            "Generá una con `python -c \"import secrets; print(secrets.token_hex(32))\"`."
        )
app.secret_key = _secret

# Endurecer la cookie de sesión (lleva el JWT de Studio server-side) (A1).
# Secure por defecto; en dev local sobre http hay que setear SESSION_COOKIE_SECURE=False.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("SESSION_COOKIE_SECURE", "True").lower() == "true",
)

# ── Auth de la app: Google OIDC real (C1) ──────────────────────────────────────
# Solo dominios de este workspace pueden entrar.
ALLOWED_EMAIL_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "seedtag.com")
# OIDC se activa solo si hay credenciales OAuth. Si no, cae al login simulado (dev).
OIDC_ENABLED = bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))

oauth = OAuth(app)
if OIDC_ENABLED:
    oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "hd": ALLOWED_EMAIL_DOMAIN},
    )
elif not IS_DEBUG:
    # En producción sin OIDC, el login simulado dejaría entrar a cualquiera (C1).
    print("WARNING: OIDC no configurado en producción — el login simulado está deshabilitado.")

TMP = Path(os.getenv("TMP_DIR", "./tmp"))
TMP.mkdir(parents=True, exist_ok=True)
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "SDS")

# Límites de subida: tamaño total del request y extensiones permitidas (A3).
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "300"))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".webm"}
MAX_FILES_PER_BATCH = int(os.getenv("MAX_FILES_PER_BATCH", "50"))

# Initialize SQLite database schema
database.init_db()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.before_request
def csrf_protect():
    """CSRF para una API basada en fetch: exigir el header X-Requested-With en métodos
    que cambian estado. Un sitio atacante no puede setear ese header en un POST cross-site
    (ni por <form> ni por fetch sin que falle el preflight CORS). Combinado con
    SameSite=Lax, bloquea CSRF sin tokens (A1)."""
    if request.method in SAFE_METHODS:
        return
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return jsonify({"ok": False, "error": "Solicitud rechazada por protección CSRF."}), 403


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
    """JWT de Studio del usuario actual, siempre desde su sesión (modelo por-usuario).

    El fallback a la env STUDIO_JWT_COOKIE solo se permite si ALLOW_ENV_STUDIO_JWT=True
    (desarrollo local); en producción compartir un JWT entre usuarios viola la regla
    dura del proyecto (A8)."""
    jwt = session.get("studio_jwt")
    if jwt:
        return jwt
    if os.getenv("ALLOW_ENV_STUDIO_JWT", "False").lower() == "true":
        return os.getenv("STUDIO_JWT_COOKIE")
    return None


def safe_upload_filename(filename: str, existing_names: set[str] | None = None) -> str:
    """Return a safe, unique filename for storing an uploaded video in a job dir."""
    existing_names = existing_names if existing_names is not None else set()
    safe_name = secure_filename(filename or "") or "video"
    path = Path(safe_name)
    stem = path.stem or "video"
    suffix = path.suffix

    candidate = safe_name
    counter = 2
    while candidate in existing_names:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1

    existing_names.add(candidate)
    return candidate


def login_required(view):
    """Rechaza con 401 si no hay una sesión de usuario establecida (M1)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_email"):
            return jsonify({"ok": False, "error": "No autenticado"}), 401
        return view(*args, **kwargs)
    return wrapper


def _cleanup_job_dir(job_id: str) -> None:
    """Borra el directorio temporal de un job (best-effort)."""
    job_dir = TMP / job_id
    try:
        if job_dir.exists():
            for child in job_dir.iterdir():
                try:
                    child.unlink()
                except OSError:
                    pass
            job_dir.rmdir()
    except OSError:
        pass


# ── Rutas ──────────────────────────────────────────────────────────────────--
@app.errorhandler(413)
def too_large(_e):
    return jsonify({"ok": False,
                    "error": f"El lote supera el máximo de {MAX_UPLOAD_MB} MB"}), 413



@app.get("/")
def index():
    return render_template("index.html")


# ── Auth de la app ─────────────────────────────────────────────────────────--
@app.get("/auth/login")
def auth_login():
    """Inicia el flujo OIDC de Google (C1)."""
    if not OIDC_ENABLED:
        return jsonify({"ok": False, "error": "OIDC no configurado en este entorno"}), 404
    redirect_uri = os.getenv("OAUTH_REDIRECT_URI") or url_for("auth_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.get("/auth/callback")
def auth_callback():
    """Callback de Google: valida el token y exige el dominio del workspace (C1)."""
    if not OIDC_ENABLED:
        return jsonify({"ok": False, "error": "OIDC no configurado en este entorno"}), 404
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        return redirect("/?auth_error=1")

    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    verified = userinfo.get("email_verified", False)

    # Solo correos verificados del dominio permitido.
    if not verified or not email.endswith("@" + ALLOWED_EMAIL_DOMAIN.lower()):
        session.clear()
        return redirect("/?auth_error=domain")

    session["user_email"] = email
    session["user_name"] = userinfo.get("name") or email
    return redirect("/")


@app.post("/api/login")
def login():
    """Login simulado para desarrollo. Se deshabilita si OIDC está activo, para no
    dejar entrar a cualquiera saltándose Google (C1)."""
    if OIDC_ENABLED:
        return jsonify({"ok": False, "error": "Usá el inicio de sesión con Google."}), 403
    if not IS_DEBUG:
        return jsonify({"ok": False, "error": "Login no disponible: configurá OIDC."}), 403
    session["user_email"] = os.getenv("DEV_SSO_EMAIL", "sebastian.pacheco@seedtag.com")
    session["user_name"] = os.getenv("DEV_SSO_NAME", "Sebastian Pacheco")
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
    return jsonify({
        "sso_user": session.get("user_email"),
        "sso_name": session.get("user_name"),
        "studio_user": session.get("studio_user_email"),
        "studio_name": session.get("studio_user_name"),
        "has_jwt": bool(jwt),
        "oidc_enabled": OIDC_ENABLED,
        "allowed_domain": ALLOWED_EMAIL_DOMAIN
    })


@app.post("/api/set-jwt")
@login_required
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
    except StudioJWTExpiredError:
        return jsonify({"ok": False, "error": "El JWT ingresado está expirado. Renuévalo en Studio."}), 401
    except requests.exceptions.RequestException:
        # Studio inalcanzable: no es culpa del JWT (M6).
        return jsonify({"ok": False, "error": "Studio no está disponible en este momento. Intentá de nuevo."}), 502
    except Exception:
        # No reflejar el detalle de la excepción al cliente (A2).
        return jsonify({"ok": False, "error": "No se pudo verificar el JWT con Studio."}), 400


@app.get("/api/jira-detect/<ticket_key>")
@login_required
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
@login_required
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
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"ok": False, "error": "No se seleccionaron archivos de video"}), 400

    if len(files) > MAX_FILES_PER_BATCH:
        return jsonify({"ok": False,
                        "error": f"Demasiados archivos en el lote (máx {MAX_FILES_PER_BATCH})"}), 400

    # Validar extensión server-side (el accept del HTML es solo cosmético).
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTS:
            allowed = ", ".join(sorted(ALLOWED_VIDEO_EXTS))
            return jsonify({"ok": False,
                            "error": f"Formato no admitido en '{f.filename}'. Permitidos: {allowed}"}), 400

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

    # Guardar cada archivo y agregarlo a job_items con nombres seguros y únicos.
    # Si algo falla al guardar, limpiar el directorio para no dejar temp files huérfanos.
    try:
        used_filenames = set()
        for f in files:
            filename = safe_upload_filename(f.filename, used_filenames)
            dest = job_dir / filename
            f.save(str(dest))
            database.add_job_item(job_id, filename, str(dest), status="queued")
    except Exception:
        _cleanup_job_dir(job_id)
        database.update_job_status(job_id, status="error", done=True)
        raise

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
@login_required
def job_status(job_id):
    """Consulta el estado del job y sus items desde SQLite."""
    job = database.get_job(job_id)
    # 404 también si no es del usuario actual, para no filtrar existencia (M1).
    if not job or job.get("user_email") != session.get("user_email"):
        return jsonify({"ok": False, "error": "Job no encontrado"}), 404
    return jsonify({"ok": True, **job})


@app.get("/api/job/<job_id>/stream")
@login_required
def job_status_stream(job_id):
    """Yields SSE updates in real-time when SQLite database state changes."""
    # Verificar pertenencia antes de abrir el stream (M1).
    viewer = session.get("user_email")
    initial = database.get_job(job_id)
    if not initial or initial.get("user_email") != viewer:
        return jsonify({"ok": False, "error": "Job no encontrado"}), 404

    def event_generator():
        last_state = None
        # Max duration to prevent hanging connection indefinitely in dev / cloud servers
        max_duration = 300  
        start_time = time.time()
        
        while time.time() - start_time < max_duration:
            job = database.get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'ok': False, 'error': 'Job not found'})}\n\n"
                break
            
            # Form standard state signature to compare
            current_state = {
                "status": job["status"],
                "done": job["done"],
                "items": [{"filename": it["filename"], "status": it["status"], "url": it["url"], "msg": it["msg"]} for it in job["items"]]
            }
            
            if current_state != last_state:
                last_state = current_state
                yield f"data: {json.dumps({'ok': True, **job})}\n\n"
                
            if job["done"]:
                break
                
            time.sleep(1)
            
    return Response(event_generator(), mimetype="text/event-stream")


@app.get("/api/history")
@login_required
def history():
    """Retorna el historial de uploads del usuario actual desde SQLite (M1)."""
    rows = database.get_history(limit=50, user_email=session.get("user_email"))
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

        max_attempts = 3
        jwt_expired = False

        for attempt in range(1, max_attempts + 1):
            status_text = f"uploading [Attempt {attempt}/{max_attempts}]"
            database.update_job_item(job_id, filename, status=status_text)

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
                break

            except StudioJWTExpiredError:
                database.update_job_item(
                    job_id, filename, status="error",
                    msg="JWT de Studio expirado. Por favor, renuévalo en la interfaz."
                )
                jwt_expired = True
                break

            except StudioVideoNotReadyError as nre:
                database.update_job_item(
                    job_id, filename, status="processing",
                    msg=f"Sigue procesando en Studio (video_id={nre.video_id})."
                )
                break

            except requests.exceptions.RequestException as e:
                # Solo los fallos de red son transitorios y seguros de reintentar.
                if attempt < max_attempts:
                    base_delay = 2.0
                    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0.5, 1.5)
                    database.update_job_item(
                        job_id, filename, status=status_text,
                        msg=f"Error de red. Reintentando en {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    print(f"[job {job_id}] {filename}: red agotó reintentos: {e}")
                    database.update_job_item(
                        job_id, filename, status="error",
                        msg="Error de red al subir a Studio tras varios intentos."
                    )

            except Exception as e:
                # process_video_to_creative NO es idempotente (sube + crea creative):
                # reintentar un error no-transitorio podría duplicar creatives en Studio.
                # Registrar el detalle server-side y cortar con un mensaje genérico (A6/A2).
                print(f"[job {job_id}] {filename}: error no recuperable: {e!r}")
                database.update_job_item(
                    job_id, filename, status="error",
                    msg="Error al procesar el video en Studio."
                )
                break

        if jwt_expired:
            # Marcar los items aún en cola como error y limpiar sus temp files (A4).
            current = database.get_job(job_id)
            if current:
                for pending in current["items"]:
                    if pending["status"] == "queued":
                        database.update_job_item(
                            job_id, pending["filename"], status="error",
                            msg="No procesado: el JWT de Studio expiró durante el lote."
                        )
                        try:
                            Path(pending["path"]).unlink(missing_ok=True)
                        except OSError:
                            pass
            break

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
    debug_mode = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    app.run(host=host, port=port, debug=debug_mode)
