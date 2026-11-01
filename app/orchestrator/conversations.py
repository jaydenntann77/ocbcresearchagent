"""Conversation history - the orchestrator's only storage (data/orchestrator)."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid

from app.common import config
from app.common.timeutil import now_sgt

_lock = threading.Lock()


def _conn():
    config.ORCH_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.ORCH_DIR / "conversations.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT, state TEXT);
    CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, answer TEXT,
                                         created_at TEXT);
    """)
    return conn


def create(title: str) -> str:
    cid = "c-" + uuid.uuid4().hex[:12]
    ts = now_sgt().isoformat()
    with _lock, _conn() as conn:
        conn.execute("INSERT INTO conversations VALUES (?,?,?,?,?)", (cid, title[:120], ts, ts, "{}"))
    return cid


def add_message(cid: str, role: str, content: str, answer: dict | None = None) -> str:
    mid = "m-" + uuid.uuid4().hex[:12]
    ts = now_sgt().isoformat()
    with _lock, _conn() as conn:
        conn.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)",
                     (mid, cid, role, content, json.dumps(answer) if answer else None, ts))
        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (ts, cid))
    return mid


def get_state(cid: str) -> dict:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT state FROM conversations WHERE id=?", (cid,)).fetchone()
    return json.loads(row["state"]) if row and row["state"] else {}


def set_state(cid: str, state: dict):
    with _lock, _conn() as conn:
        conn.execute("UPDATE conversations SET state=? WHERE id=?", (json.dumps(state), cid))


def exists(cid: str) -> bool:
    with _lock, _conn() as conn:
        return conn.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone() is not None


def list_all() -> list[dict]:
    with _lock, _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT 200")]


def get(cid: str) -> dict | None:
    with _lock, _conn() as conn:
        c = conn.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id=?", (cid,)).fetchone()
        if not c:
            return None
        msgs = [dict(r) for r in conn.execute(
            "SELECT id, role, content, answer, created_at FROM messages WHERE conversation_id=? ORDER BY created_at", (cid,))]
    for m in msgs:
        m["answer"] = json.loads(m["answer"]) if m["answer"] else None
    return dict(c) | {"messages": msgs}


def delete(cid: str):
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
        conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
