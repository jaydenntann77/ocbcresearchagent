"""Evidence validation service (port 8102).

POST /v1/validate takes a draft answer and the specialist evidence bundle and
returns verdicts only. It reads the corpus store read-only to verify that
cited documents, pages, passages and forecast cells exist and match."""
from __future__ import annotations

from fastapi import Depends, FastAPI

from app.common import config, guard

guard.install(guard.Policy(
    role="validator",
    denied_roots=[config.ORCH_DIR, config.RAW_DIR, config.COLLECTIONS_DIR],
    read_only_roots=[config.DATA_DIR / "corpus"],
    allowed_hosts=set(),
))

from app.common.schemas import ValidationReport, ValidationRequest  # noqa: E402
from app.common.security import require_token  # noqa: E402
from app.validator.checks import Validator  # noqa: E402

app = FastAPI(title="Evidence validator", docs_url=None, redoc_url=None, openapi_url=None)
validator = Validator()


@app.get("/v1/health")
def health():
    return {"ok": True, "corpus_present": config.META_DB.exists()}


@app.post("/v1/validate", response_model=ValidationReport,
          dependencies=[Depends(require_token(config.TOKEN_ORCH_VALIDATOR))])
def validate(req: ValidationRequest) -> ValidationReport:
    return validator.validate(req.draft, req.bundle)
