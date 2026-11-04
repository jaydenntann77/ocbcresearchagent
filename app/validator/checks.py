"""Deterministic answer validation against the evidence ledger and corpus.

The validator receives the draft answer plus the evidence bundle the
specialists returned. It re-checks every evidence item against the corpus
store (read-only) and every claim/row against the evidence. It returns only
verdicts and reasons - never corpus text."""
from __future__ import annotations

import re
import sqlite3

from app.common import config
from app.common.instruments import find_pairs
from app.common.schemas import (ClaimVerdict, DraftAnswer, EvidenceBundle, RowVerdict, ValidationReport)
from app.common.security import verify_evidence_signature

NUM_RE = re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?%?")
RECO_RE = re.compile(
    r"\b(we recommend|i recommend|you should|clients? should|consider (buying|selling)|buy|sell|go long|go short|"
    r"overweight|underweight|trade idea|accumulate|take profit|stop[- ]loss|entry level|target price)\b", re.I)
STOP = set("""the a an and or of to in on for with by from at as is are was were be been being this that these those it its
their there which who whom whose than then also into over under about after before between through during per not no
but if while because so such may might can could would should will shall has have had do does did ocbc research report
reports published publishes view views said says notes noted""".split())
TEMPLATE_WORDS = set("""forecast forecasts horizon horizons published latest ingested contains contain verified table tables
values value quarter quarters ending path through relative months month year years shows show listed provides provide
instrument pair pairs page pages trajectory bias update stated available corpus window""".split())
# The executive summary and table implication are client-facing commentary that
# translates research language, so they need less verbatim overlap. Their
# numbers, pair direction and recommendation language are checked as strictly.
CLIENT_SECTIONS = {"direct", "commentary"}
CLIENT_OVERLAP = 0.35
OVERLAP = 0.6
HOUSE_VOICE = set("""house expect expects expected retain retains view views outlook looking ahead remain remains
believe overall conclusion""".split())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ").replace("\xa0", " ")).strip()


def _words(s: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z][a-z'\-]+", s.lower()) if len(w) > 3 and w not in STOP}


class Validator:
    def __init__(self, db_path=None, signing_key: str | None = None):
        self.db_path = db_path or config.META_DB
        self.key = signing_key if signing_key is not None else (config.EVIDENCE_SIGNING_KEY or "unsigned")

    def _conn(self):
        conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def check_evidence(self, bundle: EvidenceBundle) -> dict[str, list[str]]:
        problems: dict[str, list[str]] = {}
        with self._conn() as conn:
            for ev in bundle.evidence:
                errs = []
                if not verify_evidence_signature(self.key, ev.model_dump()):
                    errs.append("evidence signature invalid (not issued by a specialist)")
                doc = conn.execute("SELECT * FROM documents WHERE doc_id=?", (ev.doc_id,)).fetchone()
                if not doc:
                    errs.append(f"document {ev.doc_id} does not exist")
                else:
                    if doc["status"] != "indexed":
                        errs.append(f"document {ev.doc_id} is not an indexed document ({doc['status']})")
                    if ev.pdf_page < 1 or ev.pdf_page > (doc["page_count"] or 0):
                        errs.append(f"page {ev.pdf_page} does not exist in {ev.doc_id}")
                    if ev.source_url != doc["source_url"]:
                        errs.append("source URL does not match the document record")
                    if (ev.publication_date or None) != (doc["publication_date"] or None):
                        errs.append("publication date does not match the document record")
                chunk = conn.execute("SELECT * FROM chunks WHERE chunk_id=?", (ev.chunk_id,)).fetchone() if ev.chunk_id else None
                if not chunk:
                    errs.append("cited passage does not exist")
                elif chunk["doc_id"] != ev.doc_id or chunk["pdf_page"] != ev.pdf_page:
                    errs.append("cited passage is not on the cited document page")
                else:
                    body = _norm(chunk["text"])
                    for line in ev.excerpt.split("\n"):
                        if _norm(line) and _norm(line) not in body:
                            errs.append("excerpt text not found verbatim on the cited page")
                            break
                if errs:
                    problems[ev.evidence_id] = errs
            for fv in bundle.forecasts:
                rec = conn.execute("SELECT * FROM forecast_records WHERE record_id=?", (fv.record_id,)).fetchone()
                errs = []
                if not rec:
                    errs.append("forecast record does not exist")
                else:
                    for field in ("instrument_label", "instrument_key", "horizon_label", "value"):
                        if str(rec[field]) != str(getattr(fv, field)):
                            errs.append(f"{field} '{getattr(fv, field)}' does not match source '{rec[field]}'")
                    if (rec["unit"] or None) != (fv.unit or None):
                        errs.append("unit does not match source")
                    if rec["is_observation"]:
                        errs.append("value is a spot/current observation, not a forecast")
                if errs:
                    problems[fv.record_id] = errs
        return problems

    def validate(self, draft: DraftAnswer, bundle: EvidenceBundle) -> ValidationReport:
        problems = self.check_evidence(bundle)
        evidence = {e.evidence_id: e for e in bundle.evidence}
        forecasts = {f.record_id: f for f in bundle.forecasts}
        row_verdicts = []
        for row in draft.table_rows:
            reasons = []
            fv = forecasts.get(row.record_id)
            if not fv:
                reasons.append("row is not backed by a specialist forecast record")
            else:
                if row.record_id in problems:
                    reasons += problems[row.record_id]
                for field in ("instrument_label", "instrument_key", "horizon_label", "value"):
                    if getattr(row, field) != getattr(fv, field):
                        reasons.append(f"{field} differs from extracted source value")
                if (row.unit or None) != (fv.unit or None):
                    reasons.append("unit differs from extracted source")
                if (row.scenario or None) != (fv.scenario or None):
                    reasons.append("scenario label differs from source")
                if row.evidence_id != fv.evidence_id:
                    reasons.append("row cites different evidence than the forecast record")
                ev = evidence.get(fv.evidence_id)
                if not ev:
                    reasons.append("cited evidence missing from ledger")
                elif fv.evidence_id in problems:
                    reasons += problems[fv.evidence_id]
                elif row.value not in ev.excerpt:
                    reasons.append("value not present in cited excerpt")
            row_verdicts.append(RowVerdict(row_id=row.row_id, ok=not reasons, reasons=reasons))

        claim_verdicts = []
        for claim in draft.claims:
            reasons = []
            cited = [evidence.get(e) for e in claim.evidence_ids]
            if not claim.evidence_ids:
                reasons.append("no evidence cited")
            if any(c is None for c in cited):
                reasons.append("cites evidence that is not in the ledger")
            cited = [c for c in cited if c]
            for c in cited:
                if c.evidence_id in problems:
                    reasons += [f"{c.evidence_id}: {p}" for p in problems[c.evidence_id]]
            support = " \n ".join(_norm(c.excerpt) for c in cited)
            support_extra = " ".join(
                f"{c.publication_date or ''} {c.title} {c.data_date or ''}" for c in cited)
            cited_values = [f for f in bundle.forecasts if f.evidence_id in claim.evidence_ids]
            support_values = " ".join(f"{f.value} {f.horizon_label} {f.instrument_label} {(f.horizon_end or '')[:4]}"
                                      for f in cited_values)
            text = _norm(claim.text)
            if cited:
                if claim.mode == "verbatim":
                    if text not in support:
                        reasons.append("quoted text does not match the cited excerpt")
                else:
                    for n in NUM_RE.findall(text):
                        n2 = n.rstrip(",").rstrip("%").lstrip("+")  # "2026," is 2026 followed by a comma
                        if n2 not in support and n2 not in support_values and n2 not in support_extra:
                            reasons.append(f"number '{n}' is not in the cited evidence")
                    client = claim.mode == "summary" and claim.section in CLIENT_SECTIONS
                    words = _words(text) - TEMPLATE_WORDS - (HOUSE_VOICE if client else set())
                    if claim.mode == "summary" and words:
                        supported = _words(support + " " + support_extra + " " + support_values)
                        ratio = len(words & supported) / len(words)
                        if ratio < (CLIENT_OVERLAP if client else OVERLAP):
                            reasons.append(f"wording not supported by cited excerpts (overlap {ratio:.0%})")
                    # Template sentences are fixed application wording around
                    # extracted values; their numbers, direction and language
                    # are checked above/below, not their connective words.
                reco = RECO_RE.search(text)
                if reco and reco.group(0).lower() not in support.lower():
                    reasons.append(f"recommendation language '{reco.group(0)}' not present in the source")
                for pair in find_pairs(text):
                    flat = support.upper().replace("-", "").replace("/", "") + " " + support_values.upper().replace("-", "")
                    if pair not in flat:
                        inv = pair[3:] + pair[:3]
                        reasons.append(f"instrument direction {pair[:3]}/{pair[3:]} not supported"
                                       + (f" (source quotes {inv[:3]}/{inv[3:]})" if inv in flat else ""))
            claim_verdicts.append(ClaimVerdict(claim_id=claim.claim_id, ok=not reasons, reasons=reasons))
        passed = all(v.ok for v in claim_verdicts) and all(v.ok for v in row_verdicts)
        return ValidationReport(passed=passed, claims=claim_verdicts, rows=row_verdicts, evidence_problems=problems,
                                checks_run=["evidence-signature", "document-exists", "page-exists", "excerpt-verbatim",
                                            "forecast-record-match", "row-value-match", "numbers-in-evidence",
                                            "wording-overlap", "recommendation-language", "pair-direction"])
