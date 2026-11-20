"""Conversation API + main orchestrator (port 8100). The only agent that
talks to the user.

Process policy (enforced by app.common.guard, installed before anything else):
  * no filesystem access to the corpus, raw PDFs, collections or models -
    only data/orchestrator (conversation history);
  * loopback connections only to the specialist (8101), validator (8102) and
    client-data (8105) services; internet only to the model API when a credential is configured;
  * retrieval / PDF / embedding modules cannot be imported;
  * no subprocesses.
"""
from __future__ import annotations

from app.common import config, guard

guard.install(guard.Policy(
    role="orchestrator",
    denied_roots=[config.DATA_DIR],
    allowed_roots=[config.ORCH_DIR],
    allowed_hosts={config.MODEL_API_HOST} if config.model_credentials_present() else set(),
    allowed_loopback_ports={config.PORTS["research"], config.PORTS["validator"], config.PORTS["clientdata"]},
    blocked_modules=("fitz", "pymupdf", "fastembed", "onnxruntime", "rapidocr_onnxruntime", "app.research",
                     "app.ingestion", "app.validator", "app.docs", "app.common.embedding", "app.clientdata"),
))

import json  # noqa: E402
import queue  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import threading  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import date, datetime  # noqa: E402

from fastapi import Body, Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

from app.common.instruments import CURRENCIES, find_pairs  # noqa: E402
from app.common.schemas import SPECIALIST_LABELS  # noqa: E402
from app.common.security import require_token  # noqa: E402
from app.common.timeutil import fmt_dt, fmt_range, now_sgt  # noqa: E402
from app.orchestrator import (agent, client_memory, composer, conversations, guardrails, llm,  # noqa: E402
                              model_switch, planner, router, trade_note)
from app.orchestrator.clients import ClientDataClient, ResearchClient, ServiceError, ValidatorClient  # noqa: E402

app = FastAPI(title="Conversation API", docs_url=None, redoc_url=None, openapi_url=None)
auth = require_token(config.TOKEN_GATEWAY_ORCH)
research = ResearchClient()
DEMO_CLIENT_IDS = ("T01", "T02", "T03", "T04")  # pattern clients, visible only in demo mode
validator = ValidatorClient()
clientdata = ClientDataClient()
SUGGESTIONS = [
    "What does the latest available research say about USD/SGD through 2027?",
    "Summarize OCBC's published view on SGD interest rates.",
    "What are the main risks identified in the latest credit research?",
    "What is OCBC's forecast for the Fed funds rate and 10-year UST yield?",
    "What is OCBC's latest view on JPY and the BoJ?",
]
AGENT_SUGGESTIONS = [
    "Brief me on Harbourline Logistics before my meeting",
    "Which clients have deals maturing in the next 2 weeks?",
    "What has Kestrel Semiconductor been trading recently?",
    "Any hedging ideas for Lumina Property Trust?",
    "What's a zero-cost collar and when would a USD earner use one?",
]
MODES = ("auto", "research", "agent")


def corpus_meta() -> dict:
    cov = research.coverage()
    w = cov.get("window") or {}
    if w.get("start") and w.get("end") and not w.get("label"):
        w["label"] = fmt_range(date.fromisoformat(w["start"]), date.fromisoformat(w["end"]))
    last = cov.get("last_successful_run") or {}
    refreshed = fmt_dt(datetime.fromisoformat(last["finished_at"])) if last.get("finished_at") else None
    pubs = sorted({d for s in cov.get("specialists", {}).values() for d in s.get("publication_dates", [])})
    return {"window": w, "refreshed_label": refreshed,
            "published_label": fmt_range(date.fromisoformat(pubs[0]), date.fromisoformat(pubs[-1])) if pubs else None,
            "specialists": {k: v["documents"] for k, v in cov.get("specialists", {}).items()}}


def _simple(question: str, status: str, message: str, notices=None, corpus=None) -> dict:
    return {"answer_id": None, "question": question, "generated_at": now_sgt().isoformat(),
            "generated_label": fmt_dt(now_sgt()), "status": status, "mode": "none", "notices": notices or [],
            "freshness": {"corpus_window": (corpus or {}).get("window", {}).get("label"),
                          "corpus_refreshed": (corpus or {}).get("refreshed_label"), "research_published": None,
                          "expanded": bool((corpus or {}).get("window", {}).get("expanded"))},
            "direct": [], "table": [], "table_notes": [], "rationale": [], "risks": [], "scenarios": [],
            "conflicts": [], "limitations": [], "sources": [], "specialists": [], "message": message,
            "suggestions": SUGGESTIONS[:3]}


def answer_question(question: str, state: dict, emit) -> tuple[dict, dict]:
    checks = guardrails.check(question)
    notices = []
    if checks["smalltalk"]:
        return _simple(question, "info", "Ask a research question about FX, rates, macro, equities or credit, and "
                                         "I'll consolidate what the ingested OCBC research says, with citations."), state
    q = question
    if checks["web"]:
        notices.append({"kind": "web", "text": guardrails.WEB_NOTICE})
        q = guardrails.strip_web_request(question)
    if checks["advice"]:
        notices.append({"kind": "advice", "text": guardrails.ADVICE_NOTICE})
    emit("Checking the latest research")
    try:
        corpus = corpus_meta()
    except ServiceError as exc:
        return _simple(question, "error", "The research isn't available right now. Please try again in a moment.",
                       notices), state
    w = corpus["window"]
    if not w.get("start"):
        return _simple(question, "error", "The research library is still being set up. Please try again later.",
                       notices, corpus), state
    emit("Understanding the question")
    terms = llm.search_terms(q)
    plan = planner.plan_request(q, state.get("last_plan"), (w["start"], w["end"]), bool(w.get("expanded")))
    if not plan.specialists and terms:
        # Plain-English questions ("what is the Singapore central bank doing?") name no
        # instrument; plan again with the research's own terms added.
        plan = planner.plan_request(f"{q} ({', '.join(terms)})", state.get("last_plan"), (w["start"], w["end"]),
                                    bool(w.get("expanded")))
        plan.question = q
    if not plan.specialists:
        msg = ("I couldn't identify an instrument, market or sector to research in that request. "
               "Try naming a currency pair, rate, country, issuer or sector.")
        if checks["web"] or checks["advice"]:
            msg = "No research question remained after removing the parts this assistant cannot do. " + msg
        return _simple(question, "clarify", msg, notices, corpus), state
    tasks = planner.build_tasks(plan, (w["start"], w["end"]), bool(w.get("expanded")), search_terms=terms)
    responses = []

    def run(task):
        emit(f"Reviewing {SPECIALIST_LABELS[task.specialist]} research")
        try:
            return research.run_task(task)
        except ServiceError as exc:
            from app.common.schemas import SpecialistResponse
            return SpecialistResponse(task_id=task.task_id, specialist=task.specialist, status="error",
                                      limitations=[f"Specialist service error: {exc}"])

    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(run, tasks))
    # Follow-up round: request more work when the evidence is incomplete.
    consulted = {r.specialist for r in responses}
    lead = next((r for r in responses if r.specialist == plan.lead), None)
    if lead and lead.specialist == "fx" and "rationale" in plan.info_types and "macro" not in consulted:
        rationale = [f for f in lead.findings if f.kind == "rationale"]
        if len(rationale) < 2 or lead.status in ("no_evidence", "error"):
            gaps = [f"FX research returned {len(rationale)} rationale passage(s) for {', '.join(plan.instruments)}"]
            extra = planner.build_tasks(plan, (w["start"], w["end"]), bool(w.get("expanded")), ["macro"],
                                        known_gaps=gaps, follow_up_of=lead.task_id, search_terms=terms)
            emit("Looking at macro research too")
            responses += [run(t) for t in extra]
    use_model = llm.status()["available"]
    if use_model and not conversations.take_model_call(config.MODEL_DAILY_CAP):
        use_model = False
        notices.append({"kind": "info", "text": "Today's limit for written summaries has been reached, so this answer "
                                                "quotes the OCBC reports directly. Summaries are back tomorrow."})
    emit("Checking every figure against the reports")
    try:
        answer = composer.compose(question, plan, responses, validator, notices, corpus, use_model=use_model)
    except ServiceError as exc:
        return _simple(question, "error", "The answer couldn't be checked against the reports just now, so it isn't "
                                          "shown. Please try again in a moment.", notices, corpus), state
    answer["plan"] = {"specialists": [SPECIALIST_LABELS[r.specialist] for r in responses], "lead":
                      SPECIALIST_LABELS.get(plan.lead or "", None), "instruments": plan.instruments,
                      "horizon": plan.horizon, "info_types": plan.info_types, "inherited_context": plan.inherited,
                      "search_terms": terms}
    entry = client_memory.propose(question, state.get("last_client"))
    new_state = {**state, "last_plan": plan.to_state()}
    if entry:
        answer["pending_memory"] = entry
        new_state["last_client"] = {"name": entry["name"], "company": entry["company"]}
    return answer, new_state

# "jeremy asked for usd/sgd", "Jeremy wants the SORA outlook": a person the salesperson named.
NAME_ASK_RE = re.compile(r"^\s*(?P<name>[A-Za-z][A-Za-z'-]{1,30})\s+(?:asked|asks|wants|wanted|is asking|was asking|"
                         r"needs|enquired|inquired|requested)\b\s*(?P<rest>.*)$", re.I | re.S)
NOT_NAMES = {"he", "she", "they", "client", "customer", "someone", "somebody", "who", "what", "my", "our", "the",
             "boss", "treasurer", "cfo", "ceo", "everyone", "nobody", "it", "i", "we", "you", "he's", "she's"}


def unknown_person(question: str) -> tuple[str, str] | None:
    """(name, rest of the question) when it opens with a person's name and what they asked."""
    m = NAME_ASK_RE.match(question or "")
    if not m or m["name"].lower() in NOT_NAMES:
        return None
    name = m["name"]
    return (name[:1].upper() + name[1:] if name.islower() else name), (m["rest"].strip() or question)


def memory_entry(client: dict, company: str) -> dict | None:
    """The client-memory card (insights + save) for a person whose company is not in the client book."""
    return client_memory.propose(f"{client['mention']} from {company} asked {client.get('ask_rest') or ''}", None)


def identify_client(question: str, state: dict, emit) -> dict | None:
    """Which client the question is about. Falls back to the client confirmed earlier
    in this conversation (marked inherited) when the question names nobody."""
    emit("Identifying the client")
    found = clientdata.identify(question)
    lead = NAME_ASK_RE.match(question or "")
    if (not found or found["status"] == "none") and lead and lead["name"].islower()             and lead["name"].lower() not in NOT_NAMES:
        # First names only count when capitalised ("grace period" is not Grace Lim), but one that opens
        # the question before "asked" / "wants" is a person: "jimmy asked ..." means Jimmy.
        i = lead.start("name")
        found = clientdata.identify(question[:i] + question[i].upper() + question[i + 1:]) or found
    last = state.get("client")
    if last and last.get("client_id") in DEMO_CLIENT_IDS and not clientdata.exists(last["client_id"]):
        last = None   # a demo-mode client is not carried over once demo mode is off
    # A name that matches several clients ("Jimmy") is never resolved by guessing, not even from the
    # client earlier in this conversation: routed_answer answers with research and asks which one.
    if found and found["status"] != "none":
        return found | {"inherited": False, "logged": None, "declined": False}
    if client_memory.CLIENT_RE.match(question):
        return None   # "Jeremy from Company A asked ...": a client outside the book, for the client-memory card
    person = unknown_person(question)
    if person:
        # "jeremy asked for usd/sgd" and no Jeremy in the book: never the earlier client; ask which company.
        name, rest = person
        return {"status": "ambiguous", "unknown": True, "candidates": [], "mention": name, "ask_rest": rest,
                "research_question": rest, "inherited": False, "logged": None, "declined": False}
    if last:
        return {"status": "match", "candidates": [last], "research_question": question, "mention": "",
                "inherited": True, "logged": None, "declined": False}
    return None


def fx_pairs(answer: dict, question: str) -> list[str]:
    """Currency pairs the research answered about (else any pair named in the question)."""
    inst = (answer.get("plan") or {}).get("instruments") or []
    pairs = [i for i in inst if len(i) == 6 and i[:3] in CURRENCIES and i[3:] in CURRENCIES]
    return pairs or find_pairs(question)


def attach_trade_context(client: dict, answer: dict, question: str, emit) -> None:
    """Internal client data for the client box only (never the research answer): how the
    confirmed client's own trades in the asked pair(s) relate to this ask."""
    pairs = fx_pairs(answer, question)
    if not pairs:
        return
    emit("Checking the client's trades")
    contexts = clientdata.trade_context(client["candidates"][0]["client_id"], pairs)
    if contexts:
        # Research link first (rule-based, never reworded), then optional Haiku wording line by line.
        client["trade_context"] = [trade_note.polish(c | {"research_link": trade_note.research_link(answer, c)})
                                   for c in contexts]


def agent_pairs(answer: dict, question: str, client_id: str) -> list[str]:
    """Pairs for an agent answer's client card: named in the question, else used by the agent's tools,
    else the client's most active open pairs."""
    pairs = find_pairs(question)
    if not pairs:
        pairs = list(dict.fromkeys(str(t["args"]["pair"]) for t in answer.get("trace") or []
                                   if t.get("ok") and (t.get("args") or {}).get("pair")))
    if not pairs:
        ov = clientdata.view("overview", client_id) or {}
        ranked = sorted((p for p in ov.get("pairs") or [] if p.get("open_deals")),
                        key=lambda p: -int(p.get("open_deals") or 0))
        pairs = [p["pair"] for p in ranked]
    return pairs[:3]


def attach_agent_trade_context(client: dict, answer: dict, question: str, emit) -> None:
    """The same client card research answers get: rule-based facts and ideas, the research link
    (from any forecast table the agent quoted) and the optional Haiku wording."""
    cid = client["candidates"][0]["client_id"]
    try:
        pairs = agent_pairs(answer, question, cid)
    except (ServiceError, KeyError, TypeError, ValueError):
        return
    if not pairs:
        return
    emit("Checking the client's trades")
    contexts = clientdata.trade_context(cid, pairs)
    if contexts:
        quoted = {"table": [r for s in answer.get("sections") or [] for r in s.get("research_tables") or []]}
        client["trade_context"] = [trade_note.polish(c | {"research_link": trade_note.research_link(quoted, c)})
                                   for c in contexts]


def attach_past_asks(client: dict) -> None:
    """Earlier logged asks from the confirmed contact, for the client box. Looked up before this
    question is logged, so they are the contact's previous asks."""
    c = client["candidates"][0]
    past = clientdata.past_asks(c["client_id"], c.get("contact_id"), limit=10)
    recent = (past or {}).get("items") or []
    # Client-memory insights (topics asked before, how often, how recently) for a client in the book too,
    # from the last 10 asks and the full count; the box lists the 3 most recent.
    who = c.get("contact_name") or c.get("client_name") or "this client"
    client["insights"] = client_memory.insights_for_asks(
        who, recent, client.get("research_question") or client.get("for_question") or "", (past or {}).get("count"))
    if past and past.get("count"):
        client["past_asks"] = past | {"items": recent[:3]}


def agent_answer(question: str, client: dict | None, state: dict, emit) -> tuple[dict | None, str | None]:
    """Agent mode: the tool-using agent, or - when no model can be used - a deterministic client-book
    snapshot. Returns (None, reason) when neither can answer, so the caller shows research instead."""
    status = llm.status()
    if not status["key_present"]:
        reason = "Agent mode needs the Claude API (no API key is configured)."
    elif not status["available"]:
        reason = "Agent mode needs the Claude API, which is OFF (type “turn on Claude API” to enable it)."
    elif not conversations.take_model_call(config.MODEL_DAILY_CAP):
        reason = "Today's limit for the assistant has been reached; it's back tomorrow."
    else:
        def research_fn(q: str) -> dict:
            # The agent's research tool is the full research pipeline: specialists, validator, citations.
            ans, _ = answer_question(q, {}, lambda t: emit(f"Research · {t}"))
            return ans
        names = {c["client_id"]: c.get("client_name") for c in (client or {}).get("candidates") or []
                 if c.get("client_id") and c.get("client_name")}
        try:
            ctx = agent.context_block(client, fmt_dt(now_sgt()))
            return agent.Agent(clientdata, research_fn, emit, names=names).run(
                question, ctx, state.get("turns") or []), None
        except agent.AgentUnavailable as exc:
            # The salesperson sees a plain message; the operator log keeps the cause.
            print(f"[orchestrator] assistant unavailable: {exc}", file=sys.stderr, flush=True)
            reason = "The assistant couldn't answer just now."
    snap = agent.snapshot(clientdata, client, question)
    if snap:
        snap["notices"].append({"kind": "info", "text": f"{reason} Here is a summary straight from the client book."})
        return snap, None
    return None, reason


def generic_answer(question: str, client: dict, prior: dict, emit) -> tuple[dict, dict]:
    """The name is not clearly one client (several match, or none does): no client is assumed. OCBC
    research (with its forecast) on what was asked comes first, with the name taken out; the client box
    under it asks which one - pick from the list, or type the company."""
    research_q = client.get("research_question") or question
    answer, state = answer_question(research_q, prior, emit)
    answer["question"] = question
    answer.pop("pending_memory", None)          # the client box asks for the company first
    mention = client.get("mention") or "That name"
    if client.get("unknown"):
        text = (f"No client contact named “{mention}” is in the client book, so this is OCBC research only. "
                f"Tell me which company {mention} is from (below) for client details.")
    else:
        names = ", ".join(dict.fromkeys(
            f"{c['contact_name']} ({c['client_name']})" if c.get("contact_name") else c["client_name"]
            for c in client["candidates"][:4]))
        text = (f"“{mention}” matches several clients ({names}), so this is OCBC research only. "
                f"Pick which one below for client details.")
    answer["notices"] = [{"kind": "info", "text": text}, *answer.get("notices", [])]
    answer["client"] = client
    if prior.get("client"):
        state["client"] = prior["client"]
    return answer, state


def routed_answer(question: str, prior: dict, mode: str, emit) -> tuple[dict, dict]:
    """Research mode or agent mode (app.orchestrator.router), with the client box for either."""
    client = identify_client(question, prior, emit)
    if client and client["status"] == "ambiguous":
        return generic_answer(question, client, prior, emit)
    matched = bool(client and client["status"] == "match")
    route = router.choose(question, client_matched=matched, last_mode=prior.get("last_mode"),
                          forced=mode if mode != "auto" else None)
    answer, why_not = None, None
    if route == "agent":
        answer, why_not = agent_answer(question, client, prior, emit)
    if answer is None:
        # Research sees the question with the client's name removed.
        research_q = (client or {}).get("research_question") or question
        answer, state = answer_question(research_q, prior, emit)
        answer["question"] = question
        if route == "auto" and answer["status"] in ("clarify", "info") and llm.status()["available"]:
            # Research could not place it ("what's a collar?", "hi"): answer as the assistant instead.
            tried, _ = agent_answer(question, client, prior, emit)
            if tried:
                answer, state = tried, dict(prior)
        elif why_not:
            answer["notices"] = [{"kind": "info", "text": f"{why_not} Here is OCBC research instead."},
                                 *answer.get("notices", [])]
    else:
        state = dict(prior)
    if answer.get("kind") == "agent":
        # Agent answers get the same compact client card as research answers (net position per pair,
        # "More details" with the trade list), shown right under the executive summary.
        if matched:
            answer["client"] = client
            state["client"] = client["candidates"][0]
            attach_agent_trade_context(client, answer, question, emit)
            attach_past_asks(client)
        elif prior.get("client"):
            state["client"] = prior["client"]
        return answer, state
    if client:
        answer["client"] = client
        if client["status"] == "match":
            state["client"] = client["candidates"][0]
            attach_trade_context(client, answer, question, emit)
            attach_past_asks(client)
        elif prior.get("client"):
            state["client"] = prior["client"]
    elif prior.get("client"):
        state["client"] = prior["client"]
    return answer, state


def pick_reply(cid: str, question: str, state: dict, pending: dict, pick: dict, owner: str, emit):
    """The next message answered "which client?" ("b", "Meridian Foods"): resolve the earlier
    answer's client and reply with the client box for that earlier question."""
    found = conversations.get_message(cid, pending["message_id"], owner)
    earlier, earlier_q = found if found else ({}, "")
    old = earlier.get("client") or {}
    if found and old and not old.get("logged") and not old.get("declined"):
        old.update(status="match", candidates=[pick], chosen_later=True)
        conversations.update_answer(cid, pending["message_id"], earlier | {"client": old})
    client = {"status": "match", "candidates": [pick], "research_question": old.get("research_question") or earlier_q,
              "mention": "", "inherited": False, "logged": None, "declined": False,
              "for_message": pending["message_id"], "for_question": earlier_q}
    attach_trade_context(client, earlier, earlier_q, emit)
    attach_past_asks(client)
    answer = _simple(question, "info", "")
    answer.update(suggestions=[], client=client)
    return answer, {**state, "client": pick}


def looks_like_company(text: str) -> bool:
    """A short reply naming a company, not a new question."""
    t = (text or "").strip()
    return 0 < len(t.split()) <= 6 and "?" not in t and not find_pairs(t) and not unknown_person(t)


def mark_unlisted(cid: str, mid: str, owner: str, company: str) -> tuple[dict, dict] | None:
    """The earlier answer's client box: the company named is not in the book; offer the memory card."""
    found = conversations.get_message(cid, mid, owner)
    if not found:
        return None
    earlier, _ = found
    client = earlier.get("client") or {}
    entry = memory_entry(client, company)
    client.update(status="unlisted", company=company.strip())
    conversations.update_answer(cid, mid, earlier | {"client": client, "pending_memory": entry})
    return client, entry


def unlisted_reply(cid: str, question: str, state: dict, pending: dict, owner: str):
    marked = mark_unlisted(cid, pending["message_id"], owner, question)
    answer = _simple(question, "info", "")
    answer["suggestions"] = []
    if marked:
        client, entry = marked
        answer["notices"] = [{"kind": "info", "text": f"{question.strip()} is not in the client book, so there are no "
                                                      f"trades to show. You can save {client['mention']}'s ask to "
                                                      f"client memory below."}]
        answer["pending_memory"] = entry
        return answer, {**state, "last_client": {"name": entry["name"], "company": entry["company"]}} if entry else state
    return answer, state


@app.get("/v1/health")
def health():
    return {"ok": True}


@app.get("/v1/demo", dependencies=[Depends(auth)])
def get_demo():
    try:
        return clientdata.demo()
    except ServiceError as exc:
        raise HTTPException(503, f"Client data unavailable ({exc}).")


@app.post("/v1/demo", dependencies=[Depends(auth)])
def set_demo(payload: dict = Body(...)):
    """Demo mode on/off (pattern clients T01-T04). Refused on the hosted demo."""
    if config.PUBLIC_MODE:
        raise HTTPException(403, "Demo mode is not available on the hosted demo.")
    try:
        return clientdata.demo(bool(payload.get("enabled")))
    except ServiceError as exc:
        code = str(exc).split(":", 1)[0]
        raise HTTPException(403 if code == "403" else 503, f"Demo mode could not be changed ({exc}).")


@app.get("/v1/meta", dependencies=[Depends(auth)])
def meta():
    out = {"model": llm.status(), "suggestions": SUGGESTIONS, "agent_suggestions": AGENT_SUGGESTIONS,
           "now": now_sgt().isoformat(),
           "now_label": fmt_dt(now_sgt()), "public_mode": config.PUBLIC_MODE}
    try:
        out["corpus"] = corpus_meta()
    except ServiceError as exc:
        out["corpus"] = None
        out["corpus_error"] = str(exc)
    return out


@app.get("/v1/conversations", dependencies=[Depends(auth)])
def list_conversations(x_ra_session: str = Header(default="local")):
    return conversations.list_all(x_ra_session)


@app.get("/v1/conversations/{cid}", dependencies=[Depends(auth)])
def get_conversation(cid: str, x_ra_session: str = Header(default="local")):
    c = conversations.get(cid, x_ra_session)
    if not c:
        raise HTTPException(404, "conversation not found")
    return c


@app.delete("/v1/conversations/{cid}", dependencies=[Depends(auth)])
def delete_conversation(cid: str, x_ra_session: str = Header(default="local")):
    conversations.delete(cid, x_ra_session)
    return {"deleted": cid}


@app.post("/v1/chat", dependencies=[Depends(auth)])
def chat(payload: dict = Body(...), x_ra_session: str = Header(default="local")):
    question = (payload.get("message") or "").strip()
    if not question or len(question) > 2000:
        raise HTTPException(400, "message must be 1-2000 characters")
    mode = payload.get("mode") if payload.get("mode") in MODES else "auto"
    cid = payload.get("conversation_id")
    if not cid or not conversations.exists(cid, x_ra_session):
        cid = conversations.create(question, x_ra_session)
    conversations.add_message(cid, "user", question)
    q: queue.Queue = queue.Queue()

    def emit(text: str):
        q.put({"type": "status", "text": text})

    def work():
        state = None
        try:
            prior = conversations.get_state(cid)
            # A "which client?" picker listens to the very next message only.
            pending = prior.pop("pending_pick", None)
            command = model_switch.parse_command(question)
            pick = clientdata.resolve_pick(question, pending["candidates"]) if pending and not command else None
            if command:
                # "turn on vincent claude api" etc.: no research; ask Yes/No before anything changes.
                answer, state = _simple(question, "info", ""), prior
                answer.update(suggestions=[], model_switch=model_switch.proposal(command))
            elif pick:
                answer, state = pick_reply(cid, question, prior, pending, pick, x_ra_session, emit)
            elif pending and pending.get("unknown") and looks_like_company(question):
                # "SuperHeroes Bank" in reply to "which company is Jeremy from?", and not in the book.
                answer, state = unlisted_reply(cid, question, prior, pending, x_ra_session)
            else:
                answer, state = routed_answer(question, prior, mode, emit)
                if answer.get("status") != "error":
                    # Both modes keep a short memory of the conversation for follow-ups.
                    state["last_mode"] = "agent" if answer.get("kind") == "agent" else "research"
                    state["turns"] = [*(prior.get("turns") or [])[-5:],
                                      {"q": question, "a": agent.turn_summary(answer)}]
        except Exception as exc:  # noqa: BLE001
            answer = _simple(question, "error", "Something went wrong while preparing the answer. Please try "
                                                "again.")
        mid = conversations.add_message(cid, "assistant", "", answer)
        if state is not None:
            client = answer.get("client") or {}
            if client.get("status") == "ambiguous":
                state["pending_pick"] = {"message_id": mid, "candidates": client["candidates"],
                                         "unknown": bool(client.get("unknown"))}
            conversations.set_state(cid, state)
        q.put({"type": "answer", "conversation_id": cid, "message_id": mid, "answer": answer})
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        yield f"data: {json.dumps({'type': 'conversation', 'conversation_id': cid})}\n\n"
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def _clear_pending(cid: str, mid: str, pick: dict | None = None):
    state = conversations.get_state(cid)
    if (state.get("pending_pick") or {}).get("message_id") == mid:
        state.pop("pending_pick")
    if pick:
        state["client"] = pick
    conversations.set_state(cid, state)


@app.post("/v1/model", dependencies=[Depends(auth)])
def set_model(payload: dict = Body(...)):
    """The mode-badge button, sent only after the user clicked Yes in its confirm box."""
    if config.PUBLIC_MODE:
        raise HTTPException(403, model_switch.PUBLIC_REFUSED)
    on = payload.get("enabled") is True
    if on and not model_switch.key_present():
        raise HTTPException(400, model_switch.NO_KEY)
    model_switch.set_on(on)
    return {"model": llm.status()}


@app.post("/v1/conversations/{cid}/messages/{mid}/model-switch", dependencies=[Depends(auth)])
def model_switch_confirm(cid: str, mid: str, payload: dict = Body(...), x_ra_session: str = Header(default="local")):
    """Yes / No on a "Turn ON/OFF Claude API?" box. Only Yes changes the switch; refused when hosted."""
    if config.PUBLIC_MODE:
        raise HTTPException(403, model_switch.PUBLIC_REFUSED)
    found = conversations.get_message(cid, mid, x_ra_session)
    if not found:
        raise HTTPException(404, "message not found")
    answer, _ = found
    entry = answer.get("model_switch")
    if not entry:
        raise HTTPException(400, "this message has no Claude API question")
    answer["model_switch"] = model_switch.confirm(entry, payload.get("confirm") is True)
    conversations.update_answer(cid, mid, answer)
    return {"model_switch": answer["model_switch"], "model": llm.status()}


@app.post("/v1/conversations/{cid}/messages/{mid}/client-pick", dependencies=[Depends(auth)])
def client_pick(cid: str, mid: str, payload: dict = Body(...), x_ra_session: str = Header(default="local")):
    """The user's answer to "which client?": a listed match (button), or typed text - a letter or a
    company name. Picking only sets the client; logging still needs its own confirmation."""
    found = conversations.get_message(cid, mid, x_ra_session)
    if not found:
        raise HTTPException(404, "message not found")
    answer, question = found
    client = answer.get("client")
    if not client or client.get("status") != "ambiguous" or client.get("logged") or client.get("declined"):
        raise HTTPException(400, "there is no open client choice on this answer")
    text = str(payload.get("text") or "").strip()[:200]
    if text:
        pick = clientdata.resolve_pick(text, client["candidates"])
        if not pick and client.get("unknown"):
            marked = mark_unlisted(cid, mid, x_ra_session, text)
            _clear_pending(cid, mid)
            if marked:
                return {"client": marked[0], "pending_memory": marked[1]}
        if not pick:
            raise HTTPException(400, f'No single client matches "{text}". Choose a letter, or type more of the '
                                     f"company name.")
    else:
        pick = next((c for c in client["candidates"] if c["client_id"] == payload.get("client_id")
                     and c.get("contact_id") == payload.get("contact_id")), None)
        if not pick:
            raise HTTPException(400, "choose one of the clients offered for this answer")
    client.update(status="match", candidates=[pick], picked=True)
    attach_trade_context(client, answer, question, lambda _text: None)
    attach_past_asks(client)
    answer["client"] = client
    conversations.update_answer(cid, mid, answer)
    _clear_pending(cid, mid, pick)
    return {"client": client}


@app.post("/v1/conversations/{cid}/messages/{mid}/client-log", dependencies=[Depends(auth)])
def client_log(cid: str, mid: str, payload: dict = Body(...), x_ra_session: str = Header(default="local")):
    """The user's answer to "log this interaction to <client>?". Only a client offered
    on that answer can be chosen; nothing is stored unless the user confirms."""
    found = conversations.get_message(cid, mid, x_ra_session)
    if not found:
        raise HTTPException(404, "message not found")
    answer, question = found
    client = answer.get("client")
    if not client:
        raise HTTPException(400, "no client was identified for this answer")
    if client.get("logged"):
        return {"client": client}
    if client.get("chosen_later"):
        raise HTTPException(400, "the client for this question was chosen in a later message; log it there")
    if client.get("for_message"):  # a "which client?" reply logs the question it resolved
        src = conversations.get_message(cid, client["for_message"], x_ra_session)
        if not src:
            raise HTTPException(404, "the original question was not found")
        source_answer, question = src
    else:
        source_answer = answer
    if payload.get("decline"):
        client["declined"] = True
    else:
        pick = next((c for c in client["candidates"] if c["client_id"] == payload.get("client_id")
                     and c.get("contact_id") == payload.get("contact_id")), None)
        if not pick:
            raise HTTPException(400, "choose one of the clients offered for this answer")
        summary = (" ".join(c.get("text", "") for c in (source_answer.get("direct") or [])[:2])
                   or source_answer.get("headline") or source_answer.get("message") or "")
        plan = source_answer.get("plan") or ({"lead": "Agent"} if source_answer.get("kind") == "agent" else {})
        try:
            row = clientdata.log_interaction({
                "client_id": pick["client_id"], "contact_id": pick.get("contact_id"), "question": question,
                "instruments": plan.get("instruments") or [], "topic": plan.get("lead") or "",
                "answer_summary": summary, "conversation_id": cid, "logged_by": x_ra_session})
        except ServiceError as exc:
            raise HTTPException(503, f"Could not save to the client profile ({exc}).")
        client.update(logged={"interaction_id": row["interaction_id"], "at": row["asked_at"]}, declined=False,
                      status="match", candidates=[pick])
    _clear_pending(cid, mid, None if client.get("declined") else client["candidates"][0])
    answer["client"] = client
    conversations.update_answer(cid, mid, answer)
    return {"client": client}


@app.post("/v1/memory/confirm", dependencies=[Depends(auth)])
def memory_confirm(payload: dict = Body(...)):
    entry = {k: str(payload.get(k) or "").strip()[:300] for k in ("name", "company", "description", "time")}
    if not all(entry.values()):
        raise HTTPException(400, "name, company, description and time are required")
    client_memory.save(entry)
    return {"saved": True, "recent": client_memory.history(entry["name"], 5)}
