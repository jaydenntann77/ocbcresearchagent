"""Publication-date resolution.

Signals (HTTP Last-Modified is recorded but never used):
  L  website listing date (the date printed on the OCBC listing card)
  P  printed document date (first date in the page-1 header region)
  M  PDF metadata creation date (SGT) - corroboration only
  F  date embedded in the file name - pre-download screening only

Rule (documented in README "Date resolution rule"):
  1. L and P present and equal          -> P, confidence high
  2. L and P present, differ <= 3 days  -> P, confidence medium, discrepancy flagged
  3. L and P present, differ  > 3 days  -> quarantine (conflicting dates)
  4. only L present                     -> L, high if M within 3 days of L, else medium (flagged)
  5. only P present                     -> P, medium (no listing date to corroborate)
  6. neither                            -> quarantine (publication date cannot be established)
Eligibility uses the resolved date; quarantined documents are never indexed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.common.timeutil import SGT, find_all_dates, parse_pdf_meta_date

TOLERANCE_DAYS = 3


@dataclass
class DateResolution:
    publication_date: date | None
    confidence: str            # high | medium | low
    basis: str
    quarantine: bool
    listing_date: date | None = None
    printed_date: date | None = None
    meta_date: date | None = None
    flags: list[str] = field(default_factory=list)


def printed_date_from_page(text: str) -> date | None:
    """First date in the header region of page 1 (the first ~1200 chars)."""
    hits = find_all_dates(text[:1200])
    return hits[0][1] if hits else None


def filename_date(url: str) -> date | None:
    name = url.rsplit("/", 1)[-1]
    m = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    hits = find_all_dates(name.replace("%20", " "))
    return hits[0][1] if hits else None


def resolve(listing: date | None, printed: date | None, meta_raw: str | None) -> DateResolution:
    meta_dt = parse_pdf_meta_date(meta_raw)
    meta = meta_dt.astimezone(SGT).date() if meta_dt else None
    flags: list[str] = []
    if listing and printed:
        diff = abs((listing - printed).days)
        if diff == 0:
            return DateResolution(printed, "high", "listing date and printed date agree", False,
                                  listing, printed, meta, flags)
        if diff <= TOLERANCE_DAYS:
            flags.append(f"listing date {listing} differs from printed date {printed} by {diff} day(s); printed date used")
            return DateResolution(printed, "medium", "printed date (minor listing discrepancy)", False,
                                  listing, printed, meta, flags)
        flags.append(f"listing date {listing} conflicts with printed date {printed} ({diff} days)")
        return DateResolution(None, "low", "conflicting listing and printed dates", True, listing, printed, meta, flags)
    if listing:
        if meta and abs((meta - listing).days) <= TOLERANCE_DAYS:
            return DateResolution(listing, "high", "listing date corroborated by PDF metadata", False,
                                  listing, None, meta, flags)
        flags.append("no printed date found; listing date not corroborated by PDF metadata")
        return DateResolution(listing, "medium", "listing date only", False, listing, None, meta, flags)
    if printed:
        flags.append("no website listing date; printed date used")
        return DateResolution(printed, "medium", "printed date only", False, None, printed, meta, flags)
    flags.append("publication date could not be established")
    return DateResolution(None, "low", "no reliable date", True, None, None, meta, flags)
