"""SQLite access for the client book (data/clientdata/clientdata.db)."""
from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path

from app.clientdata import generate, schema
from app.common.timeutil import now_sgt

_lock = threading.Lock()


class Store:
    def __init__(self, path: Path = generate.DB_PATH):
        self.path = path
        if not path.exists():  # first run: build the seeded dummy book (CSV export is a separate CLI step)
            generate.write_sqlite(generate.generate(), path)
        with self._conn() as conn:
            conn.executescript(schema.ddl())

    def _conn(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _all(self, sql: str, args=()) -> list[dict]:
        with _lock, self._conn() as conn:
            return [dict(r) for r in conn.execute(sql, args)]

    def clients(self) -> list[dict]:
        return self._all("SELECT * FROM clients ORDER BY client_id")

    def contacts(self, client_id: str | None = None) -> list[dict]:
        if client_id:
            return self._all("SELECT * FROM contacts WHERE client_id=? ORDER BY is_primary DESC, contact_id", (client_id,))
        return self._all("SELECT * FROM contacts ORDER BY contact_id")

    def client(self, client_id: str) -> dict | None:
        rows = self._all("SELECT * FROM clients WHERE client_id=?", (client_id,))
        return rows[0] if rows else None

    def contact(self, contact_id: str) -> dict | None:
        rows = self._all("SELECT * FROM contacts WHERE contact_id=?", (contact_id,))
        return rows[0] if rows else None

    def interactions(self, client_id: str, limit: int = 20) -> list[dict]:
        return self._all("SELECT * FROM interactions WHERE client_id=? ORDER BY asked_at DESC LIMIT ?",
                         (client_id, limit))

    def add_interaction(self, row: dict) -> dict:
        row = {c: row.get(c) for c, _ in schema.INTERACTION_COLUMNS}
        row["interaction_id"] = "I-" + uuid.uuid4().hex[:10]
        row["asked_at"] = row["asked_at"] or now_sgt().replace(microsecond=0, tzinfo=None).isoformat()
        cols = list(row)
        with _lock, self._conn() as conn:
            conn.execute(f"INSERT INTO interactions ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                         [row[c] for c in cols])
        return row
