import json
import os
import sqlite3
from datetime import datetime, timezone

from . import config


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.sqlite_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    path = config.sqlite_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                system_prompt TEXT
            )
            """
        )


def check_db() -> bool:
    try:
        with _connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


def session_exists(session_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1", (session_id,)
        ).fetchone()
        return row is not None


def get_system_prompt(session_id: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        return row["system_prompt"] if row else None


def set_system_prompt(session_id: str, system_prompt: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (session_id, system_prompt) VALUES (?, ?)
            ON CONFLICT(session_id) DO UPDATE SET system_prompt = excluded.system_prompt
            """,
            (session_id, system_prompt),
        )


def get_history(session_id: str) -> list[dict]:
    """Full history, oldest first, in the shape the API returns."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    out = []
    for r in rows:
        msg = {"role": r["role"], "content": r["content"]}
        if r["role"] == "assistant" and r["metadata"]:
            msg["metadata"] = json.loads(r["metadata"])
        out.append(msg)
    return out


def add_exchange(session_id: str, user_text: str, assistant_text: str, metadata: dict) -> None:
    """Save the user + assistant messages together, so a failed request leaves no trace."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, 'user', ?, NULL, ?)",
            (session_id, user_text, now),
        )
        conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            (session_id, assistant_text, json.dumps(metadata), now),
        )