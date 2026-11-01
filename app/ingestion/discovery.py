"""Discovery of OCBC research publications.

Sources checked (all inside the allow-listed OCBC research boundary):
  1. the research index ("Recent Updates") page;
  2. each research category page (static HTML);
  3. the AJAX listing component those category pages call
     (POST .../research-with-filter/<component>.ajax with monthParam /
     yearParam / category) for every calendar month overlapping the window -
     this endpoint returns the complete month listing (the "See more" button
     only pages client-side);
  4. the equity investment-reports page.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

from bs4 import BeautifulSoup

from app.common.timeutil import parse_human_date
from app.ingestion.fetcher import Fetcher, absolutise

CATEGORIES = {
    "macro": "Macro Views",
    "fxandrates": "FX And Rates",
    "special": "Sustainability And Commodities",
    "credit": "Credit Research",
    "equityresearch": "Equity Research",
}
INDEX_URL = "https://www.ocbc.com/group/research/index"
CATEGORY_URL = "https://www.ocbc.com/group/research/research-with-filter.page?category={cat}"
INVESTMENT_URL = "https://www.ocbc.com/group/research/investment-reports.page"
DEFAULT_COMPONENT = "/group/research/research-with-filter/1583140122563.ajax"
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
               "october", "november", "december"]


@dataclass
class ListingItem:
    url: str
    title: str
    listing_date: str | None       # ISO date as listed on the website
    listing_date_text: str | None
    category: str | None
    section: str | None
    subcategory: str | None
    found_on: str
    series: str | None = None
    sources: list[str] = field(default_factory=list)


@dataclass
class SectionCheck:
    source: str          # page or endpoint description
    category: str | None
    section: str | None
    status: str          # ok | empty | failed
    items: int
    detail: str = ""


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def parse_cards(html: str, found_on: str, category: str | None = None) -> tuple[list[ListingItem], list[tuple[str, int]]]:
    """Parse research article cards. Returns items and (section, count) pairs
    including sections that rendered 'No articles found'."""
    soup = BeautifulSoup(html, "lxml")
    items: list[ListingItem] = []
    sections: list[tuple[str, int]] = []
    wrappers = soup.select(".media-filter-media-listing__result_wrapper")
    scopes = [(w, _text(w.select_one(".subcategory"))) for w in wrappers] or [(soup, None)]
    for scope, section in scopes:
        count = 0
        for art in scope.select(".media-filter-media-listing__article"):
            link = art.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            if ".pdf" not in href.lower():
                continue
            item_el = art.find_parent(class_="media-filter-media-listing__item")
            date_text = _text(art.find("small")) or None
            d = parse_human_date(date_text) if date_text else None
            label = _text(art.find("p"))
            cat_label, _, sub_label = label.partition(":")
            items.append(ListingItem(
                url=absolutise(href), title=_text(art.find("h3")) or link.get_text(strip=True),
                listing_date=d.isoformat() if d else None, listing_date_text=date_text,
                category=category or cat_label.strip() or None, section=section or sub_label.strip() or None,
                subcategory=item_el.get("data-subcategory") if item_el else None, found_on=found_on,
                series=sub_label.strip() or (section if section else None)))
            count += 1
        if section:
            sections.append((section, count))
    # Bare PDF links outside cards (featured links on the index page).
    seen = {i.url for i in items}
    for a in soup.find_all("a", href=True):
        if ".pdf" in a["href"].lower():
            url = absolutise(a["href"])
            if url not in seen:
                seen.add(url)
                items.append(ListingItem(url=url, title=_text(a) or url.rsplit("/", 1)[-1], listing_date=None,
                                         listing_date_text=None, category=category, section=None,
                                         subcategory=None, found_on=found_on))
    return items, sections


def months_in_window(start: date, end: date) -> list[tuple[int, int]]:
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + (m == 12), m % 12 + 1)
    return out


def discover(fetcher: Fetcher, start: date, end: date, log=print) -> tuple[list[ListingItem], list[SectionCheck]]:
    checks: list[SectionCheck] = []
    by_url: dict[str, ListingItem] = {}

    def merge(items: list[ListingItem]):
        for it in items:
            existing = by_url.get(it.url)
            if existing is None:
                it.sources = [it.found_on]
                by_url[it.url] = it
            else:
                existing.sources.append(it.found_on)
                # Prefer the dated, categorised listing entry.
                if not existing.listing_date and it.listing_date:
                    existing.listing_date, existing.listing_date_text = it.listing_date, it.listing_date_text
                for attr in ("category", "section", "subcategory", "series"):
                    if not getattr(existing, attr) and getattr(it, attr):
                        setattr(existing, attr, getattr(it, attr))

    def fetch_page(url: str, label: str, category: str | None = None) -> str | None:
        try:
            r = fetcher.get(url)
        except Exception as exc:  # noqa: BLE001 - recorded, never fatal
            checks.append(SectionCheck(label, category, None, "failed", 0, f"{type(exc).__name__}: {exc}"))
            log(f"  ! {label}: {exc}")
            return None
        if r.status != 200:
            checks.append(SectionCheck(label, category, None, "failed", 0, f"HTTP {r.status}"))
            return None
        return r.content.decode("utf-8", "replace")

    # 1. Index page
    html = fetch_page(INDEX_URL, "Research index (Recent Updates)")
    component = DEFAULT_COMPONENT
    if html:
        items, _ = parse_cards(html, "index")
        merge(items)
        checks.append(SectionCheck("Research index (Recent Updates)", None, None, "ok" if items else "empty", len(items)))

    # 2 + 3. Category pages and their monthly AJAX listings
    for cat, label in CATEGORIES.items():
        page_url = CATEGORY_URL.format(cat=cat)
        html = fetch_page(page_url, f"{label} page", label)
        if html:
            m = re.search(r'id="?componentURI"?\s+value="?([^"\s>]+\.ajax)', html)
            if m:
                component = m.group(1)
            checks.append(SectionCheck(f"{label} page", label, None, "ok", 0, "static page; listings load via AJAX"))
        for (y, mo) in months_in_window(start, end):
            src = f"{label} listing {MONTH_NAMES[mo - 1].title()} {y}"
            try:
                r = fetcher.post(absolutise(component), data={
                    "monthParam": MONTH_NAMES[mo - 1], "yearParam": str(y), "category": cat, "componentURI": component},
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": page_url})
            except Exception as exc:  # noqa: BLE001
                checks.append(SectionCheck(src, label, None, "failed", 0, f"{type(exc).__name__}: {exc}"))
                continue
            body = r.content.decode("utf-8", "replace")
            if r.status != 200 or len(body) < 200:
                checks.append(SectionCheck(src, label, None, "failed", 0,
                                           f"HTTP {r.status}, {len(body)} bytes - listing not returned"))
                continue
            items, sections = parse_cards(body, src, label)
            merge(items)
            for sec, n in sections:
                checks.append(SectionCheck(src, label, sec, "ok" if n else "empty", n))
            if not sections:
                checks.append(SectionCheck(src, label, None, "ok" if items else "empty", len(items)))

    # 4. Equity investment reports page
    html = fetch_page(INVESTMENT_URL, "Investment reports (equity)", "Equity Research")
    if html:
        items, _ = parse_cards(html, "investment-reports", "Equity Research")
        merge(items)
        checks.append(SectionCheck("Investment reports (equity)", "Equity Research", None,
                                   "ok" if items else "empty", len(items)))
    return list(by_url.values()), checks


def as_dict(obj) -> dict:
    return asdict(obj)
