"""Service tokens and evidence signing."""
from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import Header, HTTPException


def require_token(expected: str | None):
    """FastAPI dependency factory: a request must carry exactly this bearer token."""

    def _dep(authorization: str | None = Header(default=None)):
        if not expected:
            raise HTTPException(503, "service token not configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing service token")
        if not hmac.compare_digest(authorization[7:], expected):
            raise HTTPException(403, "token not authorised for this endpoint")

    return _dep


_SIGNED_FIELDS = ("evidence_id", "doc_id", "publication_date", "source_url", "pdf_page", "excerpt", "table_id")


def evidence_signature(key: str, ev: dict) -> str:
    payload = json.dumps({k: ev.get(k) for k in _SIGNED_FIELDS}, sort_keys=True, ensure_ascii=False)
    return hmac.new(key.encode(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_evidence_signature(key: str, ev: dict) -> bool:
    sig = ev.get("signature") or ""
    return bool(sig) and hmac.compare_digest(sig, evidence_signature(key, ev))
