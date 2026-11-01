"""Read-only, permission-scoped access to specialist search collections.

A specialist never opens a database itself: it receives CollectionHandle
objects from `CollectionRegistry.grant(specialist)`, which issues handles only
for the collections listed for that specialist in config/specialists.json."""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass

import numpy as np

from app.common import config, embedding


class CollectionAccessDenied(PermissionError):
    pass


@dataclass
class Hit:
    chunk: dict
    score: float
    lexical_rank: int | None
    semantic_rank: int | None
    exact_match: bool


def _fts_query(text: str) -> str:
    toks = re.findall(r"[A-Za-z0-9$&]+", text)
    toks = [t for t in toks if len(t) > 1 and t.lower() not in _STOP]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(toks)) if toks else ""


_STOP = set("""a an and are as at be by for from has have in is it its of on or that the this to was were will with
what does say about give me our ocbc s through latest available published view please""".split())


class CollectionHandle:
    def __init__(self, name: str, path):
        self.name = name
        self.conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.meta = {r["key"]: json.loads(r["value"]) for r in self.conn.execute("SELECT key,value FROM meta")}
        rows = self.conn.execute("SELECT chunk_id, embedding FROM chunks ORDER BY rowid").fetchall()
        self._ids = [r["chunk_id"] for r in rows]
        embs = [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows if r["embedding"]]
        self._matrix = np.vstack(embs) if embs and len(embs) == len(rows) else None
        self._lock = threading.Lock()

    def close(self):
        self.conn.close()

    # -------------------------------------------------------------- retrieval
    def search(self, query: str, exact_terms: list[str] | None = None, k: int = 12,
               kinds: tuple[str, ...] = ("prose", "table")) -> list[Hit]:
        exact_terms = [t for t in (exact_terms or []) if t]
        lex: dict[str, int] = {}
        with self._lock:
            q = _fts_query(query + " " + " ".join(exact_terms))
            if q:
                for rank, r in enumerate(self.conn.execute(
                        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts, 0, 1.0, 2.0, 0.5, 0.5) LIMIT 60",
                        (q,))):
                    lex[r["chunk_id"]] = rank
            # Exact identifiers (pairs, tickers, tenors) get their own pass so
            # they are never drowned out by generic terms.
            for t in exact_terms:
                fq = _fts_query(t)
                if not fq:
                    continue
                for rank, r in enumerate(self.conn.execute(
                        "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 30", (fq,))):
                    lex[r["chunk_id"]] = min(lex.get(r["chunk_id"], 999), rank)
        sem: dict[str, int] = {}
        if self._matrix is not None and query.strip():
            qv = embedding.embed([query], query=True)
            if qv is not None:
                sims = self._matrix @ qv[0]
                for rank, idx in enumerate(np.argsort(-sims)[:60]):
                    sem[self._ids[idx]] = rank
        ids = set(lex) | set(sem)
        if not ids:
            return []
        rows = {r["chunk_id"]: dict(r) for r in self.conn.execute(
            f"SELECT chunk_id, doc_id, pdf_page, printed_page, section, kind, text, table_id, seq, ocr, title, "
            f"publication_date, date_confidence, report_type, source_url FROM chunks WHERE chunk_id IN "
            f"({','.join('?' * len(ids))})", list(ids))}
        hits = []
        aliases = [a.lower() for a in exact_terms]
        for cid, row in rows.items():
            if row["kind"] not in kinds:
                continue
            if len(row["text"]) < 120 or re.match(r"^\W*\d*\s*Source:", row["text"]):
                continue  # chart captions / source lines carry no research content
            score = 0.0
            if cid in lex:
                score += 1.0 / (60 + lex[cid])
            if cid in sem:
                score += 1.0 / (60 + sem[cid])
            low = row["text"].lower()
            exact = any(a in low for a in aliases)
            if exact:
                score += 0.02
            hits.append(Hit(row, score, lex.get(cid), sem.get(cid), exact))
        hits.sort(key=lambda h: (-h.score, h.chunk["publication_date"] or ""), reverse=False)
        return hits[:k]

    def neighbours(self, chunk: dict) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT chunk_id, text, seq FROM chunks WHERE doc_id=? AND pdf_page=? AND seq IN (?,?) AND kind='prose'",
            (chunk["doc_id"], chunk["pdf_page"], chunk["seq"] - 1, chunk["seq"] + 1))]

    def chunk(self, chunk_id: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM chunks WHERE chunk_id=?", (chunk_id,)).fetchone()
        return dict(r) if r else None

    def forecast_records(self, keys: list[str]) -> list[dict]:
        if not keys:
            return []
        return [dict(r) for r in self.conn.execute(
            f"SELECT * FROM forecast_records WHERE instrument_key IN ({','.join('?' * len(keys))}) "
            f"ORDER BY publication_date DESC, table_id, rowid", keys)]

    def available_instrument_keys(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT DISTINCT instrument_key FROM forecast_records")}

    def documents(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT DISTINCT doc_id, title, publication_date, report_type FROM chunks ORDER BY publication_date DESC")]


class CollectionRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._build = None
        self._handles: dict[str, CollectionHandle] = {}
        self.pointer: dict = {}
        self.policy = config.load_json_config("specialists.json")["access"]

    def _refresh(self):
        pointer_path = config.COLLECTIONS_DIR / "current.json"
        if not pointer_path.exists():
            return
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if pointer.get("build") == self._build:
            return
        handles = {name: CollectionHandle(name, config.COLLECTIONS_DIR / fn) for name, fn in pointer["files"].items()}
        old = self._handles
        self._handles, self._build, self.pointer = handles, pointer["build"], pointer
        for h in old.values():
            h.close()

    def ready(self) -> bool:
        with self._lock:
            self._refresh()
            return bool(self._handles)

    def grant(self, specialist: str) -> list[CollectionHandle]:
        allowed = self.policy.get(specialist)
        if not allowed:
            raise CollectionAccessDenied(f"no collections are permitted for '{specialist}'")
        with self._lock:
            self._refresh()
            return [self._handles[c] for c in allowed if c in self._handles]

    def open_for(self, specialist: str, collection: str) -> CollectionHandle:
        """Explicit access check used by tests and by any future tool surface."""
        if collection not in self.policy.get(specialist, []):
            raise CollectionAccessDenied(f"specialist '{specialist}' may not search collection '{collection}'")
        with self._lock:
            self._refresh()
            return self._handles[collection]
