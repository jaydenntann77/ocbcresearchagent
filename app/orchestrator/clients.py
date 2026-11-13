"""Narrow service interfaces available to the orchestrator: dispatch a
specialist task, validate a draft answer, read corpus-level coverage metadata.
There is no client for search, documents, embeddings or the web."""
from __future__ import annotations

import httpx

from app.common import config
from app.common.schemas import (DraftAnswer, EvidenceBundle, SpecialistResponse, SpecialistTask, ValidationReport,
                                ValidationRequest)


class ServiceError(Exception):
    pass


class ResearchClient:
    def __init__(self, base: str | None = None, token: str | None = None, timeout: float = 120.0):
        self.base = base or config.service_url("research")
        self.token = token or config.TOKEN_ORCH_RESEARCH
        self.client = httpx.Client(timeout=timeout)

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def run_task(self, task: SpecialistTask) -> SpecialistResponse:
        try:
            r = self.client.post(f"{self.base}/v1/tasks", json=task.model_dump(), headers=self._h())
        except httpx.HTTPError as exc:
            raise ServiceError(f"specialist service unreachable ({type(exc).__name__})") from exc
        if r.status_code != 200:
            raise ServiceError(f"specialist service returned HTTP {r.status_code}")
        # Strict contract: unexpected fields (e.g. user-directed messages) are rejected.
        return SpecialistResponse.model_validate(r.json())

    def coverage(self) -> dict:
        try:
            r = self.client.get(f"{self.base}/v1/coverage", headers=self._h())
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as exc:
            raise ServiceError(f"coverage unavailable ({type(exc).__name__})") from exc


class ValidatorClient:
    def __init__(self, base: str | None = None, token: str | None = None):
        self.base = base or config.service_url("validator")
        self.token = token or config.TOKEN_ORCH_VALIDATOR
        self.client = httpx.Client(timeout=60.0)

    def validate(self, draft: DraftAnswer, bundle: EvidenceBundle) -> ValidationReport:
        req = ValidationRequest(draft=draft, bundle=bundle)
        try:
            r = self.client.post(f"{self.base}/v1/validate", json=req.model_dump(),
                                 headers={"Authorization": f"Bearer {self.token}"})
        except httpx.HTTPError as exc:
            raise ServiceError(f"validator unreachable ({type(exc).__name__})") from exc
        if r.status_code != 200:
            raise ServiceError(f"validator returned HTTP {r.status_code}")
        return ValidationReport.model_validate(r.json())


class ClientDataClient:
    """Client-data service: identify the client in a question and log confirmed
    interactions. Client lookups are optional - a failure never blocks an answer."""

    def __init__(self, base: str | None = None, token: str | None = None):
        self.base = base or config.service_url("clientdata")
        self.token = token or config.TOKEN_ORCH_CLIENTS
        self.client = httpx.Client(timeout=15.0)

    def _h(self):
        return {"Authorization": f"Bearer {self.token}"}

    def identify(self, question: str) -> dict | None:
        try:
            r = self.client.post(f"{self.base}/v1/identify", json={"question": question}, headers=self._h())
        except httpx.HTTPError:
            return None
        return r.json() if r.status_code == 200 else None

    def demo(self, enabled: bool | None = None) -> dict:
        """Read (enabled=None) or set demo mode. Raises ServiceError with the status on refusal."""
        try:
            if enabled is None:
                r = self.client.get(f"{self.base}/v1/demo", headers=self._h())
            else:
                r = self.client.post(f"{self.base}/v1/demo", json={"enabled": enabled}, headers=self._h())
        except httpx.HTTPError as exc:
            raise ServiceError(f"client-data service unreachable ({type(exc).__name__})") from exc
        if r.status_code != 200:
            raise ServiceError(f"{r.status_code}:{(r.json() or {}).get('detail', '') if r.content else ''}")
        return r.json()

    def exists(self, client_id: str) -> bool:
        """Whether a client is visible right now (pattern clients only while demo mode is on)."""
        try:
            r = self.client.get(f"{self.base}/v1/clients/{client_id}", headers=self._h())
        except httpx.HTTPError:
            return True   # a lookup failure never drops the conversation's client
        return r.status_code == 200

    def past_asks(self, client_id: str, contact_id: str | None) -> dict | None:
        """Earlier logged asks from this contact (None on any failure - never blocks an answer)."""
        params = {"contact_id": contact_id} if contact_id else {}
        try:
            r = self.client.get(f"{self.base}/v1/clients/{client_id}/asks", params=params, headers=self._h())
        except httpx.HTTPError:
            return None
        return r.json() if r.status_code == 200 else None

    def resolve_pick(self, text: str, candidates: list[dict]) -> dict | None:
        try:
            r = self.client.post(f"{self.base}/v1/resolve-pick", json={"text": text, "candidates": candidates},
                                 headers=self._h())
        except httpx.HTTPError:
            return None
        return r.json().get("pick") if r.status_code == 200 else None

    def trade_context(self, client_id: str, pairs: list[str]) -> list[dict]:
        """Neutral notes on the client's own trades in these pairs ([] on any failure)."""
        try:
            r = self.client.post(f"{self.base}/v1/clients/{client_id}/trade-context", json={"pairs": pairs},
                                 headers=self._h())
        except httpx.HTTPError:
            return []
        return r.json().get("contexts") or [] if r.status_code == 200 else []

    def log_interaction(self, payload: dict) -> dict:
        try:
            r = self.client.post(f"{self.base}/v1/interactions", json=payload, headers=self._h())
        except httpx.HTTPError as exc:
            raise ServiceError(f"client-data service unreachable ({type(exc).__name__})") from exc
        if r.status_code != 200:
            raise ServiceError(f"client-data service returned HTTP {r.status_code}")
        return r.json()["interaction"]
