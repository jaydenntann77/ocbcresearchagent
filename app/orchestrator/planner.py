"""Request understanding and specialist task planning (deterministic).

Selects only the specialists a request needs; never fans out to all five by
default. Follow-up questions inherit entities from the previous turn."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from app.common.instruments import COMMODITY_KEYS, find_benchmarks, find_countries, find_currencies, find_pairs
from app.common.schemas import CorpusConstraints, SpecialistTask

WORDS = {
    "fx": r"\b(fx|currenc\w*|exchange rate|forex|dollar|neer|s\$neer|appreciat\w*|depreciat\w*|pairs?)\b",
    "rates": r"\b(interest rates?|rates? outlook|policy rates?|yields?|ust|treasur\w*|sgs|sora|sofr|tonar?|sonia|e-?str|"
             r"corra|honia|saron|fed\b|fomc|fed funds|ecb|boj|boe|"
             r"curve|swaps?|rate (hikes?|cuts?)|hikes?|cuts?|bond yields?|duration|central bank)\b",
    "macro": r"\b(gdp|inflation|growth|econom\w*|macro|recession|fiscal|budget|cpi|pce|pmi|exports?|trade|labou?r|"
             r"unemployment|commodit\w*|oil|brent|policy|esg|sustainab\w*|climate|carbon|"
             r"outlook for (singapore|china|us|asia))\b",
    "equities": r"\b(equit\w*|stocks?|shares?|sti\b|s&p|nasdaq|nikkei|hang seng|earnings|reits?|sector|target price|dividends?)\b",
    "credit": r"\b(credit|issuers?|spreads?|high yield|investment grade|ratings?|perps?|perpetual|default|bonds? issu\w*|"
              r"corporate bonds?|asiadollar|sgd bonds?|new issues?)\b",
}
INFO = {
    "forecast": r"\b(forecasts?|projections?|targets?|expect\w*|through \d{4}|path|end[- ]?\d{4}|levels?|year[- ]end|"
                r"\d[qQ]\d{2}|outlook|where will)\b",
    "rationale": r"\b(rationale|why|drivers?|reasons?|explain\w*|views?|colou?r|commentary|say|says|summar\w*|thinking|"
                 r"supporting|context|outlook)\b",
    "risks": r"\b(risks?|downside|upside|uncertaint\w*|threats?|concerns?|vulnerab\w*)\b",
    "scenarios": r"\b(scenarios?|alternative|bull case|bear case|base case)\b",
}
# "Give me an overview of OCBC's views": a request across desks, not a follow-up
# on the previous instrument. Macro leads, with FX and Rates.
BROAD_RE = re.compile(r"\b(overview|big picture|round-?up|market wrap|key (themes|views|calls)|main (themes|views)|"
                      r"house views|research views|across (desks|markets|asset classes)|what is ocbc saying|"
                      r"what'?s ocbc saying|summar(y|ise|ize) of (ocbc|the research|research))\b", re.I)
BROAD_DESKS = ["macro", "fx", "rates"]

# Precious metals are Rates & FX coverage (FX Weekly forecasts them); Macro
# covers energy and industrial commodities.
PRECIOUS = ("GOLD", "SILVER", "PLATINUM", "PALLADIUM")
PRECIOUS_RE = re.compile(r"\bprecious metals?\b|\bbullion\b", re.I)

# MAS steers the Singapore dollar through the S$NEER policy band, not an interest
# rate, so MAS questions are FX questions about SGD.
MAS_RE = re.compile(r"\bmas\b|monetary authority of singapore|singapore'?s? central bank|s\$neer|sgd neer|policy band",
                    re.I)
FOLLOW_UP = re.compile(r"^(and|what about|how about|also|ok|okay|then|same|that|those|it|for)\b|\b(that|those|it|same)\b", re.I)


@dataclass
class Plan:
    question: str
    specialists: list[str]
    lead: str | None
    instruments: list[str]
    currencies: list[str]
    countries: list[str]
    issuers: list[str]
    sectors: list[str]
    horizon: str | None
    horizon_years: list[int]
    info_types: list[str]
    inherited: bool = False
    notes: list[str] = field(default_factory=list)

    def to_state(self) -> dict:
        return self.__dict__.copy()


def _rate_keys(q: str, currencies: list[str], countries: list[str]) -> list[str]:
    low = q.lower()
    keys = []
    if re.search(r"fed funds|fed\b|fomc", low):
        keys.append("FEDFUNDS")
    if "sofr" in low and "swap" not in low:
        keys.append("SOFR")
    for m in re.finditer(r"\b(\d{1,2})[- ]?(?:y|yr|year)[- ]?(ust|treasur\w*|sgs|swap|sofr swap)", low):
        n, kind = m.group(1), m.group(2)
        keys.append(f"UST{n}Y" if kind.startswith(("ust", "treasur")) else f"SGS{n}Y" if kind == "sgs" else f"SOFRSWAP{n}Y")
    for m in re.finditer(r"\b(ust|sgs)\s?(\d{1,2})y\b", low):
        keys.append(f"{m.group(1).upper()}{m.group(2)}Y")
    keys += find_benchmarks(q)  # SORA, TONA, SONIA, €STR, ...
    generic = re.search(r"interest rates?|rates? outlook|yields?|treasur", low)
    if generic and not keys:
        if "USD" in currencies or "US" in countries or re.search(r"\bus\b|u\.s\.|treasur", low):
            keys += ["FEDFUNDS", "SOFR", "UST2Y", "UST10Y"]
        if "SGD" in currencies or "SG" in countries:
            keys += ["SORA", "SGS2Y", "SGS10Y"]
    return list(dict.fromkeys(keys))


def plan_request(question: str, previous: dict | None, window: tuple[str, str], expanded: bool = False) -> Plan:
    q = question.strip()
    low = q.lower()
    pairs = find_pairs(q)
    currencies = find_currencies(q)
    countries = find_countries(q)
    years = sorted({int(y) for y in re.findall(r"\b(20[2-4]\d)\b", q)})
    commodity = [v for k, v in COMMODITY_KEYS.items() if re.search(rf"\b{k}\b", low)]
    if PRECIOUS_RE.search(q):
        commodity = list(dict.fromkeys(commodity + list(PRECIOUS)))
    issuers = re.findall(r"\b([A-Z][A-Za-z&]+(?: [A-Z][A-Za-z&]+){0,3}) \((?:[A-Z0-9 ]{2,10})\)", q)

    scores = {s: len(re.findall(rx, low)) for s, rx in WORDS.items()}
    if pairs:
        scores["fx"] += 3
    elif currencies and not re.search(r"\b(interest )?rates?\b|\byields?\b|\bbonds?\b|\bcredit\b", low):
        scores["fx"] += 1  # a currency named on its own ("JPY and the BoJ") is an FX question too
    if commodity:
        if any(c in PRECIOUS for c in commodity):
            scores["fx"] += 3
        if any(c not in PRECIOUS for c in commodity):
            scores["macro"] += 1
    if MAS_RE.search(q):
        if "SGD" not in currencies:
            currencies = currencies + ["SGD"]
        # "central bank" and "policy" describe MAS here, not a rates or macro request.
        scores["rates"] -= len(re.findall(r"\bcentral bank\b", low))
        scores["macro"] -= len(re.findall(r"\bpolicy\b", low))
        scores["fx"] += 3
    rate_keys = _rate_keys(q, currencies, countries) if scores["rates"] > 0 else []
    if rate_keys and re.search(r"fed funds|fed|fomc|sofr|sora|ust|treasur|sgs|\d+[- ]?y", low):
        scores["rates"] += 2  # an explicitly named rate instrument is a rates request in its own right

    info = [k for k, rx in INFO.items() if re.search(rx, low)]
    horizon = None
    m = re.search(r"\b((?:through|until|till|to|by|out to|for|in|end[- ]?of|end[- ]?)\s*(?:end[- ]?)?(20\d{2}|\d[qQ]\d{2}))", q)
    if m:
        horizon = m.group(1)
    elif years:
        horizon = ", ".join(map(str, years))

    has_entities = bool(pairs or currencies or countries or commodity or issuers or rate_keys)
    inherited = False
    broad = bool(BROAD_RE.search(q)) and not has_entities
    if previous and not broad and (not has_entities and not any(scores.values())
                                   or FOLLOW_UP.search(low) and not has_entities):
        inherited = True
        pairs = pairs or previous.get("instruments", [])
        currencies = currencies or previous.get("currencies", [])
        countries = countries or previous.get("countries", [])
        issuers = issuers or previous.get("issuers", [])
        for s in previous.get("specialists", []):
            scores[s] = max(scores.get(s, 0), 1)
        if not years and previous.get("horizon_years"):
            years, horizon = previous["horizon_years"], previous.get("horizon")
        if not info:
            info = previous.get("info_types", [])

    if not info:
        info = ["forecast", "rationale"] if (pairs or rate_keys or commodity) else ["rationale", "risks"]
    if "forecast" in info and "rationale" not in info and re.search(r"\b(why|rationale|support)", low):
        info.append("rationale")

    selected = [s for s, sc in sorted(scores.items(), key=lambda kv: -kv[1]) if sc > 0]
    if broad:
        # An overview of a named desk stays with that desk; otherwise the main three.
        selected = selected or BROAD_DESKS
        if not re.search(r"\b(forecasts?|projections?)\b", low):
            info = ["rationale", "risks"]
    if not selected and (currencies or countries):
        selected = ["macro"]
    lead = selected[0] if selected else None
    if (pairs or any(c in PRECIOUS for c in commodity)) and "fx" in selected:
        lead = "fx"
        # A straightforward FX request goes to FX alone; others join only when
        # the question itself asks about their domain.
        need = 2 if pairs else 1  # a metals question naming oil or inflation also needs Macro
        selected = ["fx"] + [s for s in selected if s != "fx" and scores[s] >= need]
    instruments = list(dict.fromkeys(pairs + rate_keys + commodity))
    return Plan(question=q, specialists=selected[:3], lead=lead, instruments=instruments, currencies=currencies,
                countries=countries, issuers=issuers, sectors=[], horizon=horizon, horizon_years=years,
                info_types=list(dict.fromkeys(info)), inherited=inherited)


def objective_for(spec: str, plan: Plan) -> str:
    what = ", ".join(plan.instruments or plan.currencies or plan.countries or plan.issuers) or {
        "credit": "credit markets and issuers", "equities": "equity markets", "macro": "the economic outlook",
        "rates": "interest rates", "fx": "currencies"}[spec]
    parts = []
    if "forecast" in plan.info_types:
        parts.append(f"extract OCBC's published forecasts for {what}" + (f" ({plan.horizon})" if plan.horizon else "")
                     + " exactly as printed, with horizon labels, units, footnotes and stated forecast dates")
    if "rationale" in plan.info_types:
        parts.append(f"find OCBC's published rationale and market commentary on {what}")
    if "risks" in plan.info_types:
        parts.append(f"find risks and alternative outcomes OCBC identifies for {what}")
    if "scenarios" in plan.info_types:
        parts.append("find any published scenario analysis")
    return f"[{spec.upper()}] " + "; ".join(parts or [f"find OCBC research relevant to {what}"])


def build_tasks(plan: Plan, window: tuple[str, str], expanded: bool, specialists: list[str] | None = None,
                known_gaps: list[str] | None = None, follow_up_of: str | None = None,
                search_terms: list[str] | None = None) -> list[SpecialistTask]:
    tasks = []
    for spec in specialists or plan.specialists:
        instruments = plan.instruments
        if spec == "fx":
            instruments = [i for i in instruments if len(i) == 6 and i.isalpha() or i in ("DXY", "GOLD", "SILVER",
                                                                                          "PLATINUM", "PALLADIUM")]
        elif spec == "rates":
            instruments = [i for i in instruments if not (len(i) == 6 and i.isalpha()) and i not in COMMODITY_KEYS.values()]
        elif spec == "macro":
            instruments = [i for i in instruments if i in COMMODITY_KEYS.values()]
        else:
            instruments = []
        tasks.append(SpecialistTask(
            task_id=f"T-{uuid.uuid4().hex[:8]}", specialist=spec, original_question=plan.question,
            objective=objective_for(spec, plan), instruments=instruments, currencies=plan.currencies,
            countries=plan.countries, sectors=plan.sectors, issuers=plan.issuers, horizon=plan.horizon,
            horizon_years=plan.horizon_years,
            info_types=[i for i in plan.info_types if i != "forecast" or instruments] or ["rationale"],
            corpus=CorpusConstraints(window_start=window[0], window_end=window[1], expanded_range=expanded),
            known_gaps=known_gaps or [], follow_up_of=follow_up_of, search_terms=search_terms or []))
    return tasks
