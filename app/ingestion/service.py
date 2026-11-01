"""Ingestion worker + administration API (port 8104).

The only process allowed to reach the OCBC website. Exposes (admin token,
injected by the gateway):
  GET  /v1/status    corpus/coverage report for the administration view
  POST /v1/ingest    start an incremental refresh (optionally an explicit wider window)
  GET/PUT /v1/schedule  configurable refresh schedule (cron, SGT)
"""
from __future__ import annotations

import json
import threading
import traceback

from fastapi import Body, Depends, FastAPI, HTTPException

from app.ingestion.policy import install_ingestion_guard

install_ingestion_guard()

from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402
from apscheduler.triggers.cron import CronTrigger  # noqa: E402

from app.common import config, embedding  # noqa: E402
from app.common.freshness import label as freshness_label, policy as freshness_policy  # noqa: E402
from app.common.security import require_token  # noqa: E402
from app.common.timeutil import SGT, fmt_range, now_sgt  # noqa: E402
from app.ingestion import store  # noqa: E402
from app.ingestion.pipeline import run_ingestion  # noqa: E402

app = FastAPI(title="Ingestion service", docs_url=None, redoc_url=None, openapi_url=None)
auth = require_token(config.TOKEN_ADMIN)
_job_lock = threading.Lock()
_job = {"running": False, "log": [], "started_at": None, "error": None}
scheduler = BackgroundScheduler(timezone=SGT)


def _log(msg: str):
    _job["log"] = (_job["log"] + [f"{now_sgt().strftime('%H:%M:%S')} {msg}"])[-300:]


def _run(days: int | None, trigger: str):
    if not _job_lock.acquire(blocking=False):
        return False
    _job.update(running=True, log=[], started_at=now_sgt().isoformat(), error=None)

    def work():
        try:
            run_ingestion(days=days, trigger=trigger, log=_log)
        except Exception as exc:  # noqa: BLE001
            _job["error"] = f"{type(exc).__name__}: {exc}"
            _log(traceback.format_exc()[-800:])
        finally:
            _job["running"] = False
            _job_lock.release()

    threading.Thread(target=work, daemon=True).start()
    return True


def _apply_schedule(cron: str | None):
    for j in scheduler.get_jobs():
        j.remove()
    if cron:
        scheduler.add_job(lambda: _run(None, "scheduled"), CronTrigger.from_crontab(cron, timezone=SGT), id="refresh")


@app.on_event("startup")
def startup():
    conn = store.connect(config.META_DB)
    cron = store.get_state(conn, "schedule_cron", config.INGEST_SCHEDULE_CRON or "")
    conn.close()
    scheduler.start()
    if config.PUBLIC_MODE:
        return  # hosted demo: read-only corpus, no crawling and no scheduled refresh
    try:
        _apply_schedule(cron)
    except ValueError:
        _apply_schedule(None)


@app.get("/v1/health")
def health():
    return {"ok": True, "running": _job["running"]}


@app.get("/v1/status", dependencies=[Depends(auth)])
def status():
    conn = store.connect(config.META_DB)
    try:
        active = store.get_state(conn, "active_window")
        last_ok = store.get_state(conn, "last_successful_run")
        latest = conn.execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        run_id = latest["run_id"] if latest else None
        checks = [dict(r) for r in conn.execute("SELECT source,category,section,status,items,detail FROM section_checks "
                                                "WHERE run_id=?", (run_id,))] if run_id else []
        items = [dict(r) for r in conn.execute("SELECT url,state,detail,listing,doc_id FROM run_items WHERE run_id=? "
                                               "ORDER BY state, url", (run_id,))] if run_id else []
        for it in items:
            listing = json.loads(it.pop("listing") or "{}")
            it.update(title=listing.get("title"), listing_date=listing.get("listing_date"),
                      category=listing.get("category"), section=listing.get("section"))
        docs = [dict(r) for r in conn.execute(
            "SELECT doc_id,title,category,section,report_type,source_url,alias_urls,listing_date,printed_date,meta_date,"
            "publication_date,date_confidence,date_basis,date_flags,page_count,status,status_detail,specialists,ocr_pages,"
            "dev_fixture FROM documents ORDER BY publication_date DESC")]
        for d in docs:
            for k in ("alias_urls", "date_flags", "specialists", "ocr_pages"):
                d[k] = json.loads(d[k] or "[]")
            d["freshness"] = freshness_label(d["publication_date"], d["report_type"], d["date_confidence"])
        suspicious = [dict(r) for r in conn.execute(
            "SELECT c.doc_id, d.title, c.pdf_page, c.suspicious_reason FROM chunks c JOIN documents d USING(doc_id) "
            "WHERE c.suspicious=1")]
        counts: dict[str, int] = {}
        for it in items:
            counts[it["state"]] = counts.get(it["state"], 0) + 1
        pointer_path = config.COLLECTIONS_DIR / "current.json"
        coverage = json.loads(latest["summary"] or "{}").get("collections", {}) if latest else {}
        schedule = store.get_state(conn, "schedule_cron", config.INGEST_SCHEDULE_CRON or "")
        next_run = scheduler.get_job("refresh").next_run_time.isoformat() if scheduler.get_job("refresh") else None
        return {
            "now": now_sgt().isoformat(),
            "active_window": active, "last_successful_run": last_ok,
            "latest_run": dict(latest) | {"summary": json.loads(latest["summary"] or "{}")} if latest else None,
            "requested_window_label": fmt_range(*(map(lambda s: __import__("datetime").date.fromisoformat(s),
                                                      (latest["window_start"], latest["window_end"])))) if latest else None,
            "counts": counts, "section_checks": checks, "items": items, "documents": docs,
            "suspicious_passages": suspicious, "coverage": coverage,
            "collections_build": json.loads(pointer_path.read_text()) if pointer_path.exists() else None,
            "freshness_policy": freshness_policy(),
            "schedule": {"cron": schedule, "timezone": "Asia/Singapore", "next_run": next_run},
            "job": _job, "semantic_retrieval": embedding.available(),
            "default_window_days": config.INGEST_WINDOW_DAYS, "public_mode": config.PUBLIC_MODE,
        }
    finally:
        conn.close()


@app.post("/v1/ingest", dependencies=[Depends(auth)])
def ingest(payload: dict = Body(default={})):
    if config.PUBLIC_MODE:
        raise HTTPException(403, "ingestion is disabled in public mode")
    days = payload.get("days")
    if days is not None:
        days = int(days)
        if not 1 <= days <= 90:
            raise HTTPException(400, "days must be between 1 and 90")
    if not _run(days, "admin"):
        raise HTTPException(409, "an ingestion run is already in progress")
    return {"started": True, "days": days or config.INGEST_WINDOW_DAYS,
            "expanded": bool(days and days != config.INGEST_WINDOW_DAYS)}


@app.get("/v1/schedule", dependencies=[Depends(auth)])
def get_schedule():
    conn = store.connect(config.META_DB)
    try:
        return {"cron": store.get_state(conn, "schedule_cron", config.INGEST_SCHEDULE_CRON or "")}
    finally:
        conn.close()


@app.put("/v1/schedule", dependencies=[Depends(auth)])
def put_schedule(payload: dict = Body(...)):
    if config.PUBLIC_MODE:
        raise HTTPException(403, "scheduling is disabled in public mode")
    cron = (payload.get("cron") or "").strip()
    try:
        _apply_schedule(cron or None)
    except ValueError as exc:
        raise HTTPException(400, f"invalid cron expression: {exc}")
    conn = store.connect(config.META_DB)
    try:
        store.set_state(conn, "schedule_cron", cron)
        conn.commit()
    finally:
        conn.close()
    return {"cron": cron}
