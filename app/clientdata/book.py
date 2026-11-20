"""The client book the client-data service answers from: the database, plus the showcase client (C013,
always on) loaded read-only from dummy_data/showcase/, plus - only while demo mode is ON - the pattern
test clients T01-T04 loaded read-only from dummy_data/patterns/.

* Demo mode lives in memory, so it is OFF every time the service (run.py) starts.
* OFF: T01-T04 do not exist for identification, profiles, trades, ideas or logging.
* ON: their T± dates are resolved against today (SGT) and they behave like any other client.
* Every save goes to the database (Store), never to dummy_data/. Asks a user logged about T01-T04
  stay in the database while demo mode is off and are merged back in when it is on again.
* Weiyang's seeded clients (C001-C012) come from the database exactly as before.
* The showcase client (Brightway Engineering, app/clientdata/showcase.py) is there whether demo
  mode is on or off, with its T± dates resolved against today like the pattern clients. Asks logged
  about it are saved to the database and merged with its seeded history.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Callable

from app.clientdata import patterns, showcase
from app.clientdata.generate import Book
from app.clientdata.store import Store
from app.common.timeutil import today_sgt


class ClientBook:
    def __init__(self, store: Store, pattern_dir: Path = patterns.PATTERN_DIR,
                 today: Callable[[], date] = today_sgt, showcase_dir: Path | None = showcase.SHOWCASE_DIR):
        self.store, self.pattern_dir, self._today = store, pattern_dir, today
        self.showcase_dir = showcase_dir       # None: no showcase client (tests of the seeded book alone)
        self.demo = False                      # always starts OFF
        self._cache: tuple[date, Book] | None = None
        self._show_cache: tuple[date, Book] | None = None

    # ---------------------------------------------------------------- showcase client (always on)
    def showcase_book(self) -> Book | None:
        if self.showcase_dir is None:
            return None
        today = self._today()
        if not self._show_cache or self._show_cache[0] != today:
            self._show_cache = (today, showcase.load(today, self.showcase_dir))
        return self._show_cache[1]

    def is_showcase(self, client_id: str) -> bool:
        return self.showcase_dir is not None and client_id in showcase.CLIENT_IDS

    def _fixed(self, client_id: str) -> Book | None:
        """The read-only book a file-based client comes from (showcase, or pattern while demo is on)."""
        if self.is_showcase(client_id):
            return self.showcase_book()
        if self.is_pattern(client_id):
            return self.pattern_book()
        return None

    def _file_books(self) -> list[Book]:
        return [b for b in (self.showcase_book(), self.pattern_book()) if b]

    def _from_files(self, client_id: str) -> bool:
        return self.is_showcase(client_id) or self.is_pattern(client_id)

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
        db = [c for c in self.store.clients() if not self._from_files(c["client_id"])]
        return db + [c for b in self._file_books() for c in b.clients]

    def contacts(self, client_id: str | None = None) -> list[dict]:
        if client_id and self._from_files(client_id):
            fb = self._fixed(client_id)
            return [p for p in fb.contacts if p["client_id"] == client_id] if fb else []
        db = [p for p in self.store.contacts(client_id) if not self._from_files(p["client_id"])]
        return db + ([] if client_id else [p for b in self._file_books() for p in b.contacts])

    def client(self, client_id: str) -> dict | None:
        if self._from_files(client_id):
            fb = self._fixed(client_id)
            return next((c for c in fb.clients if c["client_id"] == client_id), None) if fb else None
        return self.store.client(client_id)

    def contact(self, contact_id: str) -> dict | None:
        for b in self._file_books():
            hit = next((p for p in b.contacts if p["contact_id"] == contact_id), None)
            if hit:
                return hit
        row = self.store.contact(contact_id)
        return row if row and not self._from_files(row["client_id"]) else None

    def trades(self, client: dict) -> list[dict]:
        if self._from_files(client["client_id"]):
            fb = self._fixed(client["client_id"])
            return [t for t in fb.trades if t["sibs_cif"] == client["sibs_cif"]] if fb else []
        return self.store.trades(client["sibs_cif"])

    def interactions(self, client_id: str, limit: int = 20) -> list[dict]:
        """Saved asks from the database, plus a file-based client's seeded asks (the showcase client
        always, a pattern client while demo mode is on)."""
        rows = self.store.interactions(client_id, limit)
        if self._from_files(client_id):
            fb = self._fixed(client_id)
            if not fb:
                return []
            rows = rows + [i for i in fb.interactions if i["client_id"] == client_id]
        return sorted(rows, key=lambda r: r.get("asked_at") or "", reverse=True)[:limit]

    # ---------------------------------------------------------------- writes (database only)
    def add_interaction(self, row: dict) -> dict:
        return self.store.add_interaction(row)
