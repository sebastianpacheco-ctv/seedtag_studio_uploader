"""
Database persistence layer using SQLite for Studio Batch Uploader.
Stores jobs and their individual video items, providing a complete upload history.
"""
import sqlite3
import os
import threading
from pathlib import Path
from datetime import datetime

DATABASE_PATH = Path(os.getenv("TMP_DIR", "./tmp")) / "jobs.db"
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Global thread lock to ensure consistent snapshots and thread safety
db_lock = threading.Lock()


def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes the database schema if tables don't exist."""
    with db_lock:
        with get_db_connection() as conn:
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
            conn.commit()


def create_job(job_id: str, ticket_key: str, user_email: str, status: str = "pending"):
    """Inserts a new job record."""
    now = datetime.now().isoformat()
    with db_lock:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, ticket_key, user_email, created_at, status, done) VALUES (?, ?, ?, ?, ?, 0)",
                (job_id, ticket_key, user_email, now, status)
            )
            conn.commit()


def add_job_item(job_id: str, filename: str, path: str, status: str = "queued"):
    """Inserts a new video item under a job."""
    now = datetime.now().isoformat()
    with db_lock:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO job_items (job_id, filename, path, status, url, msg, created_at) VALUES (?, ?, ?, ?, NULL, '', ?)",
                (job_id, filename, path, status, now)
            )
            conn.commit()


def update_job_status(job_id: str, status: str, done: bool = False):
    """Updates the global job status and done flag."""
    with db_lock:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status = ?, done = ? WHERE job_id = ?",
                (status, 1 if done else 0, job_id)
            )
            conn.commit()


def update_job_item(job_id: str, filename: str, status: str, url: str = None, msg: str = ""):
    """Updates the status, URL, or error message of a specific item."""
    with db_lock:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE job_items SET status = ?, url = COALESCE(?, url), msg = ? WHERE job_id = ? AND filename = ?",
                (status, url, msg, job_id, filename)
            )
            conn.commit()


def get_job(job_id: str) -> dict | None:
    """Retrieves a job and its associated items."""
    with db_lock:
        with get_db_connection() as conn:
            job_row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if not job_row:
                return None

            items_rows = conn.execute("SELECT * FROM job_items WHERE job_id = ?", (job_id,)).fetchall()

            job_dict = dict(job_row)
            job_dict["done"] = bool(job_dict["done"])
            job_dict["items"] = [dict(item) for item in items_rows]
            return job_dict


def get_history(limit: int = 50) -> list[dict]:
    """Retrieves all jobs and their completed stats for history display."""
    with db_lock:
        with get_db_connection() as conn:
            rows = conn.execute("""
                SELECT j.*, 
                       (SELECT COUNT(*) FROM job_items WHERE job_id = j.job_id) as total_items,
                       (SELECT COUNT(*) FROM job_items WHERE job_id = j.job_id AND status = 'done') as success_items,
                       (SELECT COUNT(*) FROM job_items WHERE job_id = j.job_id AND status = 'error') as error_items
                FROM jobs j 
                ORDER BY j.created_at DESC 
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(row) for row in rows]

