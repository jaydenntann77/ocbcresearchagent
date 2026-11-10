"""Conversation API + main orchestrator (port 8100). The only agent that
talks to the user.

Process policy (enforced by app.common.guard, installed before anything else):
  * no filesystem access to the corpus, raw PDFs, collections or models -
    only data/orchestrator (conversation history);
  * loopback connections only to the specialist (8101) and validator (8102)
    services; internet only to the model API when a credential is configured;
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
    allowed_loopback_ports={config.PORTS["research"], config.PORTS["validator"]},
    blocked_modules=("fitz", "pymupdf", "fastembed", "onnxruntime", "rapidocr_onnxruntime", "app.research",
                     "app.ingestion", "app.validator", "app.docs", "app.common.embedding"),
))

import json  # noqa: E402
import queue  # noqa: E402
import threading  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from datetime import date, datetime  # noqa: E402

from fastapi import Body, Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402

from app.common.schemas import SPECIALIST_LABELS  # noqa: E402
from app.common.security import require_token  # noqa: E402
from app.common.timeutil import fmt_dt, fmt_range, now_sgt  # noqa: E402
from app.orchestrator import client_memory, composer, conversations, guardrails, llm, planner  # noqa: E402from app.orchestrator.clients import ResearchClient, ServiceError, ValidatorClient  # noqa: E402
from app.orchestrator.clients import ResearchClient, ServiceError, ValidatorClient  # noqa: E402

app = FastAPI(title="Conversation API", docs_url=None, redoc_url=None, openapi_url=None)
auth = require_token(config.TOKEN_GATEWAY_ORCH)
research = ResearchClient()
validator = ValidatorClient()
SUGGESTIONS = [
    "What does the latest available research say about USD/SGD through 2027?",
    "Summarize OCBC's published view on SGD interest rates.",
    "What are the main risks identified in the latest credit research?",
    "What is OCBC's forecast for the Fed funds rate and 10-year UST yield?",
    "What is OCBC's latest view on JPY and the BoJ?",
]


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
    emit("Checking corpus coverage")
    try:
        corpus = corpus_meta()
    except ServiceError as exc:
        return _simple(question, "error", f"The research service is unavailable ({exc}). No answer was generated; "
                                          f"please retry or contact the administrator.", notices), state
    w = corpus["window"]
    if not w.get("start"):
        return _simple(question, "error", "The research knowledge base has not been built yet. An administrator "
                                          "needs to run ingestion (Corpus status → Refresh).", notices, corpus), state
    emit("Understanding the request")
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
            emit("Requesting supporting macro research")
            responses += [run(t) for t in extra]
    use_model = llm.status()["available"]
    if use_model and not conversations.take_model_call(config.MODEL_DAILY_CAP):
        use_model = False
        notices.append({"kind": "info", "text": "Today's budget for model-written summaries has been used up, so this "
                                                "answer quotes the OCBC sources directly. Full summaries resume tomorrow "
                                                "(SGT)."})
    emit("Validating evidence and citations")
    try:
        answer = composer.compose(question, plan, responses, validator, notices, corpus, use_model=use_model)
    except ServiceError as exc:
        return _simple(question, "error", f"The evidence validator is unavailable ({exc}), so the answer was withheld "
                                          f"rather than shown unvalidated. Please retry shortly.", notices, corpus), state
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

@app.get("/v1/health")
def health():
    return {"ok": True}


@app.get("/v1/meta", dependencies=[Depends(auth)])
def meta():
    out = {"model": llm.status(), "suggestions": SUGGESTIONS, "now": now_sgt().isoformat(),
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
    cid = payload.get("conversation_id")
    if not cid or not conversations.exists(cid, x_ra_session):
        cid = conversations.create(question, x_ra_session)
    conversations.add_message(cid, "user", question)
    q: queue.Queue = queue.Queue()

    def emit(text: str):
        q.put({"type": "status", "text": text})

    def work():
        try:
            answer, state = answer_question(question, conversations.get_state(cid), emit)
            conversations.set_state(cid, state)
        except Exception as exc:  # noqa: BLE001
            answer = _simple(question, "error", f"Something went wrong while preparing the answer "
                                                f"({type(exc).__name__}). No unverified content is shown.")
        mid = conversations.add_message(cid, "assistant", "", answer)
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

@app.post("/v1/memory/confirm", dependencies=[Depends(auth)])
def memory_confirm(payload: dict = Body(...)):
    entry = {k: str(payload.get(k) or "").strip()[:300] for k in ("name", "company", "description", "time")}
    if not all(entry.values()):
        raise HTTPException(400, "name, company, description and time are required")
    client_memory.save(entry)
    return {"saved": True, "recent": client_memory.history(entry["name"], 5)}