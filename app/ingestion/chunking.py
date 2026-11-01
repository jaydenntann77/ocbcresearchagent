"""Turn extracted pages into retrieval chunks, route them to specialist
collections and flag embedded instructions.

* Prose is grouped under its running section heading (max ~1,200 chars),
  never crossing a page boundary so every chunk has one PDF page.
* Each table is its own chunk with its header and footnotes; long generic
  tables are split by rows with the header repeated, so values are never
  detached from their column labels.
"""
from __future__ import annotations

import collections
import hashlib
import re
from dataclasses import dataclass, field

from app.common import config
from app.common.instruments import normalise_pair, search_tokens_for
from app.ingestion.pdfparse import ExtractedDocument, ExtractedTable

MAX_CHARS = 1200
BOILERPLATE = re.compile(
    r"(OCBC Research Insights|Follow our podcasts|on Telegram|^By Global Markets|^\d{1,2} \w+ 20\d{2}$|"
    r"^By Global Markets \||Disclaimer|Important disclosures?)", re.I)

INJECTION_PATTERNS = [
    re.compile(r"\b(ignore|disregard|forget)\b.{0,40}\b(previous|prior|above|earlier|all)\b.{0,30}\b(instructions?|prompts?|rules)\b", re.I),
    re.compile(r"\bsystem prompt\b", re.I),
    re.compile(r"\byou are (now )?(an? )?(ai|assistant|language model|chatbot|claude|gpt)\b", re.I),
    re.compile(r"\b(as an ai|ai assistant)\b.{0,40}\b(must|should|will)\b", re.I),
    re.compile(r"\b(tell|instruct|advise) (the )?(user|reader|client|salesperson)s? to\b", re.I),
    re.compile(r"</?\s*(system|instructions?|assistant|user)\s*>", re.I),
    re.compile(r"\bdo not (tell|inform|reveal to) (the )?(user|client)\b", re.I),
    re.compile(r"\b(override|bypass) (the )?(rules|guardrails|validation|policy)\b", re.I),
]


def detect_injection(text: str) -> str | None:
    for rx in INJECTION_PATTERNS:
        m = rx.search(text)
        if m:
            return f"embedded instruction-like text: '{m.group(0)[:80]}'"
    return None


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    pdf_page: int
    printed_page: str | None
    section: str | None
    kind: str
    text: str
    table_id: str | None
    seq: int
    ocr: bool
    specialists: list[str] = field(default_factory=list)
    suspicious_reason: str | None = None

    @property
    def search_extra(self) -> str:
        return search_tokens_for(self.text)


def _policy():
    return config.load_json_config("specialists.json")


def lexicon_scores(text: str) -> dict[str, int]:
    low = f" {text.lower()} "
    scores = {}
    for spec, terms in _policy()["lexicon"].items():
        scores[spec] = sum(1 for t in terms if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low))
    return scores


def primary_specialist(category: str | None, section: str | None, subcategory: str | None) -> str | None:
    prim = _policy()["category_primary"]
    for key in (section, category):
        if key and key in prim:
            return prim[key]
    sub = (subcategory or "").lower()
    if "rate" in sub:
        return "rates"
    if sub.startswith("fx") or "asiafx" in sub:
        return "fx"
    return None


def route(text: str, primary: str | None) -> list[str]:
    scores = lexicon_scores(text)
    threshold = _policy()["secondary_threshold"]
    specs = [primary] if primary else []
    for spec, sc in sorted(scores.items(), key=lambda kv: -kv[1]):
        if spec not in specs and sc >= threshold:
            specs.append(spec)
    if not specs:
        best = max(scores.items(), key=lambda kv: kv[1])
        specs = [best[0] if best[1] > 0 else "macro"]
    return specs


def forecast_key_specialists(key: str) -> list[str]:
    routing = _policy()["forecast_key_routing"]
    if normalise_pair(key) or key == "DXY":
        return ["fx"]
    if key in routing:
        v = routing[key]
        return v if isinstance(v, list) else [v]
    return [routing["rates_default"]]


def _cid(doc_id: str, page: int, seq: int, text: str) -> str:
    return f"{doc_id}-p{page}-c{seq}-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]


def boilerplate_headings(doc: ExtractedDocument) -> set[str]:
    counts = collections.Counter(h for p in doc.pages for h in {h for _, h in p.headings})
    n = max(1, len(doc.pages))
    return {h for h, c in counts.items() if n >= 3 and c / n >= 0.5}


def table_chunks(table: ExtractedTable, max_chars: int = 3000) -> list[str]:
    head = []
    if table.title:
        head.append(table.title)
    head.append(" | ".join(table.header))
    foot = table.footnotes
    body = [" | ".join(r) for r in table.rows]
    if len("\n".join(head + body + foot)) <= max_chars or table.kind == "forecast":
        return ["\n".join(head + body + foot)]
    parts, cur = [], []
    for line in body:
        if cur and len("\n".join(head + cur + [line])) > max_chars:
            parts.append("\n".join(head + cur + foot))
            cur = []
        cur.append(line)
    if cur:
        parts.append("\n".join(head + cur + foot))
    return parts


def build_chunks(doc_id: str, doc: ExtractedDocument, primary: str | None) -> list[Chunk]:
    boiler = boilerplate_headings(doc)
    chunks: list[Chunk] = []
    seq = 0
    section = None
    for page in doc.pages:
        heads = sorted((y, h) for y, h in page.headings if h not in boiler and not BOILERPLATE.search(h))
        cur: list[str] = []
        cur_section = section

        def flush():
            nonlocal seq, cur
            text = "\n".join(cur).strip()
            if len(text) >= 40:
                seq += 1
                chunks.append(Chunk(_cid(doc_id, page.pdf_page, seq, text), doc_id, page.pdf_page, page.printed_page,
                                    cur_section, "prose", text, None, seq, page.ocr))
            cur = []

        for y, text in page.blocks:
            if BOILERPLATE.search(text) and len(text) < 120:
                continue
            new_heads = [h for hy, h in heads if abs(hy - y) < 1]
            if new_heads:
                flush()
                section = cur_section = new_heads[0]
                if text == new_heads[0]:
                    continue
            if cur and len("\n".join(cur)) + len(text) > MAX_CHARS:
                flush()
            cur.append(text)
        flush()
        for t in page.tables:
            for part in table_chunks(t):
                seq += 1
                chunks.append(Chunk(_cid(doc_id, page.pdf_page, seq, part), doc_id, page.pdf_page, page.printed_page,
                                    t.title or section, "table", part, t.table_id, seq, page.ocr))
    for c in chunks:
        c.suspicious_reason = detect_injection(c.text)
        if c.kind == "table" and any(t.kind == "forecast" and t.table_id == c.table_id
                                     for p in doc.pages for t in p.tables):
            table = next(t for p in doc.pages for t in p.tables if t.table_id == c.table_id)
            specs = []
            for cell in table.cells:
                for s in forecast_key_specialists(cell.instrument_key):
                    if s not in specs:
                        specs.append(s)
            c.specialists = specs or route(c.text, primary)
        else:
            c.specialists = route(f"{c.section or ''} {c.text}", primary)
    return chunks
