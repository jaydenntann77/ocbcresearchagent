"""Builds the per-specialist search collections from the corpus store.

Each collection is a separate SQLite file containing only the chunks and
forecast records routed to that specialist: an FTS5 index (exact tokens,
BM25) plus normalised embeddings for semantic search. Builds are versioned
(<spec>-<build>.db) and published atomically through collections/current.json
so readers never see a half-built index."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid

import numpy as np

from app.common import config, embedding
from app.common.instruments import search_tokens_for
from app.common.schemas import SPECIALISTS
from app.ingestion import store

COLLECTION_SCHEMA = """
CREATE TABLE chunks (
  chunk_id TEXT PRIMARY KEY, doc_id TEXT, pdf_page INTEGER, printed_page TEXT, section TEXT, kind TEXT,
  text TEXT, table_id TEXT, seq INTEGER, ocr INTEGER, title TEXT, publication_date TEXT, date_confidence TEXT,
  report_type TEXT, source_url TEXT, embedding BLOB
);
CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, text, extra, title, section, tokenize='unicode61');
CREATE TABLE forecast_records (
  record_id TEXT PRIMARY KEY, doc_id TEXT, table_id TEXT, pdf_page INTEGER, chunk_id TEXT,
  instrument_label TEXT, instrument_key TEXT, group_label TEXT, horizon_label TEXT, horizon_kind TEXT,
  horizon_end TEXT, value TEXT, unit TEXT, scenario TEXT, is_observation INTEGER, table_title TEXT,
  footnotes TEXT, data_date TEXT, title TEXT, publication_date TEXT, date_confidence TEXT, report_type TEXT,
  source_url TEXT
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""


def build_collections(conn: sqlite3.Connection, window_start: str, window_end: str, include_fixtures: bool = False,
                      log=print) -> dict:
    build = time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]
    config.COLLECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    docs = {r["doc_id"]: dict(r) for r in conn.execute(
        "SELECT * FROM documents WHERE status='indexed' AND publication_date BETWEEN ? AND ? AND dev_fixture=?",
        (window_start, window_end, 1 if include_fixtures else 0))}
    stats = {}
    files = {}
    embed_note = embedding.error()
    for spec in SPECIALISTS:
        path = config.COLLECTIONS_DIR / f"{spec}-{build}.db"
        out = sqlite3.connect(path)
        out.executescript(COLLECTION_SCHEMA)
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM chunks WHERE suspicious=0 ORDER BY doc_id, seq")]
        rows = [r for r in rows if r["doc_id"] in docs and spec in json.loads(r["specialists"])]
        vecs = embedding.embed([f"{r['section'] or ''}\n{r['text']}"[:2000] for r in rows]) if rows else None
        for i, r in enumerate(rows):
            d = docs[r["doc_id"]]
            emb = vecs[i].astype(np.float32).tobytes() if vecs is not None else None
            out.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                r["chunk_id"], r["doc_id"], r["pdf_page"], r["printed_page"], r["section"], r["kind"], r["text"],
                r["table_id"], r["seq"], r["ocr"], d["title"] or d["listing_title"], d["publication_date"],
                d["date_confidence"], d["report_type"], d["source_url"], emb))
            out.execute("INSERT INTO chunks_fts VALUES (?,?,?,?,?)", (
                r["chunk_id"], r["text"], search_tokens_for(r["text"]), d["title"] or d["listing_title"] or "",
                r["section"] or ""))
        recs = [dict(r) for r in conn.execute("SELECT * FROM forecast_records")]
        recs = [r for r in recs if r["doc_id"] in docs and spec in json.loads(r["specialists"])]
        for r in recs:
            d = docs[r["doc_id"]]
            out.execute("INSERT INTO forecast_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                r["record_id"], r["doc_id"], r["table_id"], r["pdf_page"], r["chunk_id"], r["instrument_label"],
                r["instrument_key"], r["group_label"], r["horizon_label"], r["horizon_kind"], r["horizon_end"],
                r["value"], r["unit"], r["scenario"], r["is_observation"], r["table_title"], r["footnotes"],
                r["data_date"], d["title"] or d["listing_title"], d["publication_date"], d["date_confidence"],
                d["report_type"], d["source_url"]))
        meta = {"specialist": spec, "build": build, "window_start": window_start, "window_end": window_end,
                "documents": len({r["doc_id"] for r in rows}), "chunks": len(rows), "forecast_records": len(recs),
                "embedding_model": embedding.MODEL_NAME if vecs is not None else None,
                "embedding_note": embed_note}
        for k, v in meta.items():
            out.execute("INSERT INTO meta VALUES (?,?)", (k, json.dumps(v)))
        out.commit()
        out.close()
        files[spec] = path.name
        stats[spec] = meta
        log(f"  collection {spec}: {meta['documents']} docs, {meta['chunks']} chunks, {meta['forecast_records']} forecast cells")
    pointer = config.COLLECTIONS_DIR / "current.json"
    tmp = pointer.with_suffix(".tmp")
    tmp.write_text(json.dumps({"build": build, "files": files, "window_start": window_start,
                               "window_end": window_end}), encoding="utf-8")
    tmp.replace(pointer)
    # Best-effort cleanup of builds older than the previous one.
    keep = set(files.values())
    olds = sorted(p for p in config.COLLECTIONS_DIR.glob("*-*.db") if p.name not in keep)
    for p in olds[:-len(SPECIALISTS)] if len(olds) > len(SPECIALISTS) else []:
        try:
            p.unlink()
        except OSError:
            pass
    return stats
