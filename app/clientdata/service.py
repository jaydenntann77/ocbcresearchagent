"""Client-data service (port 8105) - owns the synthetic client book.

Only the orchestrator can call it (orchestrator token). The orchestrator never
opens the client database itself, and this service has no network access and
no access to the research corpus.

  POST /v1/identify            which client / contact a question refers to
  GET  /v1/clients/{id}        profile, contacts and recent logged interactions
  POST /v1/interactions        log a confirmed client interaction
"""
from __future__ import annotations

from app.common import config, guard

guard.install(guard.Policy(
    role="clientdata",
    denied_roots=[config.DATA_DIR],
    allowed_roots=[config.CLIENT_DIR],
    allowed_hosts=set(),
    allowed_loopback_ports=set(),
    blocked_modules=("fitz", "pymupdf", "fastembed", "onnxruntime", "app.research", "app.ingestion",
                     "app.validator", "app.docs", "app.orchestrator", "app.common.embedding"),
))

import re  # noqa: E402

from fastapi import Body, Depends, FastAPI, HTTPException  # noqa: E402

from app.clientdata.identify import identify  # noqa: E402
from app.clientdata.store import Store  # noqa: E402
from app.common.security import require_token  # noqa: E402

app = FastAPI(title="Client data", docs_url=None, redoc_url=None, openapi_url=None)
auth = require_token(config.TOKEN_ORCH_CLIENTS)
store = Store()
ID_RE = re.compile(r"^[A-Za-z0-9\-]{1,20}$")


@app.get("/v1/health")
def health():
    return {"ok": True}


@app.post("/v1/identify", dependencies=[Depends(auth)])
def identify_client(payload: dict = Body(...)):
    question = (payload.get("question") or "").strip()
    if not question or len(question) > 2000:
        raise HTTPException(400, "question must be 1-2000 characters")
    return identify(question, store.clients(), store.contacts()).to_dict()


@app.get("/v1/clients/{client_id}", dependencies=[Depends(auth)])
def client_profile(client_id: str):
    c = store.client(client_id) if ID_RE.match(client_id) else None
    if not c:
        raise HTTPException(404, "client not found")
    return {"client": c, "contacts": store.contacts(client_id), "interactions": store.interactions(client_id)}


@app.post("/v1/interactions", dependencies=[Depends(auth)])
def log_interaction(payload: dict = Body(...)):
    cid, pid = payload.get("client_id") or "", payload.get("contact_id")
    if not ID_RE.match(cid) or not store.client(cid):
        raise HTTPException(404, "client not found")
    if pid:
        contact = store.contact(pid) if ID_RE.match(pid) else None
        if not contact or contact["client_id"] != cid:
            raise HTTPException(400, "contact does not belong to this client")
    question = (payload.get("question") or "").strip()
    if not question or len(question) > 2000:
        raise HTTPException(400, "question must be 1-2000 characters")
    row = store.add_interaction({
        "client_id": cid, "contact_id": pid, "question": question,
        "instruments": ";".join(payload.get("instruments") or [])[:200],
        "topic": (payload.get("topic") or "")[:40], "answer_summary": (payload.get("answer_summary") or "")[:1000],
        "conversation_id": (payload.get("conversation_id") or "")[:40] or None,
        "logged_by": (payload.get("logged_by") or "")[:80] or None,
    })
    return {"interaction": row}
