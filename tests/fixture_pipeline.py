"""Runs the full ingestion + specialist + validator pipeline against the
offline fixture site in an ISOLATED temporary data directory and prints a
JSON report. Invoked as a subprocess by tests/test_fixture_scenarios.py with
RA_DATA_DIR pointing at a temp dir and RA_DEV_FIXTURE_CORPUS=1."""
from __future__ import annotations

import json
import os
import sys
from datetime import date

assert os.environ.get("RA_DEV_FIXTURE_CORPUS") == "1", "fixture runner must use an isolated fixture corpus"

from app.common import config  # noqa: E402

assert "research agent" not in str(config.DATA_DIR) or "tmp" in str(config.DATA_DIR).lower() \
    or "temp" in str(config.DATA_DIR).lower(), "refusing to run fixtures against the real data directory"

from app.common.schemas import (Claim, CorpusConstraints, DraftAnswer, EvidenceBundle, SpecialistTask,  # noqa: E402
                                TableRow)
from app.ingestion.fetcher import Fetcher  # noqa: E402
from app.ingestion.pipeline import run_ingestion  # noqa: E402
from app.research.collections import CollectionRegistry  # noqa: E402
from app.research.specialists import CorpusStatus, Specialist  # noqa: E402
from app.validator.checks import Validator  # noqa: E402
from tests.fixtures.fixture_site import build_site  # noqa: E402

TODAY = date(2026, 11, 1)


def main():
    out = {}
    fetcher = Fetcher(min_interval=0, max_retries=1, transport=build_site(fail_credit_listing=True))
    summary = run_ingestion(fetcher=fetcher, today=TODAY, log=lambda *_: None, trigger="test")
    out["summary"] = {k: v for k, v in summary.items() if k != "collections"}
    # Second run: idempotency
    fetcher2 = Fetcher(min_interval=0, max_retries=1, transport=build_site(fail_credit_listing=True))
    summary2 = run_ingestion(fetcher=fetcher2, today=TODAY, log=lambda *_: None, trigger="test-rerun")
    out["rerun_counts"] = summary2["counts"]

    import sqlite3
    conn = sqlite3.connect(config.META_DB)
    conn.row_factory = sqlite3.Row
    out["documents"] = [dict(r) for r in conn.execute(
        "SELECT doc_id,title,status,status_detail,publication_date,date_confidence,date_flags,ocr_pages,dev_fixture,alias_urls "
        "FROM documents")]
    out["items"] = [dict(r) for r in conn.execute(
        "SELECT url,state,detail FROM run_items WHERE run_id=?", (summary2["run_id"],))]
    out["first_items"] = [dict(r) for r in conn.execute(
        "SELECT url,state,detail FROM run_items WHERE run_id=?", (summary["run_id"],))]
    out["section_failures"] = [dict(r) for r in conn.execute("SELECT source,status,detail FROM section_checks "
                                                              "WHERE status='failed'")]
    out["suspicious"] = [dict(r) for r in conn.execute("SELECT doc_id,suspicious_reason FROM chunks WHERE suspicious=1")]
    out["ocr_chunks"] = [dict(r) for r in conn.execute("SELECT doc_id,text FROM chunks WHERE ocr=1")]
    out["table_counts"] = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                           for t in ("documents", "chunks", "forecast_records", "pages")}

    reg = CollectionRegistry()
    status = CorpusStatus()
    corpus = CorpusConstraints(window_start="2026-10-26", window_end="2026-11-01")
    fx = Specialist("fx", reg, status).run(SpecialistTask(
        task_id="T1", specialist="fx", original_question="USD/SGD forecast through 2027", objective="forecasts",
        instruments=["USDSGD"], currencies=["USD", "SGD"], horizon="through 2027", horizon_years=[2027],
        info_types=["forecast", "rationale", "risks"], corpus=corpus))
    out["fx"] = fx.model_dump()
    eur = Specialist("fx", reg, status).run(SpecialistTask(
        task_id="T4", specialist="fx", original_question="EUR/USD forecast", objective="forecasts",
        instruments=["EURUSD"], currencies=["EUR", "USD"], info_types=["forecast"], corpus=corpus))
    out["eur"] = eur.model_dump()
    inverse = Specialist("fx", reg, status).run(SpecialistTask(
        task_id="T5", specialist="fx", original_question="SGD/USD forecast", objective="forecasts",
        instruments=["SGDUSD"], currencies=["SGD", "USD"], info_types=["forecast"], corpus=corpus))
    out["inverse"] = inverse.model_dump()
    credit = Specialist("credit", reg, status).run(SpecialistTask(
        task_id="T2", specialist="credit", original_question="main credit risks", objective="credit risks",
        info_types=["risks", "rationale"], corpus=corpus))
    out["credit"] = credit.model_dump()
    macro = Specialist("macro", reg, status).run(SpecialistTask(
        task_id="T3", specialist="macro", original_question="Singapore GDP outlook", objective="Singapore growth",
        countries=["SG"], info_types=["rationale", "risks"], corpus=corpus))
    out["macro"] = macro.model_dump()

    # Validator checks on the fixture bundle
    v = Validator()
    bundle = EvidenceBundle(evidence=fx.evidence, forecasts=fx.forecasts)
    f0 = fx.forecasts[0]
    good = TableRow(row_id="R1", instrument_label=f0.instrument_label, instrument_key=f0.instrument_key,
                    horizon_label=f0.horizon_label, value=f0.value, unit=f0.unit, scenario=f0.scenario,
                    record_id=f0.record_id, evidence_id=f0.evidence_id)
    tampered = good.model_copy(update={"row_id": "R2", "value": "1.2500"})
    ev = fx.evidence[0]
    claims = [
        Claim(claim_id="ok", section="direct", text=f"Published {f0.instrument_label} forecast {f0.horizon_label}: {f0.value}.",
              evidence_ids=[f0.evidence_id], mode="template"),
        Claim(claim_id="badnum", section="direct", text=f"{f0.instrument_label} is forecast at 1.3333 by Dec-27.",
              evidence_ids=[f0.evidence_id], mode="template"),
        Claim(claim_id="inverted", section="direct", text=f"SGD/USD is forecast at {f0.value}.",
              evidence_ids=[f0.evidence_id], mode="template"),
        Claim(claim_id="reco", section="rationale", text="Clients should buy USD-SGD on dips.",
              evidence_ids=[f0.evidence_id], mode="summary"),
        Claim(claim_id="uncited", section="rationale", text="The SGD will appreciate.", evidence_ids=[], mode="summary"),
        Claim(claim_id="unsupported", section="rationale",
              text="OCBC expects a sharp recession in Europe driven by a banking crisis.",
              evidence_ids=[ev.evidence_id], mode="summary"),
    ]
    report = v.validate(DraftAnswer(question="q", claims=claims, table_rows=[good, tampered]), bundle)
    out["validator"] = {"claims": {c.claim_id: c.ok for c in report.claims},
                        "claim_reasons": {c.claim_id: c.reasons for c in report.claims},
                        "rows": {r.row_id: r.ok for r in report.rows}}
    forged = ev.model_copy(update={"evidence_id": "E-forged", "excerpt": "OCBC forecasts USD-SGD at 1.1000 for Dec-27."})
    rep2 = v.validate(DraftAnswer(question="q", claims=[Claim(claim_id="forged", section="direct",
                                                               text="OCBC forecasts USD-SGD at 1.1000 for Dec-27.",
                                                               evidence_ids=["E-forged"], mode="verbatim")]),
                      EvidenceBundle(evidence=[forged]))
    out["validator"]["forged"] = {"ok": rep2.claims[0].ok, "problems": rep2.evidence_problems}
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    sys.exit(main())
