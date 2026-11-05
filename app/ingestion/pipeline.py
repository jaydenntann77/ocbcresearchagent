"""Ingestion run: discover -> screen by date -> download -> validate ->
deduplicate -> extract -> resolve dates -> chunk/route -> index.

Every item's state is committed as it changes, so an interrupted run resumes
where it stopped. Re-running is idempotent: documents are keyed by content
hash and re-ingesting identical content changes nothing."""
from __future__ import annotations

import hashlib
import json
import re
import traceback
import uuid
from datetime import date, timedelta

from app.common import config
from app.common.timeutil import fmt_range, ingestion_window, now_sgt
from app.ingestion import chunking, dates, indexer, store
from app.ingestion.discovery import ListingItem, as_dict, discover
from app.ingestion.fetcher import Fetcher, SourceBoundaryError
from app.ingestion.pdfparse import PdfInvalid, extract

TERMINAL = {"indexed", "duplicate", "unchanged", "excluded_date", "quarantined", "failed_download",
            "inaccessible", "invalid_pdf", "parse_failed"}


def report_type(title: str, category: str | None, section: str | None, url: str,
                subcategory: str | None = None) -> str:
    from urllib.parse import unquote
    s = " ".join(x or "" for x in (title, category, section, subcategory, unquote(url))).lower()
    if re.search(r"daily|dailyoutlook|dto|dmo|credit snapshot", s):
        return "daily"
    if re.search(r"weekly|week in|wir |wmv|fx weekly", s):
        return "weekly"
    if re.search(r"monthly|outlook 2h|outlook 1h|global economic outlook|compendium|half-year", s):
        return "monthly"
    return "thematic"


class Run:
    def __init__(self, conn, run_id: str, log):
        self.conn, self.run_id, self.log = conn, run_id, log

    def set_item(self, url: str, state: str, detail: str = "", listing: dict | None = None, doc_id: str | None = None):
        self.conn.execute("""INSERT INTO run_items(run_id,url,state,detail,listing,doc_id,updated_at) VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(run_id,url) DO UPDATE SET state=excluded.state, detail=excluded.detail,
            listing=COALESCE(excluded.listing, run_items.listing), doc_id=COALESCE(excluded.doc_id, run_items.doc_id),
            updated_at=excluded.updated_at""",
                          (self.run_id, url, state, detail, json.dumps(listing) if listing else None, doc_id,
                           now_sgt().isoformat()))
        self.conn.commit()


def _resume_or_start(conn, window_start: date, window_end: date, days: int, expanded: bool, trigger: str):
    row = conn.execute("SELECT * FROM runs WHERE status IN ('running','interrupted') ORDER BY started_at DESC LIMIT 1").fetchone()
    if row and row["window_start"] == window_start.isoformat() and row["window_end"] == window_end.isoformat():
        conn.execute("UPDATE runs SET status='running', error=NULL WHERE run_id=?", (row["run_id"],))
        conn.commit()
        return row["run_id"], True
    if row:  # stale run for another window: close it out
        conn.execute("UPDATE runs SET status='abandoned', finished_at=? WHERE run_id=?",
                     (now_sgt().isoformat(), row["run_id"]))
    run_id = now_sgt().strftime("run-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    conn.execute("INSERT INTO runs(run_id,started_at,status,trigger,window_start,window_end,window_days,expanded) "
                 "VALUES(?,?,?,?,?,?,?,?)", (run_id, now_sgt().isoformat(), "running", trigger, window_start.isoformat(),
                                             window_end.isoformat(), days, int(expanded)))
    conn.commit()
    return run_id, False


def _store_document(conn, doc_id, sha, item: ListingItem, ext, res: dates.DateResolution, raw_path, run_id,
                    fetch_info: dict, status: str, status_detail: str = "", dev_fixture: bool = False):
    primary = chunking.primary_specialist(item.category, item.section, item.subcategory)
    title = item.title or ext.title or item.url.rsplit("/", 1)[-1]
    series = (item.series or "").strip()
    if series and series.lower() not in title.lower() and not re.search(r"\(\d", title):
        title = f"{series}: {title}"
    rtype = report_type(title, item.category, item.section, item.url, item.subcategory)
    chunks = chunking.build_chunks(doc_id, ext, primary) if status == "indexed" else []
    specs = sorted({s for c in chunks if not c.suspicious_reason for s in c.specialists})
    with conn:
        for tbl in ("pages", "chunks", "forecast_records"):
            conn.execute(f"DELETE FROM {tbl} WHERE doc_id=?", (doc_id,))
        conn.execute("""INSERT INTO documents(doc_id,sha256,title,listing_title,author,category,section,subcategory,report_type,
            source_url,alias_urls,listing_date,printed_date,meta_date,last_modified_header,publication_date,date_confidence,
            date_basis,date_flags,page_count,status,status_detail,raw_path,ingested_at,run_id,warnings,specialists,ocr_pages,dev_fixture)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(doc_id) DO UPDATE SET status=excluded.status, status_detail=excluded.status_detail,
              publication_date=excluded.publication_date, date_confidence=excluded.date_confidence,
              date_basis=excluded.date_basis, date_flags=excluded.date_flags, listing_date=excluded.listing_date,
              title=excluded.title, listing_title=excluded.listing_title, category=excluded.category,
              section=excluded.section, subcategory=excluded.subcategory, report_type=excluded.report_type,
              specialists=excluded.specialists, warnings=excluded.warnings, ocr_pages=excluded.ocr_pages,
              run_id=excluded.run_id, ingested_at=excluded.ingested_at""",
                     (doc_id, sha, title, item.title, ext.author, item.category, item.section, item.subcategory, rtype,
                      item.url, "[]", res.listing_date.isoformat() if res.listing_date else None,
                      res.printed_date.isoformat() if res.printed_date else None,
                      res.meta_date.isoformat() if res.meta_date else None, fetch_info.get("last_modified"),
                      res.publication_date.isoformat() if res.publication_date else None, res.confidence, res.basis,
                      json.dumps(res.flags + _meta_title_flags(ext.title, res.publication_date)),
                      ext.page_count, status, status_detail, str(raw_path), now_sgt().isoformat(), run_id,
                      json.dumps(ext.warnings), json.dumps(specs),
                      json.dumps([p.pdf_page for p in ext.pages if p.ocr]), int(dev_fixture)))
        if status != "indexed":
            return specs, len(chunks)
        for p in ext.pages:
            conn.execute("INSERT INTO pages VALUES(?,?,?,?,?,?)",
                         (doc_id, p.pdf_page, p.printed_page, p.full_text, int(p.ocr), int(p.ocr_failed)))
        for c in chunks:
            conn.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (c.chunk_id, doc_id, c.pdf_page, c.printed_page, c.section, c.kind, c.text, c.table_id, c.seq,
                          json.dumps(c.specialists), int(bool(c.suspicious_reason)), c.suspicious_reason, int(c.ocr)))
        table_chunk = {c.table_id: c.chunk_id for c in chunks if c.table_id}
        for p in ext.pages:
            for t in p.tables:
                if t.kind != "forecast":
                    continue
                for n, cell in enumerate(t.cells):
                    rid = f"{doc_id}-{t.table_id}-r{n}"
                    conn.execute("INSERT INTO forecast_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                        rid, doc_id, t.table_id, p.pdf_page, table_chunk.get(t.table_id), cell.instrument_label,
                        cell.instrument_key, cell.group_label, cell.horizon_label, cell.horizon_kind, cell.horizon_end,
                        cell.value, cell.unit, cell.scenario, int(cell.is_observation), t.title,
                        json.dumps(t.footnotes), t.data_date,
                        json.dumps(chunking.forecast_key_specialists(cell.instrument_key))))
    return specs, len(chunks)


def _meta_title_flags(meta_title: str | None, pub: date | None) -> list[str]:
    """Flag a PDF metadata title that carries a different date (e.g. a reused
    template titled 'DMO 23 Apr 2026'). Metadata titles never set the date."""
    from app.common.timeutil import parse_human_date
    d = parse_human_date(meta_title or "")
    if d and pub and d != pub:
        return [f"PDF metadata title '{meta_title}' carries date {d}; it is not used (listing/printed date {pub} applies)"]
    return []


def ingest_pdf_bytes(conn, data: bytes, item: ListingItem, window: tuple[date, date], run: Run,
                     fetch_info: dict | None = None, dev_fixture: bool = False) -> str:
    """Process one downloaded payload. Returns the resulting item state."""
    fetch_info = fetch_info or {}
    sha = hashlib.sha256(data).hexdigest()
    doc_id = "ocbc-" + sha[:12]
    existing = conn.execute("SELECT doc_id, source_url, alias_urls, status FROM documents WHERE sha256=?", (sha,)).fetchone()
    if existing and existing["source_url"] != item.url:
        aliases = set(json.loads(existing["alias_urls"]))
        aliases.add(item.url)
        conn.execute("UPDATE documents SET alias_urls=? WHERE doc_id=?", (json.dumps(sorted(aliases)), existing["doc_id"]))
        conn.commit()
        run.set_item(item.url, "duplicate", f"identical content to {existing['doc_id']} ({existing['source_url']})",
                     doc_id=existing["doc_id"])
        return "duplicate"
    if existing and existing["status"] == "indexed":
        pub = conn.execute("SELECT publication_date FROM documents WHERE doc_id=?", (doc_id,)).fetchone()[0]
        if pub and window[0].isoformat() <= pub <= window[1].isoformat():
            run.set_item(item.url, "unchanged", "already indexed with identical content", doc_id=doc_id)
            return "unchanged"
    try:
        ext = extract(data)
    except PdfInvalid as exc:
        run.set_item(item.url, "invalid_pdf", str(exc))
        return "invalid_pdf"
    except Exception as exc:  # noqa: BLE001
        run.set_item(item.url, "parse_failed", f"{type(exc).__name__}: {exc}")
        return "parse_failed"
    listing = date.fromisoformat(item.listing_date) if item.listing_date else None
    printed = dates.printed_date_from_page(ext.pages[0].full_text if ext.pages else "")
    res = dates.resolve(listing, printed, ext.meta_creation)
    raw_path = config.RAW_DIR / f"{sha}.pdf"
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    if not raw_path.exists():
        raw_path.write_bytes(data)
    if res.quarantine:
        status, detail = "quarantined", "; ".join(res.flags)
    elif not (window[0] <= res.publication_date <= window[1]):
        status, detail = "excluded_date", f"resolved publication date {res.publication_date} outside window"
    else:
        status, detail = "indexed", ""
    if existing and existing["status"] == "indexed" and status == "indexed":
        run.set_item(item.url, "unchanged", "already indexed with identical content", doc_id=doc_id)
        return "unchanged"
    specs, n = _store_document(conn, doc_id, sha, item, ext, res, raw_path, run.run_id, fetch_info, status, detail,
                               dev_fixture)
    if status == "indexed":
        # Same URL re-published with different content: keep the old version
        # for audit but take it out of the searchable corpus.
        with conn:
            replaced = conn.execute("UPDATE documents SET status='superseded', status_detail=? WHERE source_url=? "
                                    "AND sha256<>? AND status='indexed'",
                                    (f"replaced by {doc_id} (new content at the same URL)", item.url, sha)).rowcount
        if replaced:
            run.set_item(item.url, status, f"{detail or ''} replaced {replaced} earlier version(s) at this URL".strip(),
                         doc_id=doc_id)
    run.set_item(item.url, status, detail or f"{n} chunks; specialists: {', '.join(specs)}", doc_id=doc_id)
    return status


def run_ingestion(days: int | None = None, trigger: str = "manual", log=print, fetcher: Fetcher | None = None,
                  today: date | None = None) -> dict:
    days = days or config.INGEST_WINDOW_DAYS
    expanded = days != config.INGEST_WINDOW_DAYS
    start, end = ingestion_window(days, today)
    conn = store.connect(config.META_DB)
    run_id, resumed = _resume_or_start(conn, start, end, days, expanded, trigger)
    run = Run(conn, run_id, log)
    log(f"Ingestion {run_id} ({'resumed' if resumed else 'new'}): window {start} to {end} inclusive (SGT), "
        f"{days} days{' [EXPANDED]' if expanded else ''}")
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher()
    try:
        items, checks = discover(fetcher, start, end, log)
        conn.execute("DELETE FROM section_checks WHERE run_id=?", (run_id,))
        for c in checks:
            conn.execute("INSERT INTO section_checks VALUES(?,?,?,?,?,?,?)",
                         (run_id, c.source, c.category, c.section, c.status, c.items, c.detail))
        conn.commit()
        done = {r["url"]: r["state"] for r in conn.execute("SELECT url,state FROM run_items WHERE run_id=?", (run_id,))}
        for it in items:
            if done.get(it.url) not in TERMINAL:
                run.set_item(it.url, "discovered", "", listing=as_dict(it))
        for idx, it in enumerate(items, 1):
            if done.get(it.url) in TERMINAL:
                continue
            ld = date.fromisoformat(it.listing_date) if it.listing_date else None
            if ld and not (start <= ld <= end):
                run.set_item(it.url, "excluded_date", f"website listing date {ld} outside window (not downloaded)")
                continue
            if not ld:
                fd = dates.filename_date(it.url)
                if fd and not (start - timedelta(days=3) <= fd <= end + timedelta(days=3)):
                    run.set_item(it.url, "excluded_date",
                                 f"no listing date; file-name date {fd} clearly outside window (not downloaded)")
                    continue
            log(f"  [{idx}/{len(items)}] {it.title[:70]}")
            try:
                r = fetcher.get(it.url)
            except SourceBoundaryError as exc:
                run.set_item(it.url, "inaccessible", f"source boundary: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                run.set_item(it.url, "failed_download", f"{type(exc).__name__}: {exc}")
                continue
            if r.status in (401, 403, 404, 410):
                run.set_item(it.url, "inaccessible", f"HTTP {r.status}")
                continue
            if r.status != 200:
                run.set_item(it.url, "failed_download", f"HTTP {r.status} after bounded retries")
                continue
            ingest_pdf_bytes(conn, r.content, it, (start, end), run,
                             {"last_modified": r.last_modified, "final_url": r.url},
                             dev_fixture=config.DEV_FIXTURE_CORPUS)
        rekeyed = rekey_forecasts(conn)
        if rekeyed:
            log(f"Re-keyed {rekeyed} forecast cells with the current instrument rules")
        log("Building specialist collections ...")
        stats = indexer.build_collections(conn, start.isoformat(), end.isoformat(),
                                          include_fixtures=config.DEV_FIXTURE_CORPUS, log=log)
        summary = build_summary(conn, run_id, stats)
        conn.execute("UPDATE runs SET status='completed', finished_at=?, summary=? WHERE run_id=?",
                     (now_sgt().isoformat(), json.dumps(summary), run_id))
        store.set_state(conn, "active_window", {"start": start.isoformat(), "end": end.isoformat(), "days": days,
                                                "expanded": expanded, "label": fmt_range(start, end)})
        store.set_state(conn, "last_successful_run", {"run_id": run_id, "finished_at": now_sgt().isoformat()})
        conn.commit()
        log(f"Ingestion complete: {summary['counts']}")
        return summary
    except Exception as exc:  # noqa: BLE001
        conn.execute("UPDATE runs SET status='interrupted', error=? WHERE run_id=?",
                     (f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}", run_id))
        conn.commit()
        raise
    finally:
        if own_fetcher:
            fetcher.close()
        conn.close()


def rekey_forecasts(conn) -> int:
    """Recompute instrument keys and routing for stored forecast cells, so
    changes to the instrument rules apply to documents ingested earlier."""
    from app.common.instruments import instrument_key
    changed = 0
    with conn:
        for r in conn.execute("SELECT record_id, instrument_label, instrument_key, specialists FROM forecast_records").fetchall():
            key = instrument_key(r["instrument_label"])
            specs = json.dumps(chunking.forecast_key_specialists(key))
            if key != r["instrument_key"] or specs != r["specialists"]:
                conn.execute("UPDATE forecast_records SET instrument_key=?, specialists=? WHERE record_id=?",
                             (key, specs, r["record_id"]))
                changed += 1
    return changed


def reindex(log=print) -> dict:
    """Re-key forecast cells and rebuild the specialist collections for the
    active window, without contacting the OCBC website."""
    conn = store.connect(config.META_DB)
    try:
        window = store.get_state(conn, "active_window")
        if not window:
            raise RuntimeError("no active window yet; run a normal ingestion first")
        log(f"Re-keyed {rekey_forecasts(conn)} forecast cells")
        log(f"Rebuilding collections for {window['start']} to {window['end']} ...")
        stats = indexer.build_collections(conn, window["start"], window["end"],
                                          include_fixtures=config.DEV_FIXTURE_CORPUS, log=log)
        return {"window": window, "collections": stats}
    finally:
        conn.close()


def build_summary(conn, run_id: str, stats: dict | None = None) -> dict:
    run = dict(conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())
    items = [dict(r) for r in conn.execute("SELECT * FROM run_items WHERE run_id=?", (run_id,))]
    counts: dict[str, int] = {}
    for it in items:
        counts[it["state"]] = counts.get(it["state"], 0) + 1
    checks = [dict(r) for r in conn.execute("SELECT * FROM section_checks WHERE run_id=?", (run_id,))]
    failed_checks = [c for c in checks if c["status"] == "failed"]
    return {
        "run_id": run_id, "window_start": run["window_start"], "window_end": run["window_end"],
        "window_days": run["window_days"], "expanded": bool(run["expanded"]),
        "discovered": len(items), "counts": counts,
        "sections_checked": len(checks), "sections_failed": len(failed_checks),
        "complete": not failed_checks and not any(it["state"] in ("failed_download", "inaccessible", "parse_failed",
                                                                   "invalid_pdf") for it in items),
        "collections": stats or {},
    }
