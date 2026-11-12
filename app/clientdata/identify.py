"""Work out which client (and which person at that client) a question refers to.

    "Jimmy from Company A asks for the USD/SGD forecast"
        -> Harbourline Logistics / Jimmy Tan, research question "the USD/SGD forecast"

Deterministic matching (no model call), so client names never leave this service:

* companies: counterpart name, label, aliases and the name without its legal suffix,
  matched on whole words; a distinctive first word ("Meridian") is a weak key so that a
  bare "Meridian" stays ambiguous between similarly named clients;
* people: full name, or a capitalised first name, of any contact;
* scoring: longer company phrase wins; a person who works at the matched company adds a
  bonus. ``match`` only when the best candidate is clearly ahead, else ``ambiguous``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

LEGAL_SUFFIXES = r"(pte\.?\s+ltd\.?|sdn\.?\s+bhd\.?|ltd\.?|limited|inc\.?|co\.?|group|holdings|trust|plc)"
_SUFFIX_RE = re.compile(rf"(\s+{LEGAL_SUFFIXES})+\s*$", re.I)
WEAK_FIRST_WORDS = {"mr", "mrs", "ms", "dr", "the", "company", "group", "global", "asia", "singapore"}
_STRIP_VERBS = re.compile(
    r"\b(?:is\s+asking|was\s+asking|asks|asked|ask|wants|wanted|would\s+like|needs|needed|requests|requested|"
    r"is\s+looking|was\s+looking|enquired|enquires|inquired|inquires)\b(?:\s+(?:for|about|on|to\s+know|to\s+see))?",
    re.I)
_CONNECTORS = re.compile(r"^\s*(?:[,:;()\-–]+|(?:from|at|of|in|with)\b)\s*", re.I)
_ROLES = re.compile(r"\b(?:group\s+)?(?:treasurer|cfo|ceo|coo|cio|finance\s+(?:director|manager|team)|"
                    r"treasury\s+(?:manager|analyst|team|associate)|head\s+of\s+\w+|portfolio\s+manager)\b", re.I)
_CLIENT_WORDS = re.compile(r"\b(?:my|our)\s+client\b|\bclient\b|\bcustomer\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s&]", " ", s.lower())).strip()


def _find(phrase: str, text_norm: str) -> re.Match | None:
    if not phrase:
        return None
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text_norm)


@dataclass
class Candidate:
    client_id: str
    client_name: str
    contact_id: str | None = None
    contact_name: str | None = None
    contact_title: str | None = None
    score: float = 0.0
    matched_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__ | {"score": round(self.score, 2)}


@dataclass
class Identification:
    status: str                          # match | ambiguous | none
    candidates: list[Candidate]
    research_question: str               # the question with the client mention removed
    mention: str = ""                    # the client words found in the original question

    def to_dict(self) -> dict:
        return {"status": self.status, "candidates": [c.to_dict() for c in self.candidates],
                "research_question": self.research_question, "mention": self.mention}


def company_keys(client: dict) -> list[tuple[str, float]]:
    """(normalised phrase, strength) pairs for one client."""
    name = client["counterpart_name"]
    keys = {_norm(name): 1.0, _norm(_SUFFIX_RE.sub("", name)): 1.0, _norm(client.get("counterpart_label") or ""): 1.0}
    for a in (client.get("aliases") or "").split(";"):
        if a.strip():
            keys[_norm(a)] = 1.0
    first = _norm(name).split(" ")[0]
    if first and first not in WEAK_FIRST_WORDS and len(first) > 3:
        keys.setdefault(first, 0.5)
    return [(k, s) for k, s in keys.items() if k]


def identify(question: str, clients: list[dict], contacts: list[dict]) -> Identification:
    text_norm = _norm(question)
    spans: list[tuple[int, int]] = []    # character spans in the ORIGINAL question to remove

    # ---- companies: best phrase per client
    company_hits: dict[str, tuple[float, str]] = {}
    for c in clients:
        best = None
        for phrase, strength in company_keys(c):
            if _find(phrase, text_norm):
                score = len(phrase.split()) * strength + (0.25 if strength == 1.0 else 0)
                if not best or score > best[0]:
                    best = (score, phrase)
        if best:
            company_hits[c["client_id"]] = best

    # ---- people: full name (any case) or capitalised first name
    person_hits: dict[str, tuple[float, str]] = {}
    for p in contacts:
        full = f"{p['first_name']} {p['last_name']}"
        if _find(_norm(full), text_norm):
            person_hits[p["contact_id"]] = (2.0, full)
        elif re.search(rf"(?<!\w){re.escape(p['first_name'])}(?!\w)", question):  # case-sensitive
            person_hits[p["contact_id"]] = (1.0, p["first_name"])

    by_id = {c["client_id"]: c for c in clients}
    cands: dict[tuple[str, str | None], Candidate] = {}

    def add(client_id, contact=None, score=0.0, why=()):
        key = (client_id, contact["contact_id"] if contact else None)
        cand = cands.get(key) or Candidate(client_id, by_id[client_id]["counterpart_name"])
        if contact:
            cand.contact_id = contact["contact_id"]
            cand.contact_name = f"{contact['first_name']} {contact['last_name']}"
            cand.contact_title = contact.get("title")
        cand.score = max(cand.score, score)
        cand.matched_on = sorted(set(cand.matched_on) | set(why))
        cands[key] = cand

    for p in contacts:
        if p["contact_id"] in person_hits:
            pscore, pword = person_hits[p["contact_id"]]
            if p["client_id"] in company_hits:
                cscore, cword = company_hits[p["client_id"]]
                add(p["client_id"], p, cscore + pscore + 1.0, [cword, pword])
            elif not company_hits:          # person named, no company named
                add(p["client_id"], p, pscore, [pword])
    for cid, (cscore, cword) in company_hits.items():
        if not any(k[0] == cid for k in cands):
            add(cid, None, cscore, [cword])

    ranked = sorted(cands.values(), key=lambda c: (-c.score, c.client_name, c.contact_name or ""))
    if not ranked:
        return Identification("none", [], question.strip())
    top = ranked[0]
    clear = len(ranked) == 1 or top.score - ranked[1].score >= 1.0
    status = "match" if clear else "ambiguous"
    shown = [top] if clear else [c for c in ranked if top.score - c.score < 1.0][:5]

    # ---- strip every matched mention from the research question
    words = {w for c in ranked for w in c.matched_on}
    for w in sorted(words, key=len, reverse=True):
        pattern = r"[\W_]+".join(re.escape(t) for t in w.split())
        for m in re.finditer(rf"(?<!\w){pattern}(?:'s)?(?!\w)", question, re.I):
            spans.append(m.span())
    mention = " / ".join(sorted(words, key=lambda w: question.lower().find(w.split()[0].lower())))
    return Identification(status, shown, strip_mentions(question, spans), mention)


_LETTER_RE = re.compile(r"^\s*(?:option\s+)?\(?([a-z])\)?[.)]?\s*$", re.I)
_PICK_FILLER = {"it", "its", "it's", "is", "the", "option", "for", "client", "company", "pick", "choose", "i",
                "mean", "meant", "that", "one", "please", "pls", "with", "at", "from", "of", "use", "go", "s",
                "pte", "ltd", "sdn", "bhd", "holdings", "group", "co", "inc", "limited", "trust", "plc"}


def resolve_pick(text: str, candidates: list[dict], clients: list[dict], contacts: list[dict]) -> dict | None:
    """The user's choice after "which client?": a letter ("b", "b)", "option b") picks that
    listed match; a company (or person) name picks the one client it names - preferring a
    listed match, so "Meridian" picks Meridian Foods when only that Meridian was listed.
    Anything that reads like a new question (more than one other word) is not a pick."""
    m = _LETTER_RE.match(text or "")
    if m:
        i = ord(m.group(1).lower()) - ord("a")
        return candidates[i] if 0 <= i < len(candidates) else None
    r = identify(text or "", clients, contacts)
    if r.status == "none":
        return None
    matched = {w for c in r.candidates for phrase in c.matched_on for w in _norm(phrase).split()}
    if len(set(_norm(text).split()) - matched - _PICK_FILLER) > 1:
        return None
    listed_ids = {c["client_id"] for c in candidates}
    hits = [c for c in r.candidates if c.client_id in listed_ids]
    ids = {c.client_id for c in hits}
    if len(ids) != 1:
        if r.status != "match":
            return None
        hits, ids = r.candidates, {r.candidates[0].client_id}
    cid = next(iter(ids))
    named = [c for c in hits if c.contact_id]
    listed = [c for c in candidates if c["client_id"] == cid]
    if named and len(named) == 1:      # a person was named too: that person
        return next((c for c in listed if c.get("contact_id") == named[0].contact_id), named[0].to_dict())
    if len(listed) == 1:               # the one listed match at that company keeps its contact
        return listed[0]
    return Candidate(cid, next(c["counterpart_name"] for c in clients if c["client_id"] == cid)).to_dict()


def strip_mentions(question: str, spans: list[tuple[int, int]]) -> str:
    merged: list[list[int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, last = [], 0
    for s, e in merged:
        out.append(question[last:s])
        last = e
    out.append(question[last:])
    q = " ".join(out)
    q = _STRIP_VERBS.sub(" ", q, count=1)
    q = _CLIENT_WORDS.sub(" ", q)
    if spans:
        q = _ROLES.sub(" ", q, count=1)
        q = re.sub(r"\(\s*\)", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    for _ in range(3):
        q = _CONNECTORS.sub("", q).strip()
    q = re.sub(r"^(?:and|to|for|about|on)\s+", "", q, flags=re.I).strip(" ,")
    q = re.sub(r"\s+([?.!,])", r"\1", q)
    return q[:1].upper() + q[1:] if q else question.strip()
