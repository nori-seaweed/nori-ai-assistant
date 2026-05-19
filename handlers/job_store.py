import os
import re
import time
import uuid
from typing import Optional


def _resolve_db_url(url: str) -> str:
    """Supabaseの直接接続URLをIPv4対応プーラーURLに変換する。
    RenderフリープランはIPv6非対応のため、
    db.PROJECT.supabase.co → *.pooler.supabase.com (Transaction Pooler) に切替える。

    Supabase API から取得した正確な接続設定:
      host: aws-1-ap-northeast-1.pooler.supabase.com
      port: 6543 (Transaction Pooler)
      user: postgres.<project_ref>
    """
    m = re.match(
        r"postgresql://postgres:(.+)@db\.([^.]+)\.supabase\.co:5432/(.+)", url
    )
    if m:
        password, project_ref, db = m.groups()
        # SUPABASE_POOLER_HOST を優先。未設定の場合は API 取得済みの既知値を使用
        pooler = os.getenv(
            "SUPABASE_POOLER_HOST",
            "aws-1-ap-northeast-1.pooler.supabase.com",
        )
        port = os.getenv("SUPABASE_POOLER_PORT", "6543")
        converted = (
            f"postgresql://postgres.{project_ref}:{password}"
            f"@{pooler}:{port}/{db}?sslmode=require"
        )
        print(f"[job_store] Supabase直接URLをプーラーURLへ変換: {pooler}:{port}")
        return converted
    return url  # 変換不要（すでにプーラーURLなど）


# DATABASE_URLが設定されていればPostgreSQL、なければSQLite（ローカル開発用）
_RAW_DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_URL = _resolve_db_url(_RAW_DATABASE_URL) if _RAW_DATABASE_URL else None

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    def _conn():
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        return conn

    def init_db():
        try:
            _init_db_internal()
        except Exception as e:
            print(f"[job_store] ERROR: PostgreSQL init_db失敗 → {e}")
            print("[job_store] DB接続なしで起動継続（ジョブ操作時に再接続試行）")

    def _init_db_internal():
        with _conn() as conn:
            with conn.cursor() as c:
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
                        instrumental INTEGER DEFAULT 0,
                        created_at BIGINT NOT NULL,
                        updated_at BIGINT NOT NULL
                    )
                """)
                # カラム追加（既存テーブルへの対応）
                try:
                    c.execute("ALTER TABLE jobs ADD COLUMN instrumental INTEGER DEFAULT 0")
                except Exception:
                    conn.rollback()
                try:
                    c.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, updated_at DESC)")
                except Exception:
                    conn.rollback()
            conn.commit()

    def _row_to_dict(row, cursor) -> Optional[dict]:
        if row is None:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))

    def create_job(user_id: str, theme: str) -> dict:
        job_id = uuid.uuid4().hex[:8]
        now = int(time.time())
        with _conn() as conn:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO jobs (id, user_id, stage, theme, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (job_id, user_id, "lyrics", theme, now, now),
                )
            conn.commit()
        return get_job(job_id)

    def get_job(job_id: str) -> Optional[dict]:
        with _conn() as conn:
            with conn.cursor() as c:
                c.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
                row = c.fetchone()
                return _row_to_dict(row, c)

    def get_latest_job(user_id: str) -> Optional[dict]:
        with _conn() as conn:
            with conn.cursor() as c:
                c.execute(
                    "SELECT * FROM jobs WHERE user_id = %s AND stage != 'done' ORDER BY updated_at DESC LIMIT 1",
                    (user_id,),
                )
                row = c.fetchone()
                return _row_to_dict(row, c)

    def update_job(job_id: str, **fields) -> dict:
        if not fields:
            return get_job(job_id)
        fields["updated_at"] = int(time.time())
        keys = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [job_id]
        with _conn() as conn:
            with conn.cursor() as c:
                c.execute(f"UPDATE jobs SET {keys} WHERE id = %s", values)
            conn.commit()
        return get_job(job_id)

else:
    # ローカル開発用SQLiteフォールバック
    import sqlite3

    DB_PATH = os.getenv("JOB_DB_PATH", "/tmp/nori_jobs.db")

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
                    instrumental INTEGER DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            try:
                c.execute("ALTER TABLE jobs ADD COLUMN instrumental INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
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
