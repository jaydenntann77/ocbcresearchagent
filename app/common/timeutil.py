"""Asia/Singapore time helpers. Singapore has no DST, so a fixed UTC+8 offset
is exact and avoids depending on a tz database (absent on some Windows hosts)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

SGT = timezone(timedelta(hours=8), "SGT")

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def now_sgt() -> datetime:
    return datetime.now(SGT)


def today_sgt() -> date:
    return now_sgt().date()


def ingestion_window(days: int, today: date | None = None) -> tuple[date, date]:
    """Inclusive window of `days` calendar dates ending today (SGT)."""
    end = today or today_sgt()
    return end - timedelta(days=days - 1), end


def fmt_date(d: date | None) -> str:
    return d.strftime("%d %b %Y").lstrip("0") if d else "unknown"


def fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "never"
    return dt.astimezone(SGT).strftime("%d %b %Y, %H:%M SGT").lstrip("0")


def fmt_range(start: date, end: date) -> str:
    if start == end:
        return f"{end.day} {end.strftime('%B %Y')}"
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {end.strftime('%B %Y')}"
    if start.year == end.year:
        return f"{start.day} {start.strftime('%B')} – {end.day} {end.strftime('%B %Y')}"
    return f"{start.day} {start.strftime('%B %Y')} – {end.day} {end.strftime('%B %Y')}"


_DATE_DMY = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+(\d{4})\b",
    re.IGNORECASE)
_DATE_MDY = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.IGNORECASE)


def parse_human_date(text: str) -> date | None:
    """Parse the first unambiguous '30 October 2026' / 'Oct 30, 2026' date."""
    for m in _DATE_DMY.finditer(text):
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            continue
    for m in _DATE_MDY.finditer(text):
        try:
            return date(int(m.group(3)), MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        except ValueError:
            continue
    return None


def find_all_dates(text: str) -> list[tuple[int, date]]:
    out = []
    for m in _DATE_DMY.finditer(text):
        try:
            out.append((m.start(), date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))))
        except ValueError:
            pass
    return sorted(out)


def parse_pdf_meta_date(value: str | None) -> datetime | None:
    """PDF 'D:20261029111659+08'00'' -> aware datetime."""
    if not value:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([+\-Z])?(\d{2})?'?(\d{2})?", value)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh, mm, ss = int(m.group(4) or 0), int(m.group(5) or 0), int(m.group(6) or 0)
    tz = timezone.utc
    if m.group(7) in ("+", "-") and m.group(8):
        offset = timedelta(hours=int(m.group(8)), minutes=int(m.group(9) or 0))
        tz = timezone(offset if m.group(7) == "+" else -offset)
    try:
        return datetime(y, mo, d, hh, mm, ss, tzinfo=tz)
    except ValueError:
        return None


_HORIZON_MONTH = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s']?(\d{2}|\d{4})$", re.I)
_HORIZON_QTR = re.compile(r"^([1-4])Q[-\s']?(\d{2}|\d{4})F?$", re.I)
_HORIZON_YEAR = re.compile(r"^(?:FY|CY)?(20\d{2})F?$", re.I)


def horizon_end_date(label: str) -> date | None:
    """End date of an absolute horizon label (Dec-27, 4Q26, 2027). Relative
    labels such as 3M/12M return None (their anchor is report-specific)."""
    s = label.strip()
    m = _HORIZON_MONTH.match(s)
    if m:
        y = int(m.group(2))
        y = y + 2000 if y < 100 else y
        mo = MONTHS[m.group(1)[:3].lower()]
        nxt = date(y + (mo == 12), mo % 12 + 1, 1)
        return nxt - timedelta(days=1)
    m = _HORIZON_QTR.match(s)
    if m:
        y = int(m.group(2))
        y = y + 2000 if y < 100 else y
        q = int(m.group(1))
        mo = q * 3
        nxt = date(y + (mo == 12), mo % 12 + 1, 1)
        return nxt - timedelta(days=1)
    m = _HORIZON_YEAR.match(s)
    if m:
        return date(int(m.group(1)), 12, 31)
    return None
