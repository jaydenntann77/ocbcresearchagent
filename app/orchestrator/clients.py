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
