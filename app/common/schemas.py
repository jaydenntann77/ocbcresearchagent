"""Wire contracts between agents. All models forbid extra fields so that a
specialist cannot smuggle user-directed content (e.g. a `message_to_user`
field) through the findings channel; such payloads fail validation."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SpecialistName = Literal["fx", "rates", "macro", "equities", "credit"]
SPECIALISTS: tuple[str, ...] = ("fx", "rates", "macro", "equities", "credit")
SPECIALIST_LABELS = {
    "fx": "FX", "rates": "Rates", "macro": "Macro", "equities": "Equities", "credit": "Credit",
}

InfoType = Literal["forecast", "rationale", "risks", "scenarios", "commentary", "data_points"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- task contract
class CorpusConstraints(Strict):
    window_start: str            # ISO date, inclusive
    window_end: str              # ISO date, inclusive
    expanded_range: bool = False  # True only when an administrator explicitly widened the window


class SpecialistTask(Strict):
    task_id: str
    specialist: SpecialistName
    original_question: str
    objective: str
    instruments: list[str] = []          # normalised keys, e.g. USDSGD, UST10Y
    currencies: list[str] = []
    countries: list[str] = []
    sectors: list[str] = []
    issuers: list[str] = []
    horizon: str | None = None           # e.g. "through 2027"
    horizon_years: list[int] = []
    info_types: list[InfoType] = ["forecast", "rationale"]
    corpus: CorpusConstraints
    output_schema: str = "SpecialistResponse/v1"
    evidence_requirements: str = (
        "Every finding must cite evidence items with document ID, PDF page and a verbatim excerpt. "
        "Forecast values must be copied exactly with their original horizon labels and units.")
    known_gaps: list[str] = []
    follow_up_of: str | None = None
    search_terms: list[str] = []         # the research's own wording for the question (query rewrite)


# ---------------------------------------------------------------- evidence
class Evidence(Strict):
    evidence_id: str
    doc_id: str
    title: str
    publication_date: str | None
    date_confidence: Literal["high", "medium", "low"]
    data_date: str | None = None          # explicitly stated data/forecast date, verbatim
    report_type: str | None = None
    source_url: str
    pdf_page: int
    printed_page: str | None = None
    section: str | None = None
    excerpt: str
    ocr: bool = False
    chunk_id: str | None = None
    table_id: str | None = None
    signature: str = ""                   # HMAC by the research service over the fields above


class ForecastValue(Strict):
    record_id: str
    instrument_label: str                 # as printed, e.g. "USD-SGD"
    instrument_key: str                   # normalised, e.g. USDSGD
    horizon_label: str                    # as printed, e.g. "Dec-27"
    horizon_kind: Literal["absolute", "relative"]
    horizon_end: str | None = None        # ISO date for absolute horizons
    value: str                            # exact string from the source
    unit: str | None = None
    scenario: str | None = None           # None == baseline
    table_title: str | None = None
    group_label: str | None = None
    footnotes: list[str] = []
    data_date: str | None = None
    evidence_id: str


class Finding(Strict):
    finding_id: str
    kind: Literal["forecast_summary", "rationale", "risk", "scenario", "commentary", "data_point"]
    statement: str
    statement_mode: Literal["verbatim", "summary"]
    evidence_ids: list[str]
    instruments: list[str] = []


class Conflict(Strict):
    description: str
    instrument_key: str
    horizon_label: str
    record_ids: list[str]
    resolution: Literal["latest_publication_applies", "unresolved"]


class Coverage(Strict):
    status: Literal[
        "found", "no_relevant_information", "document_inaccessible",
        "extraction_failed", "conflicting_sources", "horizon_not_covered"]
    detail: str


class SpecialistResponse(Strict):
    task_id: str
    specialist: SpecialistName
    status: Literal["ok", "partial", "no_evidence", "error"]
    findings: list[Finding] = []
    forecasts: list[ForecastValue] = []
    evidence: list[Evidence] = []
    conflicts: list[Conflict] = []
    coverage: list[Coverage] = []
    missing_coverage: list[str] = []
    limitations: list[str] = []
    documents_considered: int = 0
    mode: Literal["extractive", "model_assisted"] = "extractive"


# ---------------------------------------------------------------- answer + validation
class Claim(Strict):
    claim_id: str
    section: Literal["direct", "rationale", "risks", "scenarios", "commentary", "limitations"]
    text: str
    evidence_ids: list[str]
    mode: Literal["verbatim", "summary", "template"] = "template"
    specialist: str | None = None
    part: Literal["view", "path", "why", "risks", "conclusion"] | None = None  # executive-summary structure


class TableRow(Strict):
    row_id: str
    instrument_label: str
    instrument_key: str
    horizon_label: str
    value: str
    unit: str | None = None
    scenario: str | None = None
    record_id: str
    evidence_id: str
    publication_date: str | None = None
    horizon_passed: bool = False


class DraftAnswer(Strict):
    question: str
    claims: list[Claim] = []
    table_rows: list[TableRow] = []


class EvidenceBundle(Strict):
    evidence: list[Evidence]
    forecasts: list[ForecastValue] = []


class ValidationRequest(Strict):
    draft: DraftAnswer
    bundle: EvidenceBundle


class ClaimVerdict(Strict):
    claim_id: str
    ok: bool
    reasons: list[str] = []


class RowVerdict(Strict):
    row_id: str
    ok: bool
    reasons: list[str] = []


class ValidationReport(Strict):
    passed: bool
    claims: list[ClaimVerdict]
    rows: list[RowVerdict]
    evidence_problems: dict[str, list[str]] = {}
    checks_run: list[str] = []
