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


def test_window_and_counts(conn):
    state = {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT * FROM corpus_state")}
    w = state["active_window"]
    assert w["days"] == 7 and not w["expanded"]
    docs = conn.execute("SELECT * FROM documents WHERE status='indexed'").fetchall()
    assert len(docs) >= 20
    for d in docs:
        assert w["start"] <= d["publication_date"] <= w["end"]
        assert d["dev_fixture"] == 0
        assert d["source_url"].startswith("https://www.ocbc.com/iwov-resources/sg/ocbc/gbc/pdf/")


def test_dates_listing_and_printed_agree(conn):
    for d in conn.execute("SELECT * FROM documents WHERE status='indexed'"):
        assert d["date_confidence"] == "high", d["title"]
        assert d["listing_date"] == d["printed_date"] == d["publication_date"]


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
    got = {(r["horizon_label"], r["value"]) for r in conn.execute(
        "SELECT horizon_label, value FROM forecast_records WHERE instrument_label='USD-SGD' AND is_observation=0")}
    assert got == {("Dec-26", "1.2700"), ("Mar-27", "1.2670"), ("Jun-27", "1.2630"), ("Sep-27", "1.2610"),
                   ("Dec-27", "1.2550")}
    spot = conn.execute("SELECT value, horizon_label FROM forecast_records WHERE instrument_label='USD-SGD' "
                        "AND is_observation=1").fetchall()
    assert [(s["value"], s["horizon_label"]) for s in spot] == [("1.2773", "Current (25 Sep)")]


def test_forecast_data_date_and_footnotes_preserved(conn):
    r = conn.execute("SELECT data_date, footnotes FROM forecast_records WHERE instrument_label='USD-SGD' LIMIT 1").fetchone()
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


def test_rate_named_only_in_market_moves_is_explained():
    """SORA appears only in daily curve-move notes; TONA not at all. Each is reported separately."""
    import subprocess
    import sys
    code = ("from app.research.collections import CollectionRegistry\n"
            "from app.research import specialists as S\n"
            "from app.orchestrator import planner\n"
            "W=('2026-10-26','2026-11-01')\n"
            "p=planner.plan_request('tell me sora and tona forecast to 2027',None,W)\n"
            "t=planner.build_tasks(p,W,False)[0]\n"
            "r=S.Specialist('rates',CollectionRegistry(),S.CorpusStatus()).run(t)\n"
            "import json; print(json.dumps([c.detail for c in r.coverage]))")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=300)
    details = json.loads(out.stdout.strip().splitlines()[-1])
    assert any(d.startswith("SORA is mentioned in") and "past market moves" in d for d in details)
    assert any(d.startswith("No passage mentioning TONA") for d in details)
