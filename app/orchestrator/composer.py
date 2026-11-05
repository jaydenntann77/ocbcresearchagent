"""Answer composition and evidence validation.

Builds a DraftAnswer (claims + forecast rows) strictly from specialist
responses, submits it with the evidence ledger to the validator, removes
whatever fails, and assembles the referenced answer shown to the user."""
from __future__ import annotations

import re
import uuid
from datetime import date

from app.common.freshness import horizon_passed, label as freshness_label
from app.common.instruments import display_name
from app.common.schemas import (SPECIALIST_LABELS, Claim, DraftAnswer, EvidenceBundle, SpecialistResponse, TableRow)
from app.common.timeutil import fmt_date, fmt_dt, fmt_range, now_sgt
from app.orchestrator import llm

REL_ORDER = {"1M": 1, "3M": 3, "6M": 6, "9M": 9, "12M": 12, "18M": 18, "24M": 24}
NO_FORECAST = "The ingested OCBC research does not contain a verified forecast for this horizon."


def no_evidence_message(plan, limitations: list[dict]) -> str:
    """Name what is missing. "For this horizon" is used only when the instrument
    has forecasts but not for the requested years."""
    if "forecast" not in plan.info_types:
        return "The ingested OCBC research does not contain relevant information for this request."
    if any(l["type"] == "horizon_not_covered" for l in limitations) or not plan.instruments:
        return NO_FORECAST
    names = [display_name(k) for k in plan.instruments]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
    return f"The ingested OCBC research does not contain a verified forecast for {joined}."

# Client-facing presentation: lead with an executive summary (house view, key
# forecast, main drivers, what could change the view), show ONE forecast table,
# and keep the remaining evidence out of the narrative.
SUMMARY_MAX = 8
HEADLINE_RE = re.compile(r"^[A-Z][^:.!?]{2,80}?\s+:\s+")       # "USD Still Has Support : The USD..."
HOUSE_VIEW_RE = re.compile(r"\b(we|our)\b", re.I)
RELATIVE_ASK_RE = re.compile(r"\b(\d{1,2}\s*-?\s*m(onths?)?\b|relative horizon|months? ahead)", re.I)
SOURCE_LINE_RE = re.compile(r"^\s*source\s*:", re.I)


def _d(s: str | None) -> str:
    return fmt_date(date.fromisoformat(s)) if s else "date unknown"


def _row_sort(fv):
    if fv.horizon_kind == "absolute":
        return (0, fv.horizon_end or "", 0)
    return (1, "", REL_ORDER.get(fv.horizon_label.upper(), 99))


def _one_representation(question: str, forecasts: list) -> list:
    """Show one version of each instrument's forecast: the calendar path, or the
    3M/6M/12M one when the question asks for relative horizons."""
    keep = "relative" if RELATIVE_ASK_RE.search(question) else "absolute"
    has = {f.instrument_key for f in forecasts if f.horizon_kind == keep}
    return [f for f in forecasts if f.horizon_kind == keep or f.instrument_key not in has]


def _path_sentence(fvs: list) -> str:
    """Template sentence naming the start and end of a published path (not every value)."""
    first, last = fvs[0], fvs[-1]
    name = first.instrument_label
    if first.unit and name.endswith(first.unit):  # "Gold $/oz" -> "gold"
        name = name[:-len(first.unit)].strip().lower()
    if len(fvs) == 1:
        return f"Our house forecast for {name} is {first.value} for {first.horizon_label}."
    # No comma straight after a horizon label: the validator would read "Dec-26," as a number.
    try:
        move = float(last.value.rstrip("%")) - float(first.value.rstrip("%"))
        verb = "easing" if move < 0 else "rising" if move > 0 else ""
    except ValueError:
        verb = "moving"
    if not verb:
        return (f"Our house forecast has {name} unchanged at {first.value} "
                f"from {first.horizon_label} to {last.horizon_label}.")
    return (f"Our house forecast has {name} {verb} from {first.value} in {first.horizon_label} "
            f"to {last.value} by {last.horizon_label}.")


PART_ORDER = {"view": 0, "path": 1, "why": 2, "risks": 3, "conclusion": 4}


def _summary(claims: list[Claim], path_claims: list[Claim]) -> list[Claim]:
    """Executive summary from validated material, in the house order: what we
    think, where the market goes, why, what could change the view."""
    rationale = [c for c in claims if c.section == "rationale"]
    risks = [c for c in claims if c.section in ("risks", "scenarios")]
    rationale.sort(key=lambda c: not HOUSE_VIEW_RE.search(c.text))
    view = rationale[:1] if rationale and HOUSE_VIEW_RE.search(rationale[0].text) else []
    rest = rationale[len(view):]
    if path_claims:
        why, risk = rest[:1], risks[:1]
    else:  # a view or risk question: the findings are the answer
        why = rest[:3 - len(view)]
        risk = risks[:max(1, 4 - len(view) - len(why))]
    tagged = ([c.model_copy(update={"part": "view"}) for c in view]
              + [c.model_copy(update={"part": "path"}) for c in path_claims[:4]]
              + [c.model_copy(update={"part": "why"}) for c in why]
              + [c.model_copy(update={"part": "risks"}) for c in risk])
    return tagged[:SUMMARY_MAX]


def build_draft(question: str, responses: list[SpecialistResponse]):
    evidence = {}
    forecasts = []
    for r in responses:
        for e in r.evidence:
            evidence.setdefault(e.evidence_id, e)
        forecasts += r.forecasts
    shown = _one_representation(question, forecasts)
    hidden_ev = {f.evidence_id for f in forecasts} - {f.evidence_id for f in shown}
    hidden_tables = {evidence[e].table_id for e in hidden_ev if e in evidence and evidence[e].table_id} \
        - {evidence[f.evidence_id].table_id for f in shown if f.evidence_id in evidence}
    forecasts = shown
    rows: list[TableRow] = []
    for fv in sorted(forecasts, key=lambda f: (f.instrument_key,) + _row_sort(f)):
        ev = evidence.get(fv.evidence_id)
        rows.append(TableRow(row_id=f"R{len(rows) + 1}", instrument_label=fv.instrument_label,
                             instrument_key=fv.instrument_key, horizon_label=fv.horizon_label, value=fv.value,
                             unit=fv.unit, scenario=fv.scenario, record_id=fv.record_id, evidence_id=fv.evidence_id,
                             publication_date=ev.publication_date if ev else None,
                             horizon_passed=horizon_passed(fv.horizon_end)))
    claims: list[Claim] = []

    def add(section, text, ev_ids, mode, spec=None):
        for c in claims:
            if c.section == section and c.text == text:
                c.evidence_ids = list(dict.fromkeys(c.evidence_ids + ev_ids))
                return
        claims.append(Claim(claim_id=f"C{len(claims) + 1}", section=section, text=text, evidence_ids=ev_ids,
                            mode=mode, specialist=spec))

    # Forecast path: one template sentence per instrument/source table naming
    # where the path starts and ends; the table carries every value.
    by_table: dict[tuple, list] = {}
    for fv in forecasts:
        by_table.setdefault((fv.instrument_key, fv.evidence_id, fv.horizon_kind), []).append(fv)
    paths = []
    for (key, ev_id, kind), fvs in by_table.items():
        fvs.sort(key=_row_sort)
        paths.append(Claim(claim_id=f"P{len(paths) + 1}", section="direct", text=_path_sentence(fvs),
                           evidence_ids=[ev_id], mode="template"))
    for r in responses:
        for f in r.findings:
            section = {"rationale": "rationale", "risk": "risks", "scenario": "scenarios",
                       "data_point": "commentary", "commentary": "rationale",
                       "forecast_summary": "direct"}[f.kind]
            if section == "commentary" and (SOURCE_LINE_RE.match(f.statement) or all(
                    evidence[e].table_id in hidden_tables for e in f.evidence_ids if e in evidence)):
                continue  # attribution lines are shown under the table; notes on a hidden table are moot
            # Drop report-headline prefixes; the remainder is still verbatim.
            text = HEADLINE_RE.sub("", f.statement) if section != "commentary" else f.statement
            add(section, text, f.evidence_ids, "verbatim", r.specialist)
    # Executive summary: the chosen claims move into the "direct" section, in order.
    summary = _summary(claims, paths)
    picked = {c.claim_id for c in summary}
    origin = {f"S{i + 1}": c.section for i, c in enumerate(summary)}
    claims[:] = [c.model_copy(update={"section": "direct", "claim_id": f"S{i + 1}"}) for i, c in enumerate(summary)] \
        + [c for c in claims if c.claim_id not in picked]
    draft = DraftAnswer(question=question, claims=claims, table_rows=rows)
    all_fc = [f for r in responses for f in r.forecasts]
    bundle = EvidenceBundle(evidence=list(evidence.values()), forecasts=all_fc)
    return draft, bundle, origin


def compose(question: str, plan, responses: list[SpecialistResponse], validator, notices: list[dict],
            corpus: dict, use_model: bool = True) -> dict:
    draft, bundle, origin = build_draft(question, responses)
    model_note = None
    model_removed = []
    mode = "extractive"
    if use_model and llm.status()["available"] and (draft.claims or draft.table_rows):
        try:
            sentences = llm.synthesize(
                question, [f.model_dump() for r in responses for f in r.findings],
                [e.model_dump() for e in bundle.evidence], [r.model_dump() for r in draft.table_rows])
            model_claims = [Claim(claim_id=f"M{i + 1}", section=s["section"], text=s["text"],
                                  evidence_ids=s["evidence_ids"], mode="summary", part=s.get("part"))
                            for i, s in enumerate(sentences)]
            report = validator.validate(DraftAnswer(question=question, claims=model_claims), bundle)
            ok = [c for c, v in zip(model_claims, report.claims) if v.ok]
            dropped = len(model_claims) - len(ok)
            model_removed = [{"text": c.text, "reasons": v.reasons} for c, v in zip(model_claims, report.claims)
                             if not v.ok]
            if any(c.section == "direct" for c in ok):
                mode = "model_assisted"
                # The model's executive summary replaces the extractive one; the
                # quotes that summary was built from go back to supporting research.
                rest = [c.model_copy(update={"section": origin[c.claim_id]}) if c.claim_id in origin else c
                        for c in draft.claims]
                summary = sorted((c for c in ok if c.section == "direct"), key=lambda c: PART_ORDER.get(c.part, 0))
                # The key forecast must be in the summary: if every model sentence
                # stating it failed validation, lead with the fixed-wording path.
                values = {r.value for r in draft.table_rows}
                if values and not any(v in c.text for c in summary for v in values):
                    summary = [c for c in draft.claims if c.section == "direct" and c.mode == "template"] + summary
                draft.claims = summary + [c for c in ok if c.section != "direct"] \
                    + [c for c in rest if c.section != "direct"]
            if dropped:
                model_note = f"{dropped} model-written sentence(s) failed evidence validation and were removed."
        except llm.ModelUnavailable as exc:
            model_note = str(exc)

    report = validator.validate(draft, bundle)
    bad_claims = {v.claim_id: v.reasons for v in report.claims if not v.ok}
    bad_rows = {v.row_id: v.reasons for v in report.rows if not v.ok}
    claims = [c for c in draft.claims if c.claim_id not in bad_claims]
    rows = [r for r in draft.table_rows if r.row_id not in bad_rows]

    evidence = {e.evidence_id: e for e in bundle.evidence if e.evidence_id not in report.evidence_problems}
    order: list[str] = []

    def cite(ids):
        out = []
        for i in ids:
            if i in evidence:
                if i not in order:
                    order.append(i)
                out.append(order.index(i) + 1)
        return out

    def claim_out(c: Claim):
        return {"text": c.text, "mode": c.mode, "citations": cite(c.evidence_ids),
                "specialist": SPECIALIST_LABELS.get(c.specialist or "", None), "part": c.part}

    sections = {s: [] for s in ("direct", "rationale", "risks", "scenarios", "commentary")}
    for c in claims:
        if c.section == "direct":
            sections["direct"].append(claim_out(c))
    table = []
    forecast_meta = {f.record_id: f for f in bundle.forecasts}
    for r in rows:
        fv = forecast_meta[r.record_id]
        ev = evidence.get(r.evidence_id)
        table.append({
            "instrument": r.instrument_label, "horizon": r.horizon_label, "horizon_kind": fv.horizon_kind,
            "value": r.value, "unit": r.unit, "quotation": r.instrument_label if not r.unit else None,
            "scenario": r.scenario or "Baseline", "publication_date": r.publication_date,
            "publication_label": _d(r.publication_date), "data_date": fv.data_date,
            "horizon_passed": r.horizon_passed, "citations": cite([r.evidence_id]),
            "table_title": fv.table_title, "doc_title": ev.title if ev else None,
        })
    for c in claims:
        if c.section in ("rationale", "risks", "scenarios", "commentary"):
            sections[c.section].append(claim_out(c))

    limitations = []
    for r in responses:
        for cov in r.coverage:
            if cov.status != "found":
                limitations.append({"type": cov.status, "text": cov.detail, "specialist": SPECIALIST_LABELS[r.specialist]})
        for m in r.missing_coverage:
            limitations.append({"type": "missing_coverage", "text": m, "specialist": SPECIALIST_LABELS[r.specialist]})
        for m in r.limitations:
            limitations.append({"type": "limitation", "text": m, "specialist": SPECIALIST_LABELS[r.specialist]})
        if r.status == "error":
            limitations.append({"type": "error", "text": f"The {SPECIALIST_LABELS[r.specialist]} specialist could not "
                                                          f"complete its search.", "specialist": SPECIALIST_LABELS[r.specialist]})
    conflicts = [{"text": c.description, "resolution": c.resolution} for r in responses for c in r.conflicts]
    if any(t["horizon_kind"] == "relative" for t in table):
        limitations.append({"type": "note", "text": "3M/6M/12M horizons are relative horizons as published; they are "
                                                    "not mapped to calendar dates and are not a monthly path.",
                            "specialist": None})
    if any(t["horizon_passed"] for t in table):
        limitations.append({"type": "horizon_passed", "text": "One or more forecast horizons shown have already "
                                                             "passed.", "specialist": None})
    removed = len(bad_claims) + len(bad_rows)
    if removed:
        limitations.append({"type": "validation", "text": f"{removed} statement(s) or table value(s) failed evidence "
                                                          f"validation and were omitted.", "specialist": None})
    if model_note:
        limitations.append({"type": "model", "text": model_note, "specialist": None})

    sources = []
    for n, eid in enumerate(order, 1):
        e = evidence[eid]
        fr = freshness_label(e.publication_date, e.report_type, e.date_confidence)
        sources.append({"n": n, "evidence_id": eid, "doc_id": e.doc_id, "title": e.title,
                        "publication_date": e.publication_date, "publication_label": _d(e.publication_date),
                        "date_confidence": e.date_confidence, "data_date": e.data_date, "report_type": e.report_type,
                        "freshness": fr, "url": e.source_url, "pdf_page": e.pdf_page, "printed_page": e.printed_page,
                        "section": e.section, "excerpt": e.excerpt, "ocr": e.ocr})
    pub_dates = sorted({s["publication_date"] for s in sources if s["publication_date"]})
    if len(pub_dates) > 1 and (date.fromisoformat(pub_dates[-1]) - date.fromisoformat(pub_dates[0])).days >= 2:
        limitations.append({"type": "mixed_dates", "text": f"This answer combines reports published on different "
                                                          f"dates ({fmt_range(date.fromisoformat(pub_dates[0]), date.fromisoformat(pub_dates[-1]))}); "
                                                          f"check each source's date.", "specialist": None})
    has_content = bool(table or any(sections.values()))
    blocking = [l for l in limitations if l["type"] not in ("note", "model", "mixed_dates", "limitation")]
    status = "complete" if has_content and not blocking else "partial" if has_content else "no_evidence"
    window = corpus.get("window") or {}
    return {
        "answer_id": f"A-{uuid.uuid4().hex[:10]}",
        "question": question,
        "generated_at": now_sgt().isoformat(), "generated_label": fmt_dt(now_sgt()),
        "status": status, "mode": mode, "notices": notices,
        "freshness": {
            "research_published": fmt_range(date.fromisoformat(pub_dates[0]), date.fromisoformat(pub_dates[-1]))
            if pub_dates else None,
            "corpus_window": window.get("label"), "corpus_refreshed": corpus.get("refreshed_label"),
            "expanded": bool(window.get("expanded")),
        },
        "direct": sections["direct"], "table": table,
        "table_notes": sections["commentary"], "rationale": sections["rationale"],
        "risks": sections["risks"], "scenarios": sections["scenarios"],
        "conflicts": conflicts, "limitations": limitations, "sources": sources,
        "specialists": [SPECIALIST_LABELS[r.specialist] for r in responses],
        "validation": {"passed_after_removal": True, "removed": removed, "checks": report.checks_run,
                       "removed_reasons": list(bad_claims.values())[:5] + list(bad_rows.values())[:5],
                       "model_removed": model_removed},
        "no_evidence_message": None if has_content else no_evidence_message(plan, limitations),
    }
