"""DEVELOPMENT FIXTURE: an offline mock of the OCBC research listing pages
(httpx.MockTransport) so the full ingestion pipeline can be exercised without
network access and without touching the real corpus."""
from __future__ import annotations

import urllib.parse

import httpx

from tests.fixtures import make_fixtures as mf

PDF_BASE = "/iwov-resources/sg/ocbc/gbc/pdf/TestFixtures/"
_PDF_CACHE: dict[str, bytes] = {}

FX = "FX And Rates : FX Weekly"
FX_ITEMS = [
    ("FX Outlook Older Test", "26 Oct 2026", "older.pdf", FX),
    ("FX Outlook Newer Test", "28 Oct 2026", "newer.pdf", FX),
    ("FX Alternative Test", "28 Oct 2026", "samedate.pdf", FX),
    ("Date Conflict Test", "30 Oct 2026", "conflictdate.pdf", FX),
    ("Broken File Test", "30 Oct 2026", "notapdf.pdf", FX),
    ("Duplicate Copy Test", "28 Oct 2026", "duplicate-copy.pdf", FX),
    ("Forbidden Test", "29 Oct 2026", "forbidden.pdf", FX),
    ("Old Report Test", "02 Sep 2026", "old.pdf", FX),
]
MACRO_ITEMS = [
    ("Scanned Macro Note", "29 Oct 2026", "scanned.pdf", "Macro Views : Weekly Macro View"),
    ("Macro Weekly Test", "27 Oct 2026", "malicious.pdf", "Macro Views : Weekly Macro View"),
]
EMPTY = ('<div class="media-filter-media-listing__result_wrapper"><div class="subcategory">Empty</div>'
         'No articles found</div>' + " " * 300)
CATEGORY_PAGE = ('<html><input type=hidden id=componentURI '
                 'value="/group/research/research-with-filter/1583140122563.ajax"></html>')


def card(title: str, date: str, href: str, label: str) -> str:
    return (f'<div class="col-md-6 col-lg-4 media-filter-media-listing__item" data-subcategory="test">'
            f'<div class="report__article media-filter-media-listing__article"><div class="media-filter-media-listing__article-inner">'
            f'<p>{label}</p><h3><strong>{title}</strong></h3><small>{date}</small>'
            f'<a href="{href}">Download</a></div></div></div>')


def _wrapper(section: str, items) -> str:
    return (f'<div class="media-filter-media-listing media-filter-media-listing__result_wrapper">'
            f'<div class="subcategory subcategory--black">{section}</div><div class="row">'
            + "".join(card(t, d, PDF_BASE + f, label) for t, d, f, label in items) + "</div></div>")


def _pdfs() -> dict[str, bytes]:
    if not _PDF_CACHE:  # identical bytes on every request/run (idempotency tests)
        _PDF_CACHE.update({
            "older.pdf": mf.forecast_pdf("26 October 2026", "15 October 2026", ["1.2700", "1.2670", "1.2630", "1.2550"],
                                         "FX Outlook Older Test", eur_values=["1.12", "1.11", "1.11", "1.13"]),
            "newer.pdf": mf.forecast_pdf("28 October 2026", "25 October 2026", ["1.2700", "1.2670", "1.2630", "1.2550"],
                                         "FX Outlook Newer Test"),
            "samedate.pdf": mf.forecast_pdf("28 October 2026", None, ["1.2900", "1.2670", "1.2630", "1.2550"],
                                            "FX Alternative Test"),
            "malicious.pdf": mf.malicious_pdf("27 October 2026"),
            "scanned.pdf": mf.scanned_pdf("29 October 2026"),
            "conflictdate.pdf": mf.dated_pdf("10 October 2026", "Date Conflict Test"),
            "notapdf.pdf": b"<html><body>Not a PDF</body></html>",
        })
        _PDF_CACHE["duplicate-copy.pdf"] = _PDF_CACHE["newer.pdf"]
    return _PDF_CACHE


def build_site(fail_credit_listing: bool = True) -> httpx.MockTransport:
    pdfs = _pdfs()
    fx_listing = _wrapper("Foreign Exchange (FX)", FX_ITEMS)
    macro_listing = _wrapper("Weekly Macro Views", MACRO_ITEMS)

    def handler(request: httpx.Request) -> httpx.Response:
        path = urllib.parse.unquote(request.url.path)
        if path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /eforms/\n")
        if path.startswith("/group/research/research-with-filter/") and path.endswith(".ajax"):
            form = urllib.parse.parse_qs(request.content.decode())
            cat = form.get("category", [""])[0]
            month = form.get("monthParam", [""])[0]
            if cat == "credit" and fail_credit_listing:
                return httpx.Response(500, text="error")
            if month == "october" and cat == "fxandrates":
                return httpx.Response(200, text=fx_listing)
            if month == "october" and cat == "macro":
                return httpx.Response(200, text=macro_listing)
            return httpx.Response(200, text=EMPTY)
        if path.startswith("/group/research/"):
            return httpx.Response(200, text=CATEGORY_PAGE)
        if path.startswith(PDF_BASE):
            name = path[len(PDF_BASE):]
            if name == "forbidden.pdf":
                return httpx.Response(403, text="forbidden")
            if name in pdfs:
                return httpx.Response(200, content=pdfs[name], headers={
                    "content-type": "application/pdf", "last-modified": "Sun, 01 Nov 2026 00:00:00 GMT"})
            return httpx.Response(404)
        return httpx.Response(404)

    return httpx.MockTransport(handler)
