"""Instrument / entity normalisation shared by ingestion (forecast-table keys),
specialists (exact matching) and the orchestrator planner (request parsing).
Contains vocabulary only - no market data."""
from __future__ import annotations

import re

CURRENCIES = {
    "USD", "SGD", "EUR", "JPY", "GBP", "AUD", "NZD", "CAD", "CHF", "CNY", "CNH", "HKD", "KRW", "TWD",
    "THB", "IDR", "MYR", "PHP", "INR", "VND", "NOK", "SEK", "MXN", "BRL", "ZAR", "XAU", "XAG",
}
CURRENCY_NAMES = {
    "singapore dollar": "SGD", "sing dollar": "SGD", "us dollar": "USD", "dollar": "USD", "yen": "JPY",
    "euro": "EUR", "sterling": "GBP", "pound": "GBP", "yuan": "CNY", "renminbi": "CNY", "rmb": "CNY",
    "ringgit": "MYR", "rupiah": "IDR", "baht": "THB", "won": "KRW", "rupee": "INR", "aussie": "AUD",
    "kiwi": "NZD", "loonie": "CAD", "swiss franc": "CHF", "peso": "PHP", "dong": "VND",
}

_PAIR_RE = re.compile(r"\b([A-Z]{3})\s?[-/]?\s?([A-Z]{3})\b")

COMMODITY_KEYS = {
    "gold": "GOLD", "silver": "SILVER", "platinum": "PLATINUM", "palladium": "PALLADIUM",
    "brent": "BRENT", "wti": "WTI", "copper": "COPPER", "aluminium": "ALUMINIUM", "aluminum": "ALUMINIUM",
}

# Overnight / benchmark rates: key -> (pattern, display name, wording used in research text).
BENCHMARK_RATES = {
    "SORA": (r"\bsora\b|singapore overnight rate average", "SORA", ["SORA", "Singapore Overnight Rate Average"]),
    "TONA": (r"\btonar?\b|tokyo overnight average", "TONA", ["TONA", "TONAR", "Tokyo Overnight Average"]),
    "SONIA": (r"\bsonia\b|sterling overnight index average", "SONIA", ["SONIA", "Sterling Overnight Index Average"]),
    "ESTR": (r"€str|\be-?str\b|euro short-term rate", "€STR", ["€STR", "ESTR", "euro short-term rate"]),
    "CORRA": (r"\bcorra\b|canadian overnight repo rate average", "CORRA", ["CORRA"]),
    "HONIA": (r"\bhonia\b|hong kong overnight index average", "HONIA", ["HONIA"]),
    "SARON": (r"\bsaron\b|swiss average rate overnight", "SARON", ["SARON"]),
}


# "3M SGD OIS" is quoted by currency but references that currency's overnight rate.
OIS_CURRENCY = {"SGD": "SORA", "USD": "SOFR", "JPY": "TONA", "GBP": "SONIA", "EUR": "ESTR"}


def find_benchmarks(text: str) -> list[str]:
    """Benchmark overnight rates named in free text, in order of appearance."""
    hits = []
    for key, (rx, _, _) in BENCHMARK_RATES.items():
        m = re.search(rx, text, re.I)
        if m:
            hits.append((m.start(), key))
    return [k for _, k in sorted(hits)]


RATE_PATTERNS = [
    (re.compile(r"\bfed funds?\b|\bffr\b|federal funds", re.I), "FEDFUNDS"),
    (re.compile(r"\bsofr\b(?!\s*swap)", re.I), "SOFR"),
] + [(re.compile(rx, re.I), key) for key, (rx, _, _) in BENCHMARK_RATES.items()] + [
    (re.compile(r"\b(\d{1,2})[- ]?(?:y|yr|year)[- ]?(?:us )?(?:treasury|ust)\b|\bust\s?(\d{1,2})y\b", re.I), "UST{n}Y"),
    (re.compile(r"\b(\d{1,2})[- ]?(?:y|yr|year)[- ]?sgs\b|\bsgs\s?(\d{1,2})y\b", re.I), "SGS{n}Y"),
    (re.compile(r"\b(\d{1,2})[- ]?(?:y|yr|year)[- ]?(?:sofr )?(?:swap )?rate\b", re.I), "SOFRSWAP{n}Y"),
]


def normalise_pair(text: str) -> str | None:
    """'USD-SGD', 'USD/SGD', 'USDSGD', 'usd sgd' -> 'USDSGD' (direction preserved)."""
    t = text.strip().upper()
    m = _PAIR_RE.fullmatch(t) or _PAIR_RE.match(t)
    if m and m.group(1) in CURRENCIES and m.group(2) in CURRENCIES and m.group(1) != m.group(2):
        return m.group(1) + m.group(2)
    return None


def instrument_key(label: str) -> str:
    """Normalised key for a forecast-table row label."""
    raw = label.strip()
    pair = normalise_pair(raw)
    if pair:
        return pair
    low = raw.lower()
    if low.startswith("dxy"):
        return "DXY"
    for word, key in COMMODITY_KEYS.items():
        if re.search(rf"\b{word}\b", low):
            return key
    # Swap/OIS tenors of a benchmark rate are separate instruments from the
    # overnight rate itself ("3M TONAR OIS" vs "JPY TONAR").
    m = re.match(r"^\s*(\d{1,2}[MY])\s+(.+?)\s+OIS\b", raw, re.I)
    if m:
        base = OIS_CURRENCY.get(m.group(2).strip().upper()) or instrument_key(m.group(2))
        if base in BENCHMARK_RATES or base == "SOFR":
            return f"{base}OIS{m.group(1).upper()}"
    # A compounded average ("3M compounded SORA") is a different series from
    # the overnight rate, so it needs its own key.
    m = re.match(r"^\s*(\d{1,2}M)\s+compounded\s+(.+)$", raw, re.I)
    if m:
        return f"{instrument_key(m.group(2))}{m.group(1).upper()}COMP"
    for rx, key in RATE_PATTERNS:
        m = rx.search(raw)
        if m:
            n = next((g for g in m.groups() if g), "") if m.groups() else ""
            return key.replace("{n}", n)
    return re.sub(r"[^A-Z0-9]+", "", raw.upper())[:40]


def find_pairs(text: str) -> list[str]:
    """Explicit currency pairs mentioned in free text, direction preserved."""
    out: list[str] = []
    up = text.upper()
    for m in re.finditer(r"\b([A-Z]{3})\s?[-/]\s?([A-Z]{3})\b|\b([A-Z]{3})([A-Z]{3})\b", up):
        a, b = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if a in CURRENCIES and b in CURRENCIES and a != b and a + b not in out:
            out.append(a + b)
    return out


def find_currencies(text: str) -> list[str]:
    found = []
    for tok in re.findall(r"\b[A-Z]{3}\b", text.upper()):
        if tok in CURRENCIES and tok not in found:
            found.append(tok)
    low = text.lower()
    for name, code in CURRENCY_NAMES.items():
        if re.search(rf"\b{re.escape(name)}s?\b", low) and code not in found:
            found.append(code)
    return found


RATE_ALIASES = {"FEDFUNDS": ["fed funds", "federal funds", "FFR", "Fed", "FOMC"]}
_TENOR_KEY = re.compile(r"(UST|SGS|SOFRSWAP)(\d{1,2})Y")


def related_rate_keys(key: str, available: set[str]) -> list[str]:
    """For a benchmark rate, its OIS tenors present in the corpus (SOFR -> SOFROIS1Y, ...)."""
    if key in BENCHMARK_RATES or key == "SOFR":
        return sorted(k for k in available if k.startswith(f"{key}OIS"))
    return []


def display_name(key: str) -> str:
    """Readable name for an instrument key (ESTR -> €STR, USDSGD -> USD/SGD)."""
    m = re.fullmatch(r"([A-Z]+)OIS(\d{1,2}[MY])", key)
    if m and (m.group(1) in BENCHMARK_RATES or m.group(1) == "SOFR"):
        ccy = "SGD" if m.group(1) == "SORA" else None  # the research says "SGD OIS", not "SORA OIS"
        return f"{m.group(2)} {ccy or display_name(m.group(1))} OIS"
    m = re.fullmatch(r"([A-Z]+)(\d{1,2}M)COMP", key)
    if m:
        return f"{m.group(2)} compounded {display_name(m.group(1))}"
    if key in BENCHMARK_RATES:
        return BENCHMARK_RATES[key][1]
    if len(key) == 6 and key[:3] in CURRENCIES and key[3:] in CURRENCIES:
        return f"{key[:3]}/{key[3:]}"
    return {"FEDFUNDS": "Fed funds rate"}.get(key, key)


def instrument_aliases(key: str) -> list[str]:
    """Words that mark a sentence as being about an instrument key. Keys such as
    FEDFUNDS or UST10Y never appear in research text, so they need the wording
    the research actually uses."""
    if len(key) == 6 and key[:3] in CURRENCIES and key[3:] in CURRENCIES:
        a, b = key[:3], key[3:]
        return [f"{a}{b}", f"{a}-{b}", f"{a}/{b}", f"{a} {b}"]
    if key in RATE_ALIASES:
        return [key] + RATE_ALIASES[key]
    if key in BENCHMARK_RATES:
        return BENCHMARK_RATES[key][2]
    m = re.fullmatch(r"([A-Z]+)(?:OIS(\d{1,2}[MY])|(\d{1,2}M)COMP)", key)
    if m and m.group(1) in BENCHMARK_RATES | {"SOFR": None}:
        base = instrument_aliases(m.group(1)) if m.group(1) != "SOFR" else ["SOFR"]
        ois = ["SGD OIS"] if m.group(1) == "SORA" else []
        return [key, m.group(2) or m.group(3)] + (["OIS"] + ois if m.group(2) else ["compounded"]) + base
    m = _TENOR_KEY.fullmatch(key)
    if m:
        kind, n = m.groups()
        names = {"UST": ["UST", "Treasury", "Treasuries"], "SGS": ["SGS"], "SOFRSWAP": ["SOFR", "swap"]}[kind]
        return [key, f"{n}Y", f"{n}-year", f"{n} year"] + names
    words = [w for w, k in COMMODITY_KEYS.items() if k == key]
    return [key] + words


def search_tokens_for(text: str) -> str:
    """Extra tokens appended to the full-text index so that 'USD-SGD',
    'USD/SGD' and 'USDSGD' all match the same query token."""
    extra = set(find_pairs(text))
    for m in re.finditer(r"\b(\d{1,2})[- ]?(?:y|yr|year)\b", text, re.I):
        extra.add(f"{m.group(1)}Y")
    for m in re.finditer(r"\b([1-4])Q\s?(\d{2})\b", text):
        extra.add(f"{m.group(1)}Q{m.group(2)}")
    return " ".join(sorted(extra))


COUNTRIES = {
    "singapore": "SG", "malaysia": "MY", "indonesia": "ID", "thailand": "TH", "china": "CN", "hong kong": "HK",
    "taiwan": "TW", "korea": "KR", "japan": "JP", "india": "IN", "philippines": "PH", "vietnam": "VN",
    "united states": "US", "us ": "US", "u.s.": "US", "america": "US", "euro area": "EA", "eurozone": "EA",
    "europe": "EA", "united kingdom": "UK", "uk ": "UK", "britain": "UK", "australia": "AU", "macau": "MO",
}


def find_countries(text: str) -> list[str]:
    low = f" {text.lower()} "
    out = []
    for name, code in COUNTRIES.items():
        if name in low and code not in out:
            out.append(code)
    return out
