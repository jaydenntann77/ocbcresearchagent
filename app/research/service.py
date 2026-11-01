"""Specialist execution service (port 8101).

Only endpoint for agents: POST /v1/tasks, authenticated with the
orchestrator's task token. There is deliberately no search, chunk, document or
embedding endpoint: corpus content leaves this process only as evidence
excerpts inside a validated SpecialistResponse.

Process policy: no internet (loopback only), read-only corpus access, no
access to orchestrator conversation storage."""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from app.common import config, guard

guard.install(guard.Policy(
    role="research",
    denied_roots=[config.ORCH_DIR, config.RAW_DIR],
    read_only_roots=[config.DATA_DIR / "corpus", config.COLLECTIONS_DIR, config.MODELS_DIR],
    allowed_hosts=set(),
))

from app.common import embedding  # noqa: E402
from app.common.schemas import SPECIALISTS, SpecialistResponse, SpecialistTask  # noqa: E402
from app.common.security import require_token  # noqa: E402
from app.research.collections import CollectionRegistry  # noqa: E402
from app.research.specialists import CorpusStatus, Specialist  # noqa: E402

app = FastAPI(title="Specialist research service", docs_url=None, redoc_url=None, openapi_url=None)
registry = CollectionRegistry()
status = CorpusStatus()
agents = {name: Specialist(name, registry, status) for name in SPECIALISTS}
task_auth = require_token(config.TOKEN_ORCH_RESEARCH)


@app.get("/v1/health")
def health():
    return {"ok": True, "collections_ready": registry.ready(), "build": registry.pointer.get("build"),
            "semantic_retrieval": embedding.available(), "specialists": list(SPECIALISTS)}


@app.post("/v1/tasks", response_model=SpecialistResponse, dependencies=[Depends(task_auth)])
def run_task(task: SpecialistTask) -> SpecialistResponse:
    agent = agents.get(task.specialist)
    if agent is None:
        raise HTTPException(404, "unknown specialist")
    try:
        result = agent.run(task)
    except Exception as exc:  # noqa: BLE001
        return SpecialistResponse(task_id=task.task_id, specialist=task.specialist, status="error",
                                  limitations=[f"retrieval failure: {type(exc).__name__}"])
    # Re-validate the outbound payload against the strict contract.
    return SpecialistResponse.model_validate(result.model_dump())


@app.get("/v1/coverage", dependencies=[Depends(task_auth)])
def coverage():
    """Corpus-level metadata (counts and dates only) for freshness banners."""
    out = {}
    for name in SPECIALISTS:
        handles = registry.grant(name)
        docs = [d for h in handles for d in h.documents()]
        out[name] = {"documents": len({d["doc_id"] for d in docs}),
                     "publication_dates": sorted({d["publication_date"] for d in docs if d["publication_date"]})}
    state = status.corpus_state()
    return {"window": state.get("active_window") or {"start": registry.pointer.get("window_start"),
                                                     "end": registry.pointer.get("window_end")},
            "last_successful_run": state.get("last_successful_run"), "specialists": out}
