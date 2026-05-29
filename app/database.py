"""
Database persistence layer using SQLite for Studio Batch Uploader.
Stores jobs and their individual video items, providing a complete upload history.
"""
import sqlite3
import os
import threading
from contextlib import closing
from pathlib import Path
from datetime import datetime

DATABASE_PATH = Path(os.getenv("TMP_DIR", "./tmp")) / "jobs.db"
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Global thread lock to ensure consistent snapshots and thread safety
db_lock = threading.Lock()


def get_db_connection():
    # timeout amplio + WAL: el worker, el stream SSE y los requests comparten la DB
    # en threads; sin esto aparecen errores 'database is locked' bajo carga (M2).
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initializes the database schema if tables don't exist."""
    with db_lock:
        with closing(get_db_connection()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    ticket_key TEXT,
                    user_email TEXT,
                    created_at TEXT,
                    status TEXT,
                    done INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS job_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    filename TEXT,
                    path TEXT,
                    status TEXT,
                    url TEXT,
                    msg TEXT,
                    created_at TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_job_items_job_id ON job_items(job_id)"
            )
            # Reconciliar jobs huérfanos: si el proceso murió mid-job, sus threads no
            # sobreviven, así que cualquier done=0 al arrancar quedó interrumpido (M4).
            conn.execute(
                "UPDATE jobs SET status = 'interrupted', done = 1 WHERE done = 0"
            )
            conn.execute(
                "UPDATE job_items SET status = 'error', "
                "msg = 'Interrumpido: el servidor se reinició durante la subida.' "
                "WHERE status = 'queued' OR status LIKE 'uploading%'"
            )
            conn.commit()


def create_job(job_id: str, ticket_key: str, user_email: str, status: str = "pending"):
    """Inserts a new job record."""
    now = datetime.now().isoformat()
    with db_lock:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, ticket_key, user_email, created_at, status, done) VALUES (?, ?, ?, ?, ?, 0)",
                (job_id, ticket_key, user_email, now, status)
            )
            conn.commit()


def add_job_item(job_id: str, filename: str, path: str, status: str = "queued"):
    """Inserts a new video item under a job."""
    now = datetime.now().isoformat()
    with db_lock:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "INSERT INTO job_items (job_id, filename, path, status, url, msg, created_at) VALUES (?, ?, ?, ?, NULL, '', ?)",
                (job_id, filename, path, status, now)
            )
            conn.commit()


def update_job_status(job_id: str, status: str, done: bool = False):
    """Updates the global job status and done flag."""
    with db_lock:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, done = ? WHERE job_id = ?",
                (status, 1 if done else 0, job_id)
            )
            conn.commit()


def update_job_item(job_id: str, filename: str, status: str, url: str = None, msg: str = ""):
    """Updates the status, URL, or error message of a specific item."""
    with db_lock:
        with closing(get_db_connection()) as conn:
            conn.execute(
                "UPDATE job_items SET status = ?, url = COALESCE(?, url), msg = ? WHERE job_id = ? AND filename = ?",
                (status, url, msg, job_id, filename)
            )
            conn.commit()


def get_job(job_id: str) -> dict | None:
    """Retrieves a job and its associated items."""
    with db_lock:
        with closing(get_db_connection()) as conn:
            job_row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not job_row:
                return None

            items_rows = conn.execute("SELECT * FROM job_items WHERE job_id = ?", (job_id,)).fetchall()

            job_dict = dict(job_row)
            job_dict["done"] = bool(job_dict["done"])
            job_dict["items"] = [dict(item) for item in items_rows]
            return job_dict


def get_history(limit: int = 50, user_email: str | None = None) -> list[dict]:
    """Retrieves jobs and their completed stats for history display.

    If user_email is given, only that user's jobs are returned (per-user history, M1)."""
    where = "WHERE j.user_email = ?" if user_email else ""
    params = ([user_email, limit] if user_email else [limit])
    with db_lock:
        with closing(get_db_connection()) as conn:
            rows = conn.execute(f"""
                SELECT j.*,
                       (SELECT COUNT(*) FROM job_items WHERE job_id = j.job_id) as total_items,
                       (SELECT COUNT(*) FROM job_items WHERE job_id = j.job_id AND status = 'done') as success_items,
                       (SELECT COUNT(*) FROM job_items WHERE job_id = j.job_id AND status = 'error') as error_items
                FROM jobs j
                {where}
                ORDER BY j.created_at DESC
                LIMIT ?
            """, params).fetchall()
            history = []
            job_ids = [row["job_id"] for row in rows]

            # Traer los preview links (items 'done') de todos los jobs en UNA query y
            # agruparlos por job, para mostrarlos en el historial sin N+1.
            links_by_job = {}
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                link_rows = conn.execute(
                    f"SELECT job_id, filename, url FROM job_items "
                    f"WHERE status = 'done' AND url IS NOT NULL AND job_id IN ({placeholders})",
                    job_ids,
                ).fetchall()
                for lr in link_rows:
                    links_by_job.setdefault(lr["job_id"], []).append(
                        {"filename": lr["filename"], "url": lr["url"]}
                    )

            for row in rows:
                d = dict(row)
                d["done"] = bool(d["done"])  # contrato consistente con get_job (L5)
                d["links"] = links_by_job.get(d["job_id"], [])
                history.append(d)
            return history

