"""SQLite-backed persistence: interests, memory notes, search history, API key, model quota state."""
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "mcp_agent.db"

QUOTA_COOLDOWN_SECONDS = 60 * 60  # treat a model as exhausted for 1h after a quota error


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS interests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            created_at REAL NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            model_used TEXT,
            created_at REAL NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS model_status (
            model TEXT PRIMARY KEY,
            quota_exceeded_at REAL
        )""")


# ---- interests ----

def add_interest(text: str):
    text = text.strip()
    if not text:
        return
    with _conn() as conn:
        conn.execute("INSERT INTO interests (text, created_at) VALUES (?, ?)", (text, time.time()))


def list_interests() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("SELECT id, text, created_at FROM interests ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def delete_interest(interest_id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM interests WHERE id = ?", (interest_id,))


# ---- memory notes ----

def get_memory() -> str:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'memory'").fetchone()
        return row["value"] if row else ""


def set_memory(text: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('memory', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (text,),
        )


# ---- search history ----

def add_search(query: str, model_used: str | None = None):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO search_history (query, model_used, created_at) VALUES (?, ?, ?)",
            (query, model_used, time.time()),
        )


def list_search_history(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, query, model_used, created_at FROM search_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def clear_search_history():
    with _conn() as conn:
        conn.execute("DELETE FROM search_history")


# ---- API key ----

def get_api_key() -> str | None:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'gemini_api_key'").fetchone()
        return row["value"] if row else None


def set_api_key(key: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('gemini_api_key', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key.strip(),),
        )


# ---- selected model ----

def get_selected_model() -> str | None:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'selected_model'").fetchone()
        return row["value"] if row else None


def set_selected_model(model: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('selected_model', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (model,),
        )


# ---- model quota status ----

def mark_quota_exceeded(model: str):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO model_status (model, quota_exceeded_at) VALUES (?, ?) "
            "ON CONFLICT(model) DO UPDATE SET quota_exceeded_at = excluded.quota_exceeded_at",
            (model, time.time()),
        )


def get_available_models(all_models: list[str]) -> list[str]:
    """Return all_models minus those still in quota cooldown."""
    now = time.time()
    with _conn() as conn:
        rows = conn.execute("SELECT model, quota_exceeded_at FROM model_status").fetchall()
    blocked = {
        r["model"] for r in rows
        if r["quota_exceeded_at"] and now - r["quota_exceeded_at"] < QUOTA_COOLDOWN_SECONDS
    }
    return [m for m in all_models if m not in blocked]


def get_model_cooldowns(all_models: list[str]) -> dict[str, float]:
    """Return {model: seconds_remaining} for models still in cooldown."""
    now = time.time()
    with _conn() as conn:
        rows = conn.execute("SELECT model, quota_exceeded_at FROM model_status").fetchall()
    result = {}
    for r in rows:
        if r["model"] in all_models and r["quota_exceeded_at"]:
            remaining = QUOTA_COOLDOWN_SECONDS - (now - r["quota_exceeded_at"])
            if remaining > 0:
                result[r["model"]] = remaining
    return result


init_db()