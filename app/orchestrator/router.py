"""Research mode or agent mode? Deterministic, so it is testable and costs nothing.

* research - the question asks for OCBC research (outlook, forecast, view, a named market). Answered by
  the research pipeline: OCBC research only, verbatim and cited, no ideas of the assistant's own.
* agent    - the salesperson is using the assistant as an assistant: meeting prep, a client's trades,
  positions or maturities, hedging / structuring ideas, explanations, follow-ups to an agent answer.
  Answered by the tool-using agent, with every section labelled by where it came from.
* auto     - neither is clear: try research first; if research cannot place the question, the agent
  answers it (when the model is available).

The UI has no mode switch: every question goes through choose(). The chat API still accepts
"mode": "research" | "agent" to pin a path (the tests use it).
"""
from __future__ import annotations

import re

from app.common.instruments import CURRENCIES, find_pairs

# Strong signs the salesperson wants the assistant, not a research note.
AGENT_RE = re.compile(r"""\b(
    brief(?:ing|\s+me)?|meeting|meet(?:ing)?\s+with|prep(?:are|aring|\s+for)?|catch[\s-]?up|call\s+with|
    talking\s+points?|pitch(?:ing)?|agenda|
    trades?|traded|trading\s+(?:activity|history)|deals?|positions?|exposures?|
    matur(?:e|es|ing|ity|ities)|expir(?:e|es|ing|y|ies)|roll(?:s|ed|ing|over|\s+over)?|due\s+(?:soon|this|next)|
    hedg(?:e|es|ed|ing)\s+(?:idea|ideas|suggestion|strateg\w*|option\w*)|hedging\s+ideas?|collars?|
    structur(?:e|es|ed|ing)|participating\s+forward|zero[\s-]cost|
    ideas?|suggest(?:ion|ions)?|recommend\s+(?:a|an|some)\s+(?:hedge|structure|product)|
    my\s+clients?|which\s+clients?|our\s+clients?|client\s+(?:list|book|overview|profile)|
    overview\s+of|profile\s+of|portfolio|
    what\s+is\s+an?|what's\s+an?|what\s+are\s+(?:collars?|forwards|options|swaps|ndfs?)|how\s+does\s+an?|
    explain\s+(?:how|what|the\s+difference)|difference\s+between|
    draft|e-?mail|message\s+to|follow[\s-]up\s+note
)\b""", re.I | re.X)

# Signs the question is about OCBC's research itself.
RESEARCH_RE = re.compile(r"""\b(
    outlook|forecasts?|views?|house\s+view|research|report|monitor|published|projections?|
    what\s+does\s+ocbc|ocbc(?:'s)?\s+(?:view|forecast|research|take|outlook)|
    risks?\s+(?:to|in|for|identified)|drivers?
)\b""", re.I | re.X)

MARKET_RE = re.compile(r"""\b(
    sora|sofr|sonia|estr|tona|fed(?:\s+funds)?|fomc|ust|treasur(?:y|ies)|yields?|bonds?|credit\s+spreads?|
    equit(?:y|ies)|stocks?|gdp|inflation|cpi|pce|payrolls|mas|s\$neer|boj|ecb|boe|rba|pboc|
    gold|oil|brent|rates?\s+outlook|interest\s+rates?
)\b""", re.I | re.X)


def names_market(question: str) -> bool:
    q = question or ""
    if find_pairs(q) or MARKET_RE.search(q):
        return True
    return any(re.search(rf"\b{c}\b", q) for c in CURRENCIES if c not in ("ALL",))


def choose(question: str, *, client_matched: bool = False, last_mode: str | None = None,
           forced: str | None = None) -> str:
    """'research', 'agent' or 'auto' (research first, agent if research cannot place the question)."""
    if forced in ("research", "agent"):
        return forced
    q = question or ""
    if AGENT_RE.search(q):
        return "agent"
    if RESEARCH_RE.search(q):
        return "research"
    if last_mode == "agent":
        # A follow-up to an agent answer ("what about USD/JPY?") stays with the agent, which can still
        # ask OCBC research itself when that is what the follow-up needs.
        return "agent"
    if names_market(q):
        return "research"
    if client_matched:
        return "agent"
    return "auto"
