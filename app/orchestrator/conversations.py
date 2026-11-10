"""Conversation history - the orchestrator's only storage (data/orchestrator).

Each conversation belongs to the visitor session that created it (the
gateway's signed session id), so visitors never see each other's history."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid

from app.common import config
from app.common.timeutil import now_sgt, today_sgt

_lock = threading.Lock()


def _conn():
    config.ORCH_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.ORCH_DIR / "conversations.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT, state TEXT);
    CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT, answer TEXT,
                                         created_at TEXT);
    CREATE TABLE IF NOT EXISTS model_usage (day TEXT PRIMARY KEY, calls INTEGER);
    """)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(conversations)")}
    if "owner" not in cols:
        conn.execute("ALTER TABLE conversations ADD COLUMN owner TEXT DEFAULT 'local'")
    return conn


def create(title: str, owner: str) -> str:
    cid = "c-" + uuid.uuid4().hex[:12]
    ts = now_sgt().isoformat()
    with _lock, _conn() as conn:
        conn.execute("INSERT INTO conversations(id,title,created_at,updated_at,state,owner) VALUES (?,?,?,?,?,?)",
                     (cid, title[:120], ts, ts, "{}", owner))
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


def exists(cid: str, owner: str) -> bool:
    with _lock, _conn() as conn:
        return conn.execute("SELECT 1 FROM conversations WHERE id=? AND owner=?", (cid, owner)).fetchone() is not None


def list_all(owner: str) -> list[dict]:
    with _lock, _conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE owner=? ORDER BY updated_at DESC LIMIT 200",
            (owner,))]


def get(cid: str, owner: str) -> dict | None:
    with _lock, _conn() as conn:
        c = conn.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id=? AND owner=?",
                         (cid, owner)).fetchone()
        if not c:
            return None
        msgs = [dict(r) for r in conn.execute(
            "SELECT id, role, content, answer, created_at FROM messages WHERE conversation_id=? ORDER BY created_at", (cid,))]
    for m in msgs:
        m["answer"] = json.loads(m["answer"]) if m["answer"] else None
    return dict(c) | {"messages": msgs}


def delete(cid: str, owner: str):
    with _lock, _conn() as conn:
        if conn.execute("SELECT 1 FROM conversations WHERE id=? AND owner=?", (cid, owner)).fetchone():
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
            conn.execute("DELETE FROM conversations WHERE id=?", (cid,))


def take_model_call(cap: int) -> bool:
    """Reserve one model call against today's (SGT) cap. False once the cap is used up."""
    day = today_sgt().isoformat()
    with _lock, _conn() as conn:
        row = conn.execute("SELECT calls FROM model_usage WHERE day=?", (day,)).fetchone()
        used = row["calls"] if row else 0
        if used >= cap:
            return False
        conn.execute("INSERT INTO model_usage(day, calls) VALUES(?, 1) ON CONFLICT(day) DO UPDATE SET calls=calls+1",
                     (day,))
        return True


def get_message(cid: str, mid: str, owner: str) -> tuple[dict, str] | None:
    """(assistant answer, the user question it answered) for one message of a conversation the owner holds."""
    conv = get(cid, owner)
    if not conv:
        return None
    question = ""
    for m in conv["messages"]:
        if m["role"] == "user":
            question = m["content"]
        elif m["id"] == mid and m["answer"]:
            return m["answer"], question
    return None


def update_answer(cid: str, mid: str, answer: dict):
    with _lock, _conn() as conn:
        conn.execute("UPDATE messages SET answer=? WHERE id=? AND conversation_id=?", (json.dumps(answer), mid, cid))
