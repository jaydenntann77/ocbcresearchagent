"""The client book the client-data service answers from: the database, plus - only while demo
mode is ON - the pattern test clients T01-T04 loaded read-only from dummy_data/patterns/.

* Demo mode lives in memory, so it is OFF every time the service (run.py) starts.
* OFF: T01-T04 do not exist for identification, profiles, trades, ideas or logging.
* ON: their T± dates are resolved against today (SGT) and they behave like any other client.
* Every save goes to the database (Store), never to dummy_data/. Asks a user logged about T01-T04
  stay in the database while demo mode is off and are merged back in when it is on again.
* Weiyang's seeded clients (C001-C012) come from the database exactly as before.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

from app.clientdata import patterns
from app.clientdata.generate import Book
from app.clientdata.store import Store
from app.common.timeutil import today_sgt


class ClientBook:
    def __init__(self, store: Store, pattern_dir: Path = patterns.PATTERN_DIR,
                 today: Callable[[], date] = today_sgt):
        self.store, self.pattern_dir, self._today = store, pattern_dir, today
        self.demo = False                      # always starts OFF
        self._cache: tuple[date, Book] | None = None

    # ---------------------------------------------------------------- demo mode
    def set_demo(self, on: bool) -> bool:
        self.demo = bool(on)
        self._cache = None
        return self.demo

    def pattern_book(self) -> Book | None:
        if not self.demo:
            return None
        today = self._today()
        if not self._cache or self._cache[0] != today:
            self._cache = (today, patterns.load(today, self.pattern_dir))
        return self._cache[1]

    def is_pattern(self, client_id: str) -> bool:
        return client_id in patterns.CLIENT_IDS

    # ---------------------------------------------------------------- reads
    def clients(self) -> list[dict]:
        pb = self.pattern_book()
        db = [c for c in self.store.clients() if not self.is_pattern(c["client_id"])]
        return db + (pb.clients if pb else [])

    def contacts(self, client_id: str | None = None) -> list[dict]:
        pb = self.pattern_book()
        if client_id and self.is_pattern(client_id):
            return [p for p in pb.contacts if p["client_id"] == client_id] if pb else []
        db = [p for p in self.store.contacts(client_id) if not self.is_pattern(p["client_id"])]
        return db + ([] if client_id or not pb else pb.contacts)

    def client(self, client_id: str) -> dict | None:
        if self.is_pattern(client_id):
            pb = self.pattern_book()
            return next((c for c in pb.clients if c["client_id"] == client_id), None) if pb else None
        return self.store.client(client_id)

    def contact(self, contact_id: str) -> dict | None:
        pb = self.pattern_book()
        hit = next((p for p in pb.contacts if p["contact_id"] == contact_id), None) if pb else None
        if hit:
            return hit
        row = self.store.contact(contact_id)
        return row if row and not self.is_pattern(row["client_id"]) else None

    def trades(self, client: dict) -> list[dict]:
        if self.is_pattern(client["client_id"]):
            pb = self.pattern_book()
            return [t for t in pb.trades if t["sibs_cif"] == client["sibs_cif"]] if pb else []
        return self.store.trades(client["sibs_cif"])

    def interactions(self, client_id: str, limit: int = 20) -> list[dict]:
        """Saved asks from the database, plus the pattern client's seeded asks while demo mode is on."""
        rows = self.store.interactions(client_id, limit)
        if self.is_pattern(client_id):
            pb = self.pattern_book()
            if not pb:
                return []
            rows = rows + [i for i in pb.interactions if i["client_id"] == client_id]
        return sorted(rows, key=lambda r: r.get("asked_at") or "", reverse=True)[:limit]

    # ---------------------------------------------------------------- writes (database only)
    def add_interaction(self, row: dict) -> dict:
        return self.store.add_interaction(row)
