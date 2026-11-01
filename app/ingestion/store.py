"""Corpus metadata store (SQLite). Written only by the ingestion service;
the research, validator and docs services open it read-only."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  doc_id TEXT PRIMARY KEY,
  sha256 TEXT UNIQUE NOT NULL,
  title TEXT, listing_title TEXT, author TEXT,
  category TEXT, section TEXT, subcategory TEXT, report_type TEXT,
  source_url TEXT NOT NULL, alias_urls TEXT DEFAULT '[]',
  listing_date TEXT, printed_date TEXT, meta_date TEXT, last_modified_header TEXT,
  publication_date TEXT, date_confidence TEXT, date_basis TEXT, date_flags TEXT DEFAULT '[]',
  page_count INTEGER, status TEXT NOT NULL, status_detail TEXT,
  raw_path TEXT, ingested_at TEXT, run_id TEXT,
  warnings TEXT DEFAULT '[]', specialists TEXT DEFAULT '[]', ocr_pages TEXT DEFAULT '[]',
  dev_fixture INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pages (
  doc_id TEXT, pdf_page INTEGER, printed_page TEXT, text TEXT, ocr INTEGER DEFAULT 0, ocr_failed INTEGER DEFAULT 0,
  PRIMARY KEY (doc_id, pdf_page)
);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY, doc_id TEXT, pdf_page INTEGER, printed_page TEXT, section TEXT,
  kind TEXT, text TEXT, table_id TEXT, seq INTEGER, specialists TEXT DEFAULT '[]',
  suspicious INTEGER DEFAULT 0, suspicious_reason TEXT, ocr INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id);
CREATE TABLE IF NOT EXISTS forecast_records (
  record_id TEXT PRIMARY KEY, doc_id TEXT, table_id TEXT, pdf_page INTEGER, chunk_id TEXT,
  instrument_label TEXT, instrument_key TEXT, group_label TEXT,
  horizon_label TEXT, horizon_kind TEXT, horizon_end TEXT,
  value TEXT, unit TEXT, scenario TEXT, is_observation INTEGER,
  table_title TEXT, footnotes TEXT DEFAULT '[]', data_date TEXT, specialists TEXT DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS fr_key ON forecast_records(instrument_key);
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT, trigger TEXT,
  window_start TEXT, window_end TEXT, window_days INTEGER, expanded INTEGER DEFAULT 0,
  summary TEXT DEFAULT '{}', error TEXT
);
CREATE TABLE IF NOT EXISTS run_items (
  run_id TEXT, url TEXT, state TEXT, detail TEXT, listing TEXT, doc_id TEXT, updated_at TEXT,
  PRIMARY KEY (run_id, url)
);
CREATE TABLE IF NOT EXISTS section_checks (
  run_id TEXT, source TEXT, category TEXT, section TEXT, status TEXT, items INTEGER, detail TEXT
);
CREATE TABLE IF NOT EXISTS corpus_state (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(path: Path, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
        conn.execute("PRAGMA journal_mode=DELETE")  # readers open the file read-only
        conn.executescript(SCHEMA)
    conn.row_factory = sqlite3.Row
    return conn


def get_state(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM corpus_state WHERE key=?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_state(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute("INSERT INTO corpus_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                 (key, json.dumps(value)))
