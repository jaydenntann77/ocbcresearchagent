"""PDF validation and extraction: prose, headings, printed page numbers,
tables (generic and forecast), with OCR fallback for image-only pages.

PDF text is untrusted data. Nothing here interprets or executes it."""
from __future__ import annotations

import hashlib
import re
import statistics
from dataclasses import dataclass, field

import fitz  # PyMuPDF

from app.common.instruments import instrument_key
from app.common.timeutil import horizon_end_date

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
PERIOD_RE = re.compile(
    rf"^(?:(?:{MONTHS})[-'](?:\d{{2}}|\d{{4}})|[1-4]Q[-']?\d{{2}}F?|\d{{1,2}}M|\d{{1,2}}-?mth|20\d{{2}}F?|FY\d{{2,4}}F?|"
    rf"Current|Spot|Actual|Latest|Last)$", re.I)
OBSERVATION_RE = re.compile(r"^(Current|Spot|Actual|Latest|Last)", re.I)
NUMERIC_RE = re.compile(r"^[-+−]?\(?\d[\d,]*(?:\.\d+)?\)?%?(?:[-–]\d[\d,]*(?:\.\d+)?%?)?$")
UNIT_RE = re.compile(r"(\$/\w+|USD/\w+|%|bps|bp\b)", re.I)
DATA_DATE_RE = re.compile(r"(Latest Forecast Update:?\s*[^)\n]+|as at [0-9]{1,2} \w+ 20\d{2}|data as of [^)\n]+)", re.I)


class PdfInvalid(Exception):
    pass


@dataclass
class ForecastCell:
    instrument_label: str
    instrument_key: str
    group_label: str | None
    horizon_label: str
    horizon_kind: str          # absolute | relative
    horizon_end: str | None
    value: str
    unit: str | None
    is_observation: bool       # spot / current column - never a forecast
    scenario: str | None


@dataclass
class ExtractedTable:
    table_id: str
    page: int
    kind: str                  # forecast | generic
    title: str | None
    header: list[str]
    rows: list[list[str]]
    footnotes: list[str]
    data_date: str | None
    bbox: tuple
    cells: list[ForecastCell] = field(default_factory=list)

    def as_text(self) -> str:
        lines = []
        if self.title:
            lines.append(self.title)
        lines.append(" | ".join(self.header))
        lines.extend(" | ".join(r) for r in self.rows)
        lines.extend(self.footnotes)
        return "\n".join(lines)


@dataclass
class PageContent:
    pdf_page: int
    printed_page: str | None
    text: str                  # prose text (table regions removed)
    full_text: str             # all text on the page (for verification)
    headings: list[tuple[float, str]]  # (y, heading)
    blocks: list[tuple[float, str]]     # (y, paragraph text)
    ocr: bool = False
    ocr_failed: bool = False
    tables: list[ExtractedTable] = field(default_factory=list)


@dataclass
class ExtractedDocument:
    sha256: str
    page_count: int
    title: str | None
    author: str | None
    meta_creation: str | None
    pages: list[PageContent]
    warnings: list[str] = field(default_factory=list)


def validate_pdf_bytes(data: bytes) -> fitz.Document:
    if not data.startswith(b"%PDF-"):
        raise PdfInvalid("content is not a PDF (missing %PDF- signature)")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise PdfInvalid(f"PDF could not be opened: {exc}") from exc
    if doc.needs_pass and not doc.authenticate(""):
        raise PdfInvalid("PDF is password protected")
    if doc.page_count == 0:
        raise PdfInvalid("PDF has no pages")
    return doc


# ------------------------------------------------------------------ OCR
_ocr_engine = None
_ocr_error: str | None = None


def _ocr(page: fitz.Page) -> str | None:
    global _ocr_engine, _ocr_error
    if _ocr_error:
        return None
    try:
        if _ocr_engine is None:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        pix = page.get_pixmap(dpi=200)
        result, _ = _ocr_engine(pix.tobytes("png"))
    except Exception as exc:  # noqa: BLE001
        _ocr_error = f"OCR unavailable: {exc}"
        return None
    if not result:
        return ""
    # result: [ [box, text, score], ... ]; order top-to-bottom, left-to-right
    items = sorted(result, key=lambda r: (round(r[0][0][1] / 12), r[0][0][0]))
    return "\n".join(r[1] for r in items if float(r[2]) >= 0.5)


# ------------------------------------------------------------------ helpers
def _lines_from_words(words, tol: float = 2.5):
    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines: list[list] = []
    for w in words:
        yc = (w[1] + w[3]) / 2
        if lines and abs(((lines[-1][0][1] + lines[-1][0][3]) / 2) - yc) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w[0]) for ln in lines]


def _line_text(line) -> str:
    return " ".join(w[4] for w in line)


def _in_bbox(w, bbox, pad=1.0) -> bool:
    x0, y0, x1, y1 = bbox
    cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
    return x0 - pad <= cx <= x1 + pad and y0 - pad <= cy <= y1 + pad


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace(" ", " ").replace("\xa0", " ")).strip()


# ------------------------------------------------------------------ forecast tables
def _header_columns(line) -> list[dict] | None:
    """Return column descriptors if the line looks like a period header."""
    tokens = [(i, w) for i, w in enumerate(line) if PERIOD_RE.match(w[4].strip("():,"))]
    forward = [t for t in tokens if not OBSERVATION_RE.match(t[1][4])]
    if len(forward) < 2 or len(tokens) < len(line) * 0.4:
        return None
    cols = []
    idxs = [i for i, _ in tokens]
    for n, (i, w) in enumerate(tokens):
        end = idxs[n + 1] if n + 1 < len(idxs) else len(line)
        span = line[i:end] if OBSERVATION_RE.match(w[4]) else [w]
        label = " ".join(x[4] for x in span)
        cols.append({"label": label, "x0": span[0][0], "x1": span[-1][2],
                     "xc": (w[0] + w[2]) / 2, "obs": bool(OBSERVATION_RE.match(w[4]))})
    return cols


def _extract_forecast_tables(page: fitz.Page, pno: int, lines) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    i = 0
    while i < len(lines):
        cols = _header_columns(lines[i])
        if not cols:
            i += 1
            continue
        header_line = lines[i]
        hy = header_line[0][3]
        # Observation columns ("Current (25 Sep)") whose header words sit on
        # adjacent lines because the header cell wraps.
        near = [ln for ln in lines[max(0, i - 1):i + 2]
                if ln is not header_line and abs(ln[0][1] - header_line[0][1]) <= 10]
        if not any(c["obs"] for c in cols):
            obs_words = [w for ln in near for w in ln if OBSERVATION_RE.match(w[4]) and w[2] < cols[0]["x0"]]
            if obs_words:
                anchor = obs_words[0]
                span = sorted([w for ln in near for w in ln if anchor[0] - 4 <= w[0] < cols[0]["x0"] - 4],
                              key=lambda w: (w[1], w[0]))
                cols.insert(0, {"label": " ".join(w[4] for w in span), "x0": anchor[0],
                                "x1": max(w[2] for w in span), "xc": (anchor[0] + anchor[2]) / 2, "obs": True})
        # Skip a wrapped header continuation line (e.g. "Sep)") below the header.
        j = i + 1
        if j < len(lines) and lines[j][0][1] - hy < 12 and not any(NUMERIC_RE.match(w[4]) for w in lines[j])                 and lines[j][0][0] >= min(c["x0"] for c in cols) - 15:
            if lines[j] not in near:
                for w in lines[j]:
                    for c in cols:
                        if c["obs"] and c["x0"] - 8 <= w[0] <= c["x1"] + 30:
                            c["label"] += " " + w[4]
            j += 1
        spacing = min((b["xc"] - a["xc"] for a, b in zip(cols, cols[1:])), default=60) or 60
        first_left = cols[0]["xc"] - spacing * 0.6
        # Title: nearest line above (within 90pt) mentioning forecast(s).
        title = None
        for k in range(i - 1, max(-1, i - 6), -1):
            t = _line_text(lines[k])
            if hy - lines[k][0][3] > 90:
                break
            if re.search(r"forecast", t, re.I):
                title = _clean(re.sub(r"^.*?\|\s*\d{1,2} \w+ 20\d{2}\s*", "", t))
                break
        rows, cells, footnotes, group = [], [], [], None
        last_y = lines[j - 1][0][3]
        k = j
        while k < len(lines):
            ln = lines[k]
            text = _line_text(ln)
            if ln[0][1] - last_y > 45:
                break
            if _header_columns(ln):
                break
            if re.match(r"^(Source|Note|Notes|\*)", text, re.I):
                foot = [_clean(text)]
                m = k + 1
                while m < len(lines) and lines[m][0][1] - lines[m - 1][0][3] < 6 \
                        and not _header_columns(lines[m]) and not re.match(r"^(Source|Note)", _line_text(lines[m]), re.I):
                    foot.append(_clean(_line_text(lines[m])))
                    m += 1
                footnotes.append(" ".join(foot))
                k = m
                last_y = lines[m - 1][0][3]
                continue
            toks = [w for w in ln if _clean(w[4])]
            if not toks:
                k += 1
                continue
            nums = [w for w in toks if (NUMERIC_RE.match(w[4]) or re.fullmatch(r"n\.?a\.?|NA|[-–]", w[4]))
                    and (w[0] + w[2]) / 2 > first_left]
            label = _clean(" ".join(w[4] for w in toks if w not in nums and (w[0] + w[2]) / 2 <= first_left))
            if not nums:
                text_all = _clean(" ".join(w[4] for w in toks))
                if text_all and len(text_all) < 80 and toks[0][0] < first_left:
                    group = text_all
                    rows.append([text_all] + [""] * len(cols))
                    last_y = ln[0][3]
                    k += 1
                    continue
                break
            if not label:
                break
            row = [label] + [""] * len(cols)
            for w in nums:
                xc = (w[0] + w[2]) / 2
                best = min(range(len(cols)), key=lambda c: abs(cols[c]["xc"] - xc))
                if abs(cols[best]["xc"] - xc) <= spacing * 0.6 and not row[best + 1]:
                    row[best + 1] = w[4]
            rows.append(row)
            unit_m = UNIT_RE.search(label)
            for c, col in enumerate(cols):
                if not row[c + 1]:
                    continue
                hlabel = _clean(col["label"])
                end = horizon_end_date(hlabel)
                scen = None
                for src in (title or "", group or ""):
                    sm = re.search(r"\b(base|bull|bear|upside|downside|adverse|risk)\s*(case|scenario)?\b", src, re.I)
                    if sm and "scenario" in src.lower():
                        scen = _clean(sm.group(0))
                cells.append(ForecastCell(
                    instrument_label=label, instrument_key=instrument_key(label), group_label=group,
                    horizon_label=hlabel, horizon_kind="absolute" if end else "relative",
                    horizon_end=end.isoformat() if end else None, value=row[c + 1],
                    unit=unit_m.group(1) if unit_m else None, is_observation=col["obs"], scenario=scen))
            last_y = ln[0][3]
            k += 1
        context = " ".join([title or "", group or ""] + [r[0] for r in rows if not any(r[1:])] + footnotes)
        is_forecast = bool(re.search(r"forecast", context, re.I))
        if cells:
            data_date = None
            for f in footnotes + [title or ""]:
                dm = DATA_DATE_RE.search(f)
                if dm:
                    data_date = _clean(dm.group(1)).rstrip(")")
                    break
            y0 = header_line[0][1]
            y1 = lines[k - 1][0][3] if k > i else hy
            tid = f"p{pno}-t{len(tables) + 1}"
            tables.append(ExtractedTable(
                table_id=tid, page=pno, kind="forecast" if is_forecast else "generic", title=title,
                header=["Instrument"] + [_clean(c["label"]) for c in cols], rows=rows, footnotes=footnotes,
                data_date=data_date, bbox=(0, y0 - 2, page.rect.width, y1 + 2),
                cells=cells if is_forecast else []))
        i = max(k, i + 1)
    return tables


def _extract_generic_tables(page: fitz.Page, pno: int, taken: list[tuple], start_index: int) -> list[ExtractedTable]:
    out = []
    try:
        found = page.find_tables().tables
    except Exception:  # noqa: BLE001
        return out
    for t in found:
        bbox = tuple(t.bbox)
        if any(not (bbox[3] < b[1] or bbox[1] > b[3]) for b in taken):
            continue  # overlaps a forecast table already parsed from word layout
        rows = t.extract()
        keep = [j for j in range(t.col_count) if any(_clean(r[j] or "") for r in rows)]
        clean_rows = [[_clean(r[j] or "") for j in keep] for r in rows]
        clean_rows = [r for r in clean_rows if any(r)]
        if len(clean_rows) < 2 or len(keep) < 2:
            continue
        out.append(ExtractedTable(
            table_id=f"p{pno}-t{start_index + len(out) + 1}", page=pno, kind="generic", title=None,
            header=clean_rows[0], rows=clean_rows[1:], footnotes=[], data_date=None, bbox=bbox))
    return out


# ------------------------------------------------------------------ page + document
def _headings_and_blocks(page: fitz.Page, exclude: list[tuple]) -> tuple[list, list]:
    d = page.get_text("dict")
    sizes = []
    for b in d["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                if sp["text"].strip():
                    sizes.append(round(sp["size"], 1))
    body = statistics.median(sizes) if sizes else 10
    headings, blocks = [], []
    for b in d["blocks"]:
        if "lines" not in b:
            continue
        y = b["bbox"][1]
        if any(_in_bbox((b["bbox"][0], b["bbox"][1], b["bbox"][2], b["bbox"][3]), ex, pad=2) for ex in exclude):
            continue
        text = _clean(" ".join(sp["text"] for ln in b["lines"] for sp in ln["spans"]))
        if not text:
            continue
        spans = [sp for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()]
        big = spans and all(sp["size"] >= body * 1.15 for sp in spans)
        bold = spans and all("bold" in sp["font"].lower() or sp["flags"] & 16 for sp in spans)
        if len(text) <= 90 and (big or bold) and not re.match(r"^[\d.,%\s-]+$", text):
            headings.append((y, text))
        blocks.append((y, text))
    return headings, blocks


def _printed_page_number(lines, pno: int) -> str | None:
    """Printed folio from the running header/footer. Only values within 3 of
    the PDF page index are accepted to avoid picking up stray figures."""
    cands = lines[:12] + lines[-4:]
    ok = lambda v: abs(int(v) - pno) <= 3
    for ln in cands:
        t = _line_text(ln).strip()
        if re.fullmatch(r"\d{1,3}", t) and ok(t):
            return t
        toks = [w[4] for w in ln if _clean(w[4])]
        # Running header such as "... on Telegram! 7"
        if 2 <= len(toks) <= 14 and re.fullmatch(r"\d{1,3}", toks[-1]) and not any(
                re.search(r"\d", x) for x in toks[:-1]) and ok(toks[-1]):
            return toks[-1]
        m = re.fullmatch(r"(?:Page|p\.)\s*(\d{1,3})(?:\s*of\s*\d+)?", t, re.I)
        if m and ok(m.group(1)):
            return m.group(1)
    return None


def extract(data: bytes) -> ExtractedDocument:
    doc = validate_pdf_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    meta = doc.metadata or {}
    pages: list[PageContent] = []
    warnings: list[str] = []
    for i, page in enumerate(doc):
        pno = i + 1
        full = page.get_text("text")
        ocr = ocr_failed = False
        if len(full.strip()) < 80 and page.get_images():
            text = _ocr(page)
            if text is None:
                ocr_failed = True
                warnings.append(f"page {pno}: image-only page and {_ocr_error or 'OCR failed'}")
                text = full
            else:
                ocr = bool(text.strip())
            pages.append(PageContent(pno, None, _clean(text), _clean(text), [], [(0, _clean(text))] if text.strip() else [],
                                     ocr=ocr, ocr_failed=ocr_failed))
            continue
        words = page.get_text("words")
        lines = _lines_from_words(words)
        ftables = _extract_forecast_tables(page, pno, lines)
        gtables = _extract_generic_tables(page, pno, [t.bbox for t in ftables], len(ftables))
        tables = ftables + gtables
        page_dd = DATA_DATE_RE.search(full)
        for t in ftables:
            if t.kind == "forecast" and not t.data_date and page_dd:
                # Stated once on the page for all forecast tables on it.
                t.data_date = _clean(page_dd.group(1)).rstrip(")")
        headings, blocks = _headings_and_blocks(page, [t.bbox for t in tables])
        prose = "\n".join(t for _, t in blocks)
        pages.append(PageContent(pno, _printed_page_number(lines, pno), prose, _clean(full), headings, blocks,
                                 tables=tables))
    title = _clean(meta.get("title") or "") or None
    if title and not re.search(r"[A-Za-z]{3}", title):
        title = None
    return ExtractedDocument(sha, doc.page_count, title, _clean(meta.get("author") or "") or None,
                             meta.get("creationDate"), pages, warnings)
