"""Read-only checks against the real ingested OCBC corpus (skipped if absent)."""
import json
import re
import sqlite3
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "corpus" / "corpus.db"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="real corpus not ingested")


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# These tests check rules against whatever corpus is currently ingested (any
# window). Checks tied to a specific report use FX_WEEKLY_26OCT and skip if it
# is not in the active window.
FX_WEEKLY_26OCT = "ocbc-87b1953be8a6"


def _window(conn):
    state = {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT * FROM corpus_state")}
    return state["active_window"]


def _in_window(conn, doc_id):
    w = _window(conn)
    d = conn.execute("SELECT status, publication_date FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
    return d is not None and d["status"] == "indexed" and w["start"] <= d["publication_date"] <= w["end"]


def test_window_and_counts(conn):
    from datetime import date
    w = _window(conn)
    span = (date.fromisoformat(w["end"]) - date.fromisoformat(w["start"])).days + 1
    assert span == w["days"]
    docs = conn.execute("SELECT * FROM documents WHERE status='indexed' AND publication_date BETWEEN ? AND ?",
                        (w["start"], w["end"])).fetchall()
    assert len(docs) >= 20
    for d in docs:
        assert d["dev_fixture"] == 0
        if d["source_url"].startswith("manual:"):  # added with --add-pdf; must say so
            assert "added manually" in (d["status_detail"] or "")
        else:
            assert d["source_url"].startswith("https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/")


def test_dates_follow_resolution_rule(conn):
    """Indexed documents are never low-confidence; high means listing and printed
    dates agree; anything less carries a flag explaining why."""
    for d in conn.execute("SELECT * FROM documents WHERE status='indexed'"):
        assert d["date_confidence"] in ("high", "medium"), d["title"]
        if d["date_confidence"] == "high" and d["printed_date"]:
            assert d["listing_date"] == d["printed_date"] == d["publication_date"], d["title"]
        if d["date_confidence"] == "medium":
            assert json.loads(d["date_flags"]), d["title"]
    for d in conn.execute("SELECT * FROM documents WHERE status='quarantined'"):
        assert d["publication_date"] is None and json.loads(d["date_flags"])


def test_stale_metadata_title_flagged(conn):
    flagged = [d for d in conn.execute("SELECT title, date_flags FROM documents") if "23 Apr 2026" in d["date_flags"]]
    assert flagged, "DMO whose PDF metadata title says 'DMO 23 Apr 2026' should be flagged"


def test_forecast_values_match_source_page_exactly(conn):
    """Every USD-SGD forecast cell must appear on its source page, on the same
    line as the instrument label, in the original precision."""
    recs = conn.execute("SELECT f.*, d.sha256 FROM forecast_records f JOIN documents d USING(doc_id) "
                        "WHERE instrument_key='USDSGD'").fetchall()
    assert recs
    for r in recs:
        page = fitz.open(ROOT / "data" / "corpus" / "raw" / f"{r['sha256']}.pdf")[r["pdf_page"] - 1]
        words = page.get_text("words")
        label_words = [w for w in words if w[4] == r["instrument_label"]]
        assert label_words, r["instrument_label"]
        y = (label_words[0][1] + label_words[0][3]) / 2
        row = [w[4] for w in words if abs((w[1] + w[3]) / 2 - y) < 3]
        assert r["value"] in row, (r["instrument_label"], r["horizon_label"], r["value"], row)


def test_known_usdsgd_values(conn):
    if not _in_window(conn, FX_WEEKLY_26OCT):
        pytest.skip("FX Weekly 26 Oct 2026 not in the active window")
    got = {(r["horizon_label"], r["value"]) for r in conn.execute(
        "SELECT horizon_label, value FROM forecast_records WHERE instrument_label='USD-SGD' AND is_observation=0 "
        "AND doc_id=?", (FX_WEEKLY_26OCT,))}
    assert got == {("Dec-26", "1.2700"), ("Mar-27", "1.2670"), ("Jun-27", "1.2630"), ("Sep-27", "1.2610"),
                   ("Dec-27", "1.2550")}
    spot = conn.execute("SELECT value, horizon_label FROM forecast_records WHERE instrument_label='USD-SGD' "
                        "AND is_observation=1 AND doc_id=?", (FX_WEEKLY_26OCT,)).fetchall()
    assert [(s["value"], s["horizon_label"]) for s in spot] == [("1.2773", "Current (25 Sep)")]


def test_forecast_data_date_and_footnotes_preserved(conn):
    if not _in_window(conn, FX_WEEKLY_26OCT):
        pytest.skip("FX Weekly 26 Oct 2026 not in the active window")
    r = conn.execute("SELECT data_date, footnotes FROM forecast_records WHERE instrument_label='USD-SGD' AND doc_id=? "
                     "LIMIT 1", (FX_WEEKLY_26OCT,)).fetchone()
    assert r["data_date"] == "Latest Forecast Update: 25 September 2026"
    assert any("trajectory bias" in f for f in json.loads(r["footnotes"]))


def test_forecast_tables_not_split(conn):
    for c in conn.execute("SELECT text FROM chunks WHERE kind='table' AND text LIKE '%FX Forecasts%'"):
        lines = c["text"].split("\n")
        assert any(l.startswith("Instrument |") for l in lines)  # header travels with the values


def test_ocr_pages_flagged(conn):
    wmv = conn.execute("SELECT ocr_pages FROM documents WHERE title LIKE 'Weekly Macro View%'").fetchone()
    assert json.loads(wmv["ocr_pages"])


def test_collections_respect_routing():
    cur = json.loads((ROOT / "data" / "collections" / "current.json").read_text())
    for spec, fn in cur["files"].items():
        c = sqlite3.connect(f"file:{(ROOT / 'data' / 'collections' / fn).as_posix()}?mode=ro", uri=True)
        n = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        assert n > 0, spec
        if spec == "fx":
            assert c.execute("SELECT COUNT(*) FROM forecast_records WHERE instrument_key='USDSGD'").fetchone()[0] > 0
        if spec == "credit":
            assert c.execute("SELECT COUNT(*) FROM forecast_records WHERE instrument_key='USDSGD'").fetchone()[0] == 0
        c.close()


def test_no_double_counted_documents(conn):
    shas = [r[0] for r in conn.execute("SELECT sha256 FROM documents")]
    assert len(shas) == len(set(shas))
    urls = [r[0] for r in conn.execute("SELECT source_url FROM documents WHERE status='indexed'")]
    assert len(urls) == len(set(urls))


def test_each_requested_rate_is_accounted_for():
    """Every requested rate gets its own outcome (forecasts found, or an explicit
    "no verified forecast"), and conflicts only ever compare the same instrument."""
    import subprocess
    import sys
    code = ("from app.research.collections import CollectionRegistry\n"
            "from app.research import specialists as S\n"
            "from app.orchestrator import planner\n"
            "W=('2026-10-26','2026-11-01')\n"
            "p=planner.plan_request('tell me sora and tona forecast to 2027',None,W)\n"
            "t=planner.build_tasks(p,W,False)[0]\n"
            "r=S.Specialist('rates',CollectionRegistry(),S.CorpusStatus()).run(t)\n"
            "import json; print(json.dumps({'cov': [c.detail for c in r.coverage],"
            " 'found': sorted({f.instrument_key for f in r.forecasts}),"
            " 'conflicts': [sorted({f.instrument_label for f in r.forecasts if f.record_id in c.record_ids})"
            " for c in r.conflicts]}))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    for key in ("SORA", "TONA"):
        has_rows = any(k == key or k.startswith(key + "OIS") for k in res["found"])
        says_missing = any(f"verified forecast for {key}." in d for d in res["cov"])
        assert has_rows != says_missing, (key, res)
    for labels in res["conflicts"]:
        assert len(labels) <= 1, f"conflict mixes different instruments: {labels}"


RESEARCH_MONITOR_OCT = "ocbc-833b9346e8b6"


def test_research_monitor_rates_blocks_are_forecasts(conn):
    # The SGD block of the "Rates Forecast" box and the yield tables on the next page.
    if not _in_window(conn, RESEARCH_MONITOR_OCT):
        pytest.skip("Research Monitor (Oct) not in the active window")
    rows = {(r["instrument_key"], r["horizon_label"]): r["value"] for r in conn.execute(
        "SELECT instrument_key, horizon_label, value FROM forecast_records WHERE doc_id=?", (RESEARCH_MONITOR_OCT,))}
    assert rows[("SORA", "4Q26")] == "1.40" and rows[("SORA", "4Q27")] == "1.60"
    assert rows[("SORA3MCOMP", "4Q26")] == "1.38" and rows[("SORAOIS10Y", "4Q26")] == "2.70"
    assert rows[("SGS10Y", "4Q26")]
    assert not any(k.startswith("FOLLOWOURPODCASTS") for k, _ in rows)


def test_every_forecast_shaped_table_is_read(conn):
    from app.ingestion.pipeline import unread_forecast_tables
    assert unread_forecast_tables(conn) == []
