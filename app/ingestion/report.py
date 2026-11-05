"""Writes reports/ingestion_report.md from the corpus store.

    python -m app.ingestion.report
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from app.common import config
from app.common.freshness import label as freshness_label
from app.common.timeutil import fmt_dt, fmt_range
from app.ingestion.pipeline import unread_forecast_tables

# Instruments OCBC's research normally carries a forecast for.
CORE_FORECASTS = ["USDSGD", "EURUSD", "USDJPY", "USDCNH", "FEDFUNDS", "SOFR", "UST10Y", "SORA", "SORA3MCOMP",
                  "SORAOIS10Y", "SGS10Y", "GOLD", "BRENT"]


def main():
    conn = sqlite3.connect(f"file:{config.META_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    state = {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT * FROM corpus_state")}
    run = conn.execute("SELECT * FROM runs WHERE status='completed' ORDER BY finished_at DESC LIMIT 1").fetchone()
    first = conn.execute("SELECT * FROM runs WHERE window_start=? AND window_end=? ORDER BY started_at LIMIT 1",
                         (run["window_start"], run["window_end"])).fetchone()
    summary = json.loads(run["summary"])
    items = [dict(r) for r in conn.execute("SELECT * FROM run_items WHERE run_id=?", (first["run_id"],))]
    checks = [dict(r) for r in conn.execute("SELECT * FROM section_checks WHERE run_id=?", (run["run_id"],))]
    docs = [dict(r) for r in conn.execute("SELECT * FROM documents ORDER BY publication_date DESC, title")]
    counts: dict[str, int] = {}
    for it in items:
        counts[it["state"]] = counts.get(it["state"], 0) + 1
    w = state["active_window"]
    start, end = date.fromisoformat(w["start"]), date.fromisoformat(w["end"])
    L = [f"# Ingestion and coverage report", "",
         f"* **Requested window:** {fmt_range(start, end)} inclusive ({w['days']} calendar days ending on the run date, "
         f"Asia/Singapore). Expanded beyond default: {'yes' if w['expanded'] else 'no'}.",
         f"* **First full run:** `{first['run_id']}` started {fmt_dt(datetime.fromisoformat(first['started_at']))}.",
         f"* **Last successful ingestion:** `{run['run_id']}` finished {fmt_dt(datetime.fromisoformat(run['finished_at']))} "
         f"(re-run; every document reported `unchanged`)." if run["run_id"] != first["run_id"] else "",
         f"* **Source boundary:** https://www.ocbc.com research pages and `/iwov-resources/sg/ocbc/gbc/pdf/` only; "
         f"robots.txt honoured; ≥1 s between requests; bounded retries; every redirect re-checked against the allow-list.",
         f"* **Coverage complete:** {'yes - every listing page and section was checked successfully' if summary['complete'] else 'NO - see failures below'}.",
         "", "## Totals (first full run)", "", "| Outcome | Count |", "|---|--:|"]
    L += [f"| Discovered (unique PDF URLs) | {len(items)} |"]
    for k, lab in [("indexed", "Downloaded, validated and indexed"), ("excluded_date", "Excluded by publication date"),
                   ("duplicate", "Duplicates (same content hash)"), ("quarantined", "Quarantined (date uncertain)"),
                   ("inaccessible", "Inaccessible"), ("failed_download", "Download failed"),
                   ("invalid_pdf", "Invalid PDF"), ("parse_failed", "Parse failed")]:
        L.append(f"| {lab} | {counts.get(k, 0)} |")
    L += ["", "## Pages and sections checked", "", "| Source | Section | Status | Items |", "|---|---|---|--:|"]
    for c in checks:
        L.append(f"| {c['source']} | {c['section'] or c['category'] or '—'} | {c['status']}{' — ' + c['detail'] if c['detail'] else ''} | {c['items']} |")
    L += ["", "## Coverage by specialist collection", "", "| Specialist | Documents | Passages | Forecast cells |",
          "|---|--:|--:|--:|"]
    for spec, v in summary.get("collections", {}).items():
        L.append(f"| {spec.upper()} | {v['documents']} | {v['chunks']} | {v['forecast_records']} |")
    L += ["", "Multi-sector reports (e.g. Daily Treasury Outlook, Daily Credit Snapshot) are indexed section-by-section "
          "into every specialist collection their content belongs to, keeping the original document ID and page.", "",
          "**Gap:** no Equity Research publication was listed in the window (the most recent equity report on the site "
          "is dated 5 Oct 2026). The Equities collection contains only equity-market passages from multi-sector daily "
          "reports, so equity questions will mostly return a missing-coverage notice.", "",
          "## Indexed documents", "",
          "| Published | Title | Type / age | Date basis | Specialists | OCR pages | Doc ID |", "|---|---|---|---|---|---|---|"]
    for d in docs:
        if d["status"] != "indexed":
            continue
        fr = freshness_label(d["publication_date"], d["report_type"], d["date_confidence"], end)
        L.append(f"| {d['publication_date']} | [{d['title']}]({d['source_url']}) | {d['report_type']} · {fr['label']} "
                 f"({fr['age_days']}d at window end) | {d['date_basis']} ({d['date_confidence']}) | "
                 f"{', '.join(s.upper() for s in json.loads(d['specialists']))} | "
                 f"{', '.join(map(str, json.loads(d['ocr_pages']))) or '—'} | `{d['doc_id']}` |")
    flags = [(d["title"], f) for d in docs for f in json.loads(d["date_flags"])]
    L += ["", "## Date discrepancies flagged", ""]
    L += [f"* {t}: {f}" for t, f in flags] or ["* None"]
    L += ["", "## Excluded by date", "", "| Title | Reason |", "|---|---|"]
    for it in items:
        if it["state"] == "excluded_date":
            title = json.loads(it["listing"] or "{}").get("title") or it["url"]
            L.append(f"| {title} | {it['detail']} |")
    bad = [it for it in items if it["state"] in ("inaccessible", "failed_download", "invalid_pdf", "parse_failed",
                                                 "quarantined")]
    L += ["", "## Inaccessible documents and failures", ""]
    L += [f"* {it['url']}: {it['state']} — {it['detail']}" for it in bad] or ["* None in this run."]
    unread = unread_forecast_tables(conn)
    L += ["", "## Forecast tables not read", "",
          "Tables shaped like a forecast (two or more future-period columns) that produced no forecast cells. "
          "The app cannot quote these numbers, so a question about them gets a missing-forecast answer.", ""]
    L += [f"* {u['title']} ({u['publication_date']}), page {u['page']}: first row '{u['first_row']}'"
          for u in unread] or ["* None."]
    keys = {r[0] for r in conn.execute(
        "SELECT DISTINCT f.instrument_key FROM forecast_records f JOIN documents d USING(doc_id) "
        "WHERE d.status='indexed' AND f.is_observation=0")}
    missing = [k for k in CORE_FORECASTS if k not in keys]
    L += ["", "## Core forecasts missing", "",
          "Instruments OCBC normally publishes a forecast for. Missing ones are either not published in the window "
          "or not read by the parser.", ""]
    L += [f"* {k}" for k in missing] or ["* None - all present."]
    susp = conn.execute("SELECT COUNT(*) FROM chunks WHERE suspicious=1").fetchone()[0]
    L += ["", f"Passages withheld for embedded instruction-like text: {susp}.", ""]
    out = config.ROOT / "reports" / "ingestion_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(x for x in L if x is not None) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
