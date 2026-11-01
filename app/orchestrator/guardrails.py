"""Request-level policy checks applied before any research is planned."""
from __future__ import annotations

import re

WEB_RE = re.compile(
    r"\b(search (the )?(web|internet|online)|google|bing|browse|look (it )?up online|latest news|news (today|online)|"
    r"check (the )?(web|internet|online)|on the internet|website|bloomberg|reuters)\b|https?://", re.I)
ADVICE_RE = re.compile(
    r"\b(should (i|we|my client|the client|they) (buy|sell|invest|hold|go long|go short|put)|"
    r"(give|suggest|recommend|come up with|propose) (me |us )?(an? |some )?(original |new |your own )?"
    r"(trade|trading|investment) (idea|recommendation|strategy)s?|your (own )?(view|opinion|recommendation|pick)|"
    r"what (should|would) you (buy|recommend|invest)|best (stock|trade|investment) to|"
    r"which (stock|bond|currency) should|invest(ment)? idea|trade idea|recommend a (trade|position|stock|bond))\b", re.I)
SMALLTALK_RE = re.compile(r"^\s*(hi|hello|hey|thanks|thank you|good (morning|afternoon|evening))\b[\s!.]*$", re.I)

WEB_NOTICE = ("Web search and browsing are not available. This assistant answers only from OCBC research PDFs "
              "ingested into its knowledge base; it cannot look up news, websites or market data.")
ADVICE_NOTICE = ("This assistant consolidates OCBC's published research. It does not generate original investment "
                 "ideas, trade recommendations or personal opinions. Below is what the ingested OCBC research itself "
                 "says, with citations.")


def check(question: str) -> dict:
    return {
        "web": bool(WEB_RE.search(question)),
        "advice": bool(ADVICE_RE.search(question)),
        "smalltalk": bool(SMALLTALK_RE.match(question)),
    }


def strip_web_request(question: str) -> str:
    """Remove the web-search instruction so the research part can still be answered from the corpus."""
    q = re.sub(r"https?://\S+", "", question)
    q = re.sub(r"\b(please )?(search|check|browse|look up)( on)? (the )?(web|internet|online|google)( for| and)?\b", "", q, flags=re.I)
    q = re.sub(r"\b(use|using|on|via) (google|bing|the internet|the web)\b", "", q, flags=re.I)
    return re.sub(r"\s+", " ", q).strip(" ,.;")
