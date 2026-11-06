"""Pipeline scenarios exercised against synthetic fixtures in an isolated
temporary corpus (see tests/fixtures). Runs tests/fixture_pipeline.py in a
subprocess so the real data directory is never touched."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def run():
    tmp = tempfile.mkdtemp(prefix="ra-fixture-")
    env = dict(os.environ, RA_DATA_DIR=str(Path(tmp) / "data"), RA_DEV_FIXTURE_CORPUS="1",
               RA_EVIDENCE_SIGNING_KEY="fixture-key", HF_HUB_OFFLINE="1")
    proc = subprocess.run([sys.executable, "-m", "tests.fixture_pipeline"], cwd=ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    assert proc.returncode == 0, proc.stderr[-3000:]
    return json.loads(proc.stdout)


def by_state(items):
    out = {}
    for it in items:
        out.setdefault(it["state"], []).append(it["url"].rsplit("/", 1)[-1])
    return out


def test_ingestion_outcomes_are_recorded(run):
    states = by_state(run["first_items"])
    assert "conflictdate.pdf" in states["quarantined"]          # listing vs printed date conflict
    assert "duplicate-copy.pdf" in states["duplicate"]          # same content hash
    assert "forbidden.pdf" in states["inaccessible"]            # HTTP 403
    assert "notapdf.pdf" in states["invalid_pdf"]               # HTML served with .pdf name
    assert "old.pdf" in states["excluded_date"]                 # outside window, not downloaded
    assert set(states["indexed"]) == {"older.pdf", "newer.pdf", "samedate.pdf", "scanned.pdf", "malicious.pdf"}


def test_unavailable_section_makes_coverage_incomplete(run):
    assert run["summary"]["complete"] is False
    assert any("Credit Research listing" in s["source"] for s in run["section_failures"])
    credit = run["credit"]
    assert any("could not be checked" in lim for lim in credit["limitations"])
    assert credit["status"] == "no_evidence" and not credit["findings"]


def test_rerun_is_idempotent(run):
    assert run["rerun_counts"].get("unchanged") == 5
    assert "indexed" not in run["rerun_counts"]
    assert run["table_counts"]["documents"] == 6  # 5 indexed + 1 quarantined, no duplicates


def test_fixtures_flagged_and_isolated(run):
    assert all(d["dev_fixture"] == 1 for d in run["documents"])


def test_scanned_page_ocr_flagged(run):
    scanned = next(d for d in run["documents"] if "Scanned" in d["title"])
    assert json.loads(scanned["ocr_pages"]) == [1]
    assert any("Singapore GDP growth" in c["text"] for c in run["ocr_chunks"])
    macro = run["macro"]
    assert macro["findings"] and all(e["ocr"] for e in macro["evidence"])
    assert any("OCR" in lim for lim in macro["limitations"])


def test_embedded_instructions_withheld(run):
    assert run["suspicious"] and "Ignore all previous instructions" in run["suspicious"][0]["suspicious_reason"]
    for spec in ("fx", "credit", "macro"):
        for f in run[spec]["findings"]:
            assert "Ignore all previous" not in f["statement"] and "XYZ" not in f["statement"]


def test_unresolved_conflict_shows_both_values(run):
    fx = run["fx"]
    dec26 = sorted(f["value"] for f in fx["forecasts"] if f["horizon_label"] == "Dec-26")
    assert dec26 == ["1.2700", "1.2900"]
    assert [c["resolution"] for c in fx["conflicts"]] == ["unresolved"]


def test_revision_latest_applies_with_basis(run):
    eur = run["eur"]
    assert {f["horizon_label"]: f["value"] for f in eur["forecasts"]} == {
        "Dec-26": "1.14", "Mar-27": "1.13", "Jun-27": "1.13", "Dec-27": "1.15"}
    assert eur["conflicts"] and all(c["resolution"] == "latest_publication_applies" for c in eur["conflicts"])
    assert "15 Oct 2026" in eur["conflicts"][0]["description"]  # older source retained in the explanation


def test_pair_never_inverted(run):
    inv = run["inverse"]
    assert inv["forecasts"] == []
    assert any("not inverted" in m for m in inv["missing_coverage"])


def test_semantic_fallback_disclosed(run):
    # The isolated corpus has no embedding model: lexical retrieval continues and says so.
    assert any("semantic retrieval disabled" in lim for lim in run["fx"]["limitations"])


def test_validator_blocks_unsupported_content(run):
    v = run["validator"]
    assert v["claims"]["ok"] is True
    for cid in ("badnum", "inverted", "reco", "uncited", "unsupported"):
        assert v["claims"][cid] is False, cid
    assert v["rows"] == {"R1": True, "R2": False}  # tampered value rejected
    assert v["forged"]["ok"] is False
    assert any("signature invalid" in p for p in v["forged"]["problems"]["E-forged"])
