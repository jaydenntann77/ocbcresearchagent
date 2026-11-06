"""What a question is about, and whether the research found actually covers it.

Retrieval always returns the closest passages, even when nothing in the
corpus is about the subject ("bitcoin" returns USD commentary). The answer
must then say the subject is not covered instead of presenting related
material as if it answered the question."""
from __future__ import annotations

import re

from app.common.instruments import (COMMODITY_KEYS, COUNTRIES, CURRENCY_NAMES, display_name, instrument_aliases)

# Words that describe the request rather than name its subject.
GENERIC = set("""
a about after again against ahead all also an and any are as at be been before being below between both but by can
could did do does doing during each few for from further had has have having how i if in into is it its just latest
me more most my no nor not now of off on once only or other our out over own same she should so some such than that
the their them then there these they this those through to too under until up very was we were what when where which
while who whom why will with would you your yours give tell show explain summarise summarize summary describe list
compare comparing versus vs please house ocbc ocbc's research view views outlook forecast forecasts forecasting
expect expects expected expectation expectations think thinks say says said see sees call calls target targets
price prices level levels path trend direction move moves current next near term medium long short year years
quarter quarters month months week weeks end through rate rates interest yield yields policy risk risks main key
recent published publish note notes report reports latest update updates market markets economy economic outlooks
growth inflation gdp cpi bank banks central share shares stock stocks equity equities bond bonds credit fx currency
currencies pair pairs commodity commodities rationale reasons reason drivers driver impact effect effects
overview picture big singapore's us u.s. global asia asian region regional sector sectors over opinion stance
likely going happen happens happening chance probability scenario scenarios base case upside downside
rise rises rising fall falls falling climb drop increase decrease higher lower strong strength weak weakness
together support supports supporting identified identify given interact interaction fit fits relate related
affect affects mean means matter matters change changes changed stay remain keep get got make makes take
look looking ask asked want wants need needs use used way ways thing things much many well good bad best new
""".split())
# Ordinary inflected words ("rallying", "weakened", "sharply") are not subjects.
INFLECTED_RE = re.compile(r"^[a-z]+(?:ing|ed|ly)$")

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z&$'.-]*[A-Za-z]|[A-Za-z]")
HORIZON_RE = re.compile(r"^(?:[1-4]q\d{2}|20\d{2}|\d+[my]|h[12]|[12]h\d{2})$", re.I)


def _names_for(plan, question: str = "") -> list[dict]:
    """Subjects the planner recognised, with the wording research uses for them.
    Instruments count only when the question names them: "SGD interest rates"
    is about SGD rates, not each benchmark the planner expands it to."""
    out = []
    low = question.lower()
    for k in getattr(plan, "instruments", []):
        names = instrument_aliases(k) + [display_name(k)]
        if question and not any(re.search(rf"(?<![a-z]){re.escape(n.lower())}(?![a-z])", low) for n in names):
            continue
        out.append({"known": True, "name": display_name(k), "aliases": list(dict.fromkeys(instrument_aliases(k) + [display_name(k)]))})
    named = {c for k in getattr(plan, "instruments", []) if len(k) == 6 for c in (k[:3], k[3:])}
    for c in getattr(plan, "currencies", []):
        if c in named:
            continue
        words = [n for n, code in CURRENCY_NAMES.items() if code == c]
        out.append({"known": True, "name": c, "aliases": [c] + words})
    for c in getattr(plan, "countries", []):
        words = [n.strip() for n, code in COUNTRIES.items() if code == c]
        out.append({"known": True, "name": words[0].title() if words else c, "aliases": words + [c]})
    for i in getattr(plan, "issuers", []):
        out.append({"known": True, "name": i, "aliases": [i]})
    return out


def find_subjects(question: str, plan, search_terms: list[str] | None = None) -> list[dict]:
    """[{name, aliases}] for each thing the question is about. Recognised
    entities use their research wording; any other specific word or phrase
    ("bitcoin", "DBS", "Brazilian real") is kept as written, plus the
    model's search terms when available, so a paraphrase still counts."""
    # Entities from the user's own words only: a replan with the model's search
    # terms ("BTC/USD") must not make a bitcoin question look like a USD one.
    from app.orchestrator.planner import plan_request
    own = plan_request(question, None, ("2000-01-01", "2100-12-31")) if getattr(plan, "question", question) else plan
    known = _names_for(own, question)
    covered_words = {w.lower() for s in known for a in s["aliases"] for w in TOKEN_RE.findall(a)}
    covered_words |= {w.lower() for w in COMMODITY_KEYS}
    terms = [t for t in (search_terms or []) if any(w.lower() not in GENERIC for w in TOKEN_RE.findall(t))]
    phrases, cur = [], []
    for tok in TOKEN_RE.findall(question):
        low = tok.lower().strip("'.")
        low = re.sub(r"'s$", "", low)
        if (low in GENERIC or low in covered_words or HORIZON_RE.match(low) or len(low) < 2
                or (tok.islower() and INFLECTED_RE.match(tok))):
            if cur:
                phrases.append(" ".join(cur))
                cur = []
            continue
        cur.append(re.sub(r"'s$", "", tok))
    if cur:
        phrases.append(" ".join(cur))
    unknown = [{"name": p, "aliases": [p] + terms} for p in dict.fromkeys(phrases)]
    return known + unknown


def is_covered(subject: dict, texts: list[str]) -> bool:
    blob = "\n".join(texts)
    for a in subject["aliases"]:
        # short codes (BRL, DBS) match case-sensitively; words match in any case, with a plural
        if re.fullmatch(r"[A-Z0-9$/&-]{2,8}", a):
            if re.search(rf"(?<![A-Za-z]){re.escape(a)}(?![A-Za-z])", blob):
                return True
        elif re.search(rf"(?<![A-Za-z]){re.escape(a)}(?:s|es)?(?![A-Za-z])", blob, re.I):
            return True
    return False


def is_specific(subject: dict) -> bool:
    """A name rather than an ordinary word: a recognised entity, or written
    with a capital or as a code ("Bitcoin", "DBS", "BoJ")."""
    return subject.get("known", False) or bool(re.search(r"[A-Z]", subject["name"]))


def join_names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]
