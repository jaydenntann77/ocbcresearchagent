"""Client-data service (port 8105) - owns the synthetic client book.

Only the orchestrator can call it (orchestrator token). The orchestrator never
opens the client database itself, and this service has no network access and
no access to the research corpus. dummy_data/ is read-only for this process.

  POST /v1/identify            which client / contact a question refers to
  GET  /v1/clients/{id}        profile, contacts and recent logged interactions
  POST /v1/interactions        log a confirmed client interaction (always to the database)
  POST /v1/resolve-pick        which listed match a reply ("b", "Meridian Foods") picks
  POST /v1/clients/{id}/trade-context   the client's own trades in the asked pair(s), as a neutral note
  GET  /v1/demo, POST /v1/demo demo mode: pattern clients T01-T04 (OFF at every start; refused in public mode)
"""
from __future__ import annotations

from app.common import config, guard

guard.install(guard.Policy(
    role="clientdata",
    denied_roots=[config.DATA_DIR],
    allowed_roots=[config.CLIENT_DIR],
    read_only_roots=[config.ROOT / "dummy_data"],
    allowed_hosts=set(),
    allowed_loopback_ports=set(),
    blocked_modules=("fitz", "pymupdf", "fastembed", "onnxruntime", "app.research", "app.ingestion",
                     "app.validator", "app.docs", "app.orchestrator", "app.common.embedding"),
))

import re  # noqa: E402

from fastapi import Body, Depends, FastAPI, HTTPException  # noqa: E402

from app.clientdata.book import ClientBook  # noqa: E402
from app.clientdata.identify import identify, resolve_pick  # noqa: E402
from app.clientdata.store import Store  # noqa: E402
from app.clientdata.trade_context import trade_contexts  # noqa: E402
from app.common.security import require_token  # noqa: E402
from app.common.timeutil import today_sgt  # noqa: E402

app = FastAPI(title="Client data", docs_url=None, redoc_url=None, openapi_url=None)
auth = require_token(config.TOKEN_ORCH_CLIENTS)
book = ClientBook(Store())          # demo mode OFF at every start
ID_RE = re.compile(r"^[A-Za-z0-9\-]{1,20}$")


@app.get("/v1/health")
def health():
    return {"ok": True}


def demo_state() -> dict:
    return {"enabled": book.demo, "available": not config.PUBLIC_MODE}


@app.get("/v1/demo", dependencies=[Depends(auth)])
def get_demo():
    return demo_state()


@app.post("/v1/demo", dependencies=[Depends(auth)])
def set_demo(payload: dict = Body(...)):
    if config.PUBLIC_MODE:
        raise HTTPException(403, "Demo mode is not available on the hosted demo.")
    book.set_demo(bool(payload.get("enabled")))
    return demo_state()


@app.post("/v1/identify", dependencies=[Depends(auth)])
def identify_client(payload: dict = Body(...)):
    question = (payload.get("question") or "").strip()
    if not question or len(question) > 2000:
        raise HTTPException(400, "question must be 1-2000 characters")
    return identify(question, book.clients(), book.contacts()).to_dict()


@app.get("/v1/clients/{client_id}", dependencies=[Depends(auth)])
def client_profile(client_id: str):
    c = book.client(client_id) if ID_RE.match(client_id) else None
    if not c:
        raise HTTPException(404, "client not found")
    return {"client": c, "contacts": book.contacts(client_id), "interactions": book.interactions(client_id)}


@app.get("/v1/clients/{client_id}/asks", dependencies=[Depends(auth)])
def client_asks(client_id: str, contact_id: str | None = None, limit: int = 3):
    """Earlier logged asks from this contact (the whole client when no contact is known), newest
    first, with the client's name taken out of each question. Keyed by contact ID, so two people
    who share a first name at different clients never share a history."""
    c = book.client(client_id) if ID_RE.match(client_id) else None
    if not c:
        raise HTTPException(404, "client not found")
    if contact_id and not ID_RE.match(contact_id):
        raise HTTPException(400, "invalid contact id")
    rows = [r for r in book.interactions(client_id, limit=1000) if not contact_id or r.get("contact_id") == contact_id]
    clients, contacts = book.clients(), book.contacts()
    items = []
    for r in rows[:max(1, min(limit, 10))]:
        q = r.get("question") or ""
        try:
            q = identify(q, clients, contacts).research_question or q
        except Exception:  # noqa: BLE001 - fall back to the question as logged
            pass
        items.append({"asked_at": r.get("asked_at"), "question": q[:200], "topic": r.get("topic") or "",
                      "instruments": r.get("instruments") or ""})
    return {"count": len(rows), "items": items}


@app.post("/v1/resolve-pick", dependencies=[Depends(auth)])
def pick(payload: dict = Body(...)):
    text = (payload.get("text") or "").strip()
    cands = payload.get("candidates") or []
    if not text or len(text) > 200 or not isinstance(cands, list) or len(cands) > 10:
        raise HTTPException(400, "text must be 1-200 characters and candidates at most 10")
    cands = [c for c in cands if isinstance(c, dict) and ID_RE.match(str(c.get("client_id") or ""))
             and book.client(c["client_id"])]
    return {"pick": resolve_pick(text, cands, book.clients(), book.contacts())}


@app.post("/v1/clients/{client_id}/trade-context", dependencies=[Depends(auth)])
def client_trade_context(client_id: str, payload: dict = Body(...)):
    c = book.client(client_id) if ID_RE.match(client_id) else None
    if not c:
        raise HTTPException(404, "client not found")
    pairs = [str(p)[:10] for p in (payload.get("pairs") or [])][:5]
    return {"contexts": trade_contexts(book.trades(c), pairs, today_sgt(), book.interactions(client_id, limit=1000))}


@app.post("/v1/interactions", dependencies=[Depends(auth)])
def log_interaction(payload: dict = Body(...)):
    cid, pid = payload.get("client_id") or "", payload.get("contact_id")
    if not ID_RE.match(cid) or not book.client(cid):
        raise HTTPException(404, "client not found")
    if pid:
        contact = book.contact(pid) if ID_RE.match(pid) else None
        if not contact or contact["client_id"] != cid:
            raise HTTPException(400, "contact does not belong to this client")
    question = (payload.get("question") or "").strip()
    if not question or len(question) > 2000:
        raise HTTPException(400, "question must be 1-2000 characters")
    row = book.add_interaction({
        "client_id": cid, "contact_id": pid, "question": question,
        "instruments": ";".join(payload.get("instruments") or [])[:200],
        "topic": (payload.get("topic") or "")[:40], "answer_summary": (payload.get("answer_summary") or "")[:1000],
        "conversation_id": (payload.get("conversation_id") or "")[:40] or None,
        "logged_by": (payload.get("logged_by") or "")[:80] or None,
    })
    return {"interaction": row}
