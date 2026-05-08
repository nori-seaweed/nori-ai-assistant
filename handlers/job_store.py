import os
import json
import sqlite3
import time
import uuid
from typing import Optional

# Renderの永続ディスクが/var/dataにマウントされる想定。なければ/tmp。
DB_PATH = os.getenv("JOB_DB_PATH", "/tmp/nori_jobs.db")

STAGES = ("lyrics", "music", "video", "youtube", "done")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                theme TEXT,
                lyrics TEXT,
                style TEXT,
                title TEXT,
                description TEXT,
                suno_url TEXT,
                audio_url TEXT,
                audio_path TEXT,
                thumbnail_path TEXT,
                video_path TEXT,
                youtube_url TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, updated_at DESC)")


def create_job(user_id: str, theme: str) -> dict:
    job_id = uuid.uuid4().hex[:8]
    now = int(time.time())
    with _conn() as c:
        c.execute(
            "INSERT INTO jobs (id, user_id, stage, theme, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, user_id, "lyrics", theme, now, now),
        )
    return get_job(job_id)


def get_job(job_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def get_latest_job(user_id: str) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM jobs WHERE user_id = ? AND stage != 'done' ORDER BY updated_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def update_job(job_id: str, **fields) -> dict:
    if not fields:
        return get_job(job_id)
    fields["updated_at"] = int(time.time())
    keys = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with _conn() as c:
        c.execute(f"UPDATE jobs SET {keys} WHERE id = ?", values)
    return get_job(job_id)
