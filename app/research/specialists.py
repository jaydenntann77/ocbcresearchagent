"""Specialist research agents (FX, Rates, Macro, Equities, Credit).

Each specialist receives a SpecialistTask, searches only the collections the
registry grants it, and returns a SpecialistResponse built exclusively from
ingested text: forecast values are copied cell-for-cell from parsed tables and
narrative findings are verbatim sentences with page-level evidence. There is no
code path from a specialist to the user and no network access in this process.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date

from app.common import config, embedding
from app.common.instruments import CURRENCY_NAMES, instrument_aliases
from app.common.schemas import (SPECIALIST_LABELS, Conflict, Coverage, Evidence, Finding, ForecastValue, SpecialistResponse,
                                SpecialistTask)
from app.common.security import evidence_signature
from app.common.timeutil import today_sgt
from app.research.collections import CollectionHandle, CollectionRegistry

VIEW_RE = re.compile(
    r"\b(we (?:expect|see|think|believe|look for|maintain|retain|remain|prefer|forecast|anticipate|project)|"
    r"our (?:view|forecast|house view|base case|bias)|house view|expect(?:ed|s)?|likely|bias|outlook|forecasts?|"
    r"should|could|may|would|supportive|support(?:ed|s)?|pressure|headwinds?|tailwinds?|constructive|cautious)\b", re.I)
TECHNICAL_RE = re.compile(
    r"\b(support at|resistance at|resistance|RSI|DMA|momentum|overbought|oversold|daily chart|fibo|retracement|"
    r"technically|last at|last closed|closed at|levels?\.)\b", re.I)
RISK_RE = re.compile(
    r"\b(risks?|downside|upside risk|uncertain(?:ty)?|vulnerab\w*|threat|caution|concerns?|headwinds?|"
    r"could (?:weigh|derail|hurt|complicate|constrain)|stress|volatility|pressure)\b", re.I)
SCENARIO_RE = re.compile(r"\b(scenario|alternative|in the event|should the|if the|base case|bull case|bear case)\b", re.I)
NUM_RE = re.compile(r"\d")
DESCRIPTIVE_RE = re.compile(r"(overnight|yesterday|last week|this morning|traded|closed|was (?:broadly|mostly|little)|"
                            r"were (?:broadly|mostly)|edged|drifted|snapp\w+)", re.I)

SPECIALIST_FOCUS = {
    "fx": "currency outlook exchange rate FX forecast",
    "rates": "interest rates yields policy rate curve outlook",
    "macro": "economic outlook growth inflation policy",
    "equities": "equity market stocks earnings outlook",
    "credit": "credit outlook issuers spreads risks",
}
RATE_TERMS = {
    "SGD": ["SORA", "SGS", "SGD rates", "SGD interest rates", "Singapore government securities", "MAS", "T-bill"],
    "USD": ["Fed", "FOMC", "UST", "Treasury", "Treasuries", "SOFR", "fed funds"],
    "EUR": ["ECB", "Bund", "euro area"], "JPY": ["BoJ", "JGB"], "GBP": ["BoE", "gilt", "gilts"],
    "CNY": ["PBoC", "LPR", "CGB"], "MYR": ["BNM", "MGS", "OPR"], "IDR": ["BI ", "IndoGB"],
}
FX_TERMS = {"SGD": ["S$NEER", "SGD NEER", "NEER", "MAS", "Singapore dollar"]}
COUNTRY_NAMES = {"SG": "Singapore", "MY": "Malaysia", "ID": "Indonesia", "TH": "Thailand", "CN": "China",
                 "HK": "Hong Kong", "TW": "Taiwan", "KR": "Korea", "JP": "Japan", "IN": "India", "PH": "Philippines",
                 "VN": "Vietnam", "US": "US", "EA": "euro area", "UK": "UK", "AU": "Australia", "MO": "Macau"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def split_sentences(text: str) -> list[str]:
    text = _norm(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(•])|\s*[•●]\s*", text)
    return [p.strip() for p in parts if 40 <= len(p.strip()) <= 700]


def _jaccard(a: str, b: str) -> float:
    ta, tb = set(re.findall(r"[a-z]+", a.lower())), set(re.findall(r"[a-z]+", b.lower()))
    return len(ta & tb) / max(1, len(ta | tb))


class CorpusStatus:
    """Read-only view of ingestion outcomes, used only to explain coverage gaps."""

    def __init__(self):
        self.path = config.META_DB

    def _conn(self):
        conn = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def corpus_state(self) -> dict:
        if not self.path.exists():
            return {}
        with self._conn() as conn:
            return {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM corpus_state")
                    if r["key"] in ("active_window", "last_successful_run")}

    def problems_for(self, specialist: str) -> dict[str, list[str]]:
        out = {"inaccessible": [], "extraction_failed": [], "sections_failed": []}
        if not self.path.exists():
            return out
        policy = config.load_json_config("specialists.json")["category_primary"]
        with self._conn() as conn:
            run = conn.execute("SELECT run_id FROM runs WHERE status='completed' ORDER BY finished_at DESC LIMIT 1").fetchone()
            if not run:
                return out
            for r in conn.execute("SELECT url,state,detail,listing FROM run_items WHERE run_id=? AND state IN "
                                  "('inaccessible','failed_download','invalid_pdf','parse_failed')", (run["run_id"],)):
                listing = json.loads(r["listing"] or "{}")
                spec = policy.get(listing.get("section") or "") or policy.get(listing.get("category") or "")
                if spec in (None, specialist):
                    key = "extraction_failed" if r["state"] in ("invalid_pdf", "parse_failed") else "inaccessible"
                    out[key].append(f"{listing.get('title') or r['url']} ({r['state']}: {r['detail']})")
            for r in conn.execute("SELECT source, category, detail FROM section_checks WHERE run_id=? AND status='failed'",
                                  (run["run_id"],)):
                spec = policy.get(r["category"] or "")
                if spec in (None, specialist):
                    out["sections_failed"].append(f"{r['source']} ({r['detail']})")
            for r in conn.execute("SELECT d.title, p.pdf_page FROM pages p JOIN documents d USING(doc_id) "
                                  "WHERE p.ocr_failed=1 AND d.specialists LIKE ?", (f'%"{specialist}"%',)):
                out["extraction_failed"].append(f"{r['title']} p.{r['pdf_page']} (image-only page, OCR failed)")
        return out


class Specialist:
    def __init__(self, name: str, registry: CollectionRegistry, status: CorpusStatus):
        self.name = name
        self.registry = registry
        self.status = status

    # ------------------------------------------------------------------ helpers
    def _evidence(self, chunk: dict, excerpt: str, table_id: str | None = None, data_date: str | None = None) -> Evidence:
        eid = "E-" + hashlib.sha1(f"{chunk['chunk_id']}|{excerpt}".encode("utf-8")).hexdigest()[:12]
        ev = {
            "evidence_id": eid, "doc_id": chunk["doc_id"], "title": chunk["title"] or chunk["doc_id"],
            "publication_date": chunk["publication_date"], "date_confidence": chunk["date_confidence"] or "medium",
            "data_date": data_date, "report_type": chunk["report_type"], "source_url": chunk["source_url"],
            "pdf_page": chunk["pdf_page"], "printed_page": chunk["printed_page"], "section": chunk["section"],
            "excerpt": excerpt, "ocr": bool(chunk["ocr"]), "chunk_id": chunk["chunk_id"], "table_id": table_id,
        }
        ev["signature"] = evidence_signature(config.EVIDENCE_SIGNING_KEY or "unsigned", ev)
        return Evidence(**ev)

    def focus_terms(self, task: SpecialistTask) -> list[str]:
        terms: list[str] = []
        for key in task.instruments:
            terms += instrument_aliases(key)
        for cur in task.currencies:
            if self.name == "rates":
                # A bare currency code is FX vocabulary; rates findings must
                # mention the rates instruments/institutions themselves.
                terms += RATE_TERMS.get(cur, []) + [f"{cur} rates", f"{cur} interest rates", f"{cur} yields"]
                continue
            terms.append(cur)
            if self.name in ("fx", "macro"):
                terms += FX_TERMS.get(cur, [])
            terms += [n for n, c in CURRENCY_NAMES.items() if c == cur and len(n) > 4]
        for c in task.countries:
            if c in COUNTRY_NAMES:
                terms.append(COUNTRY_NAMES[c])
        terms += task.issuers + task.sectors + task.search_terms
        return list(dict.fromkeys(t for t in terms if t))

    @staticmethod
    def _mentions(text: str, terms: list[str]) -> int:
        n = 0
        for t in terms:
            if re.fullmatch(r"[A-Z$]{3,8}", t):
                n += len(re.findall(rf"(?<![A-Za-z]){re.escape(t)}(?![A-Za-z])", text))
            else:
                n += len(re.findall(rf"(?<![A-Za-z]){re.escape(t)}s?(?![A-Za-z])", text, re.I))
        return n

    # ------------------------------------------------------------------ forecasts
    def _forecasts(self, task, handles, resp: SpecialistResponse):
        keys = [k for k in task.instruments]
        if not keys:
            return
        records = []
        for h in handles:
            for r in h.forecast_records(keys):
                r["_handle"] = h
                records.append(r)
        available = set().union(*(h.available_instrument_keys() for h in handles)) if handles else set()
        for key in keys:
            if len(key) == 6 and key not in available and (key[3:] + key[:3]) in available:
                resp.missing_coverage.append(
                    f"{key[:3]}/{key[3:]} is not published in the ingested forecast tables; OCBC publishes "
                    f"{key[3:]}-{key[:3]}. The pair was not inverted (inversion is not permitted).")
        forecasts = [r for r in records if not r["is_observation"]]
        if not forecasts:
            for key in keys:
                if not any(key in m for m in resp.missing_coverage):
                    resp.coverage.append(Coverage(status="no_relevant_information",
                                                  detail=f"The ingested OCBC research does not contain a verified forecast for {key}."))
            return
        horizon_text = (task.horizon or "").lower()
        years = sorted(task.horizon_years)
        through = bool(re.search(r"through|until|till|by|to end|out to|path", horizon_text)) or not years
        today = today_sgt()

        def wanted(r) -> bool:
            if not years:
                return True
            if r["horizon_kind"] != "absolute":
                # Relative horizons (3M/12M) are offered for "through <year>"
                # requests only; they cannot be placed in a specific year.
                return through
            y = int(r["horizon_end"][:4])
            return (today.year <= y <= max(years)) if through else (y in years)

        selected = [r for r in forecasts if wanted(r)]
        # Group identical instrument/horizon/scenario across documents.
        groups: dict[tuple, list[dict]] = {}
        for r in selected:
            groups.setdefault((r["instrument_key"], r["horizon_label"], r["scenario"] or ""), []).append(r)
        chosen: list[dict] = []
        for (key, label, scen), recs in groups.items():
            values = {r["value"] for r in recs}
            recs.sort(key=lambda r: (r["publication_date"] or "", r["data_date"] or ""), reverse=True)
            if len(values) == 1:
                chosen.append(recs[0])
                continue
            docs = {r["doc_id"] for r in recs}
            newest, older = recs[0], [r for r in recs[1:] if r["value"] != recs[0]["value"]]
            supersedes = len(docs) > 1 and all(
                (newest["publication_date"] or "") > (o["publication_date"] or "") and newest["data_date"]
                and o["data_date"] and newest["data_date"] != o["data_date"] for o in older)
            chosen.append(newest)
            if supersedes:
                resp.conflicts.append(Conflict(
                    description=(f"{newest['instrument_label']} {label}: {newest['value']} in {newest['title']} "
                                 f"({newest['publication_date']}, {newest['data_date']}) replaces "
                                 + "; ".join(f"{o['value']} in {o['title']} ({o['publication_date']}, {o['data_date']})"
                                             for o in older) + ". The newer report states a later forecast update date."),
                    instrument_key=key, horizon_label=label,
                    record_ids=[newest["record_id"]] + [o["record_id"] for o in older],
                    resolution="latest_publication_applies"))
            else:
                chosen.extend(older)
                resp.conflicts.append(Conflict(
                    description=(f"{newest['instrument_label']} {label}: sources differ - "
                                 + "; ".join(f"{r['value']} in {r['title']} ({r['publication_date']}, p.{r['pdf_page']})"
                                             for r in [newest] + older)
                                 + ". The sources do not establish which supersedes the other; both are shown."),
                    instrument_key=key, horizon_label=label,
                    record_ids=[newest["record_id"]] + [o["record_id"] for o in older], resolution="unresolved"))
        ev_cache: dict[str, Evidence] = {}
        for r in chosen:
            h: CollectionHandle = r["_handle"]
            chunk = h.chunk(r["chunk_id"]) if r["chunk_id"] else None
            if not chunk:
                resp.limitations.append(f"Forecast cell {r['record_id']} could not be linked to its table text; omitted.")
                continue
            lines = chunk["text"].split("\n")
            header = next((ln for ln in lines if ln.startswith("Instrument |")), lines[0])
            row = next((ln for ln in lines if ln.startswith(r["instrument_label"] + " |")), None)
            if row is None:
                resp.limitations.append(f"Row for {r['instrument_label']} not found verbatim in table; omitted.")
                continue
            parts = [x for x in [r["table_title"], header, row] if x]
            excerpt = "\n".join(dict.fromkeys(parts))
            if excerpt not in ev_cache:
                ev = self._evidence(chunk, excerpt, r["table_id"], r["data_date"])
                ev_cache[excerpt] = ev
                resp.evidence.append(ev)
            ev = ev_cache[excerpt]
            resp.forecasts.append(ForecastValue(
                record_id=r["record_id"], instrument_label=r["instrument_label"], instrument_key=r["instrument_key"],
                horizon_label=r["horizon_label"], horizon_kind=r["horizon_kind"], horizon_end=r["horizon_end"],
                value=r["value"], unit=r["unit"], scenario=r["scenario"], table_title=r["table_title"],
                group_label=r["group_label"], footnotes=json.loads(r["footnotes"] or "[]"), data_date=r["data_date"],
                evidence_id=ev.evidence_id))
        # Table footnotes carry qualification language (e.g. "not meant to serve
        # as point forecast"); return them verbatim as cited source notes.
        noted = set()
        for r in chosen:
            chunk = r["_handle"].chunk(r["chunk_id"]) if r["chunk_id"] else None
            if not chunk:
                continue
            for note in json.loads(r["footnotes"] or "[]"):
                line = next((ln for ln in chunk["text"].split("\n") if _norm(note) and _norm(note) in _norm(ln)), None)
                if not line or (chunk["chunk_id"], line) in noted:
                    continue
                noted.add((chunk["chunk_id"], line))
                ev = self._evidence(chunk, line, r["table_id"], r["data_date"])
                resp.evidence.append(ev)
                resp.findings.append(Finding(finding_id=f"{self.name}-N{len(noted)}", kind="data_point",
                                             statement=line, statement_mode="verbatim",
                                             evidence_ids=[ev.evidence_id], instruments=[r["instrument_key"]]))
        if years:
            covered = {int(r["horizon_end"][:4]) for r in selected if r["horizon_kind"] == "absolute"}
            want = range(today.year, max(years) + 1) if through else years
            for y in want:
                if y not in covered:
                    resp.coverage.append(Coverage(
                        status="horizon_not_covered",
                        detail=f"The ingested OCBC research does not contain a verified forecast for the {y} horizon "
                               f"({', '.join(keys)})."))
            later = sorted({int(r["horizon_end"][:4]) for r in forecasts if r["horizon_kind"] == "absolute"} - covered)
            if later and not through:
                resp.limitations.append(f"Forecasts for other years ({', '.join(map(str, later))}) exist but were not requested.")
        if resp.forecasts:
            resp.coverage.append(Coverage(status="found", detail=f"{len(resp.forecasts)} forecast values for {', '.join(keys)}"))

    # ------------------------------------------------------------------ narrative
    def _narrative(self, task: SpecialistTask, handles, resp: SpecialistResponse):
        terms = self.focus_terms(task)
        query = f"{task.objective} {task.original_question} {' '.join(task.search_terms)} {SPECIALIST_FOCUS[self.name]}"
        exact = [t for t in terms if re.fullmatch(r"[A-Z$/\-]{3,8}", t)]
        want_risks = "risks" in task.info_types
        want_rationale = any(t in task.info_types for t in ("rationale", "commentary", "forecast"))
        want_scen = "scenarios" in task.info_types
        # Credit and equity commentary often sits in table cells (issuer
        # descriptions); forecast tables are handled separately above.
        kinds = ("prose", "table") if self.name in ("credit", "equities") else ("prose",)
        hits = []
        for h in handles:
            hits += [(h, x) for x in h.search(query, exact, k=18, kinds=kinds)
                     if not x.chunk["text"].startswith(("Instrument |", "FX Forecasts"))]
            if want_risks:
                hits += [(h, x) for x in h.search(query + " risks downside uncertainty pressure", exact, k=12, kinds=kinds)
                         if not x.chunk["text"].startswith(("Instrument |", "FX Forecasts"))]
        cands = []
        seen_chunks = set()
        for h, hit in hits:
            c = hit.chunk
            if c["chunk_id"] in seen_chunks:
                continue
            seen_chunks.add(c["chunk_id"])
            for s in split_sentences(c["text"]):
                if s not in _norm(c["text"]):
                    continue
                focus = self._mentions(s, terms) if terms else 0
                section_focus = self._mentions(c["section"] or "", terms) if terms else 0
                if terms and focus == 0 and section_focus == 0:
                    continue
                if TECHNICAL_RE.search(s):
                    continue
                digits = len(NUM_RE.findall(s))
                view = bool(VIEW_RE.search(s))
                if digits > 18 and not view:
                    continue
                risk = bool(RISK_RE.search(s))
                scen = bool(SCENARIO_RE.search(s))
                score = (2.0 * min(focus, 3) + 1.0 * min(section_focus, 1) + 1.5 * view
                         + 1.5 * (risk and want_risks) + 40 * hit.score)
                if not view and not risk:
                    score -= 1.5
                if DESCRIPTIVE_RE.search(s):
                    score -= 1.5
                kind = "scenario" if scen and want_scen else "risk" if (risk and want_risks) else "rationale"
                # Narrative findings must carry a view, expectation or risk -
                # pure descriptions of past price moves are not rationale.
                if kind == "rationale" and not view:
                    continue
                if kind == "risk" and not risk:
                    continue
                if kind == "rationale" and not want_rationale:
                    continue
                cands.append((score, c, s, kind))
        cands.sort(key=lambda x: (-x[0], x[1]["publication_date"] or ""))
        limits = {"rationale": 6, "risk": 5, "scenario": 3}
        per_chunk: dict[str, int] = {}
        picked: list[tuple] = []
        for score, c, s, kind in cands:
            if score < 1.5:
                continue
            if sum(1 for p in picked if p[3] == kind) >= limits[kind]:
                continue
            if per_chunk.get(c["chunk_id"], 0) >= 2:
                continue
            if any(_jaccard(s, p[2]) >= 0.7 for p in picked):
                continue
            per_chunk[c["chunk_id"]] = per_chunk.get(c["chunk_id"], 0) + 1
            picked.append((score, c, s, kind))
        picked.sort(key=lambda p: (p[1]["publication_date"] or ""), reverse=True)
        for n, (score, c, s, kind) in enumerate(picked, 1):
            ev = self._evidence(c, s)
            resp.evidence.append(ev)
            resp.findings.append(Finding(finding_id=f"{self.name}-F{n}", kind=kind, statement=s,
                                         statement_mode="verbatim", evidence_ids=[ev.evidence_id],
                                         instruments=task.instruments))
        if not picked:
            labels = {f.instrument_key: f.instrument_label for f in resp.forecasts}
            what = ", ".join([labels.get(k, k) for k in task.instruments] or task.currencies or task.issuers
                             or task.sectors or [SPECIALIST_LABELS[self.name]])
            detail = (f"The research publishes the {what} forecast shown, but no written commentary explaining it "
                      f"in this window." if resp.forecasts else
                      f"No written commentary on {what} was found in OCBC research published in this window.")
            resp.coverage.append(Coverage(status="no_relevant_information", detail=detail))

    # ------------------------------------------------------------------ entry
    def run(self, task: SpecialistTask) -> SpecialistResponse:
        if task.specialist != self.name:
            raise ValueError("task routed to the wrong specialist")
        handles = self.registry.grant(self.name)
        resp = SpecialistResponse(task_id=task.task_id, specialist=self.name, status="ok")
        if not handles:
            resp.status = "error"
            resp.limitations.append("The research collections have not been built yet (run ingestion).")
            return resp
        resp.documents_considered = sum(h.meta.get("documents", 0) for h in handles)
        if resp.documents_considered == 0:
            resp.status = "no_evidence"
            resp.coverage.append(Coverage(status="no_relevant_information",
                                          detail=f"No {self.name.upper()} research documents were published in the "
                                                 f"ingested window ({task.corpus.window_start} to {task.corpus.window_end})."))
        else:
            if "forecast" in task.info_types:
                self._forecasts(task, handles, resp)
            self._narrative(task, handles, resp)
        if not embedding.available():
            resp.limitations.append(embedding.error() or "semantic retrieval unavailable; lexical retrieval only")
        problems = self.status.problems_for(self.name)
        for p in problems["inaccessible"]:
            resp.coverage.append(Coverage(status="document_inaccessible", detail=p))
        for p in problems["extraction_failed"]:
            resp.coverage.append(Coverage(status="extraction_failed", detail=p))
        for p in problems["sections_failed"]:
            resp.limitations.append(f"Research section could not be checked during ingestion: {p}")
        if resp.conflicts:
            resp.coverage.append(Coverage(status="conflicting_sources",
                                          detail=f"{len(resp.conflicts)} forecast conflict(s) or revision(s) detected"))
        if any(e.ocr for e in resp.evidence):
            resp.limitations.append("Some evidence was extracted by OCR from image-only pages; verify against the page image.")
        if resp.documents_considered and not resp.findings and not resp.forecasts:
            resp.status = "no_evidence"
        elif resp.coverage and any(c.status != "found" for c in resp.coverage):
            resp.status = "partial" if (resp.findings or resp.forecasts) else resp.status
        return resp
