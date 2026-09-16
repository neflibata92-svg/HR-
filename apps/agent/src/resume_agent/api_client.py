"""内网 API 客户端。"""

from __future__ import annotations

from typing import Any

import httpx

from resume_agent.config import AgentSettings


class ApiClient:
    def __init__(self, settings: AgentSettings) -> None:
        self.settings = settings
        self._headers = {"X-Api-Token": settings.api_token}

    def _url(self, path: str) -> str:
        return f"{self.settings.api_base_url.rstrip('/')}{path}"

    def list_enabled_jobs(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(self._url("/api/jobs/enabled"), headers=self._headers)
            response.raise_for_status()
            return response.json()

    def upsert_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                self._url("/api/candidates"),
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def exchange_blocked(self, candidate_id: int) -> bool:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                self._url(f"/api/candidates/{candidate_id}/exchange-blocked"),
                headers=self._headers,
            )
            response.raise_for_status()
            return bool(response.json()["blocked"])

    def post_score(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                self._url("/api/events/scores"),
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def post_outreach(self, payload: dict[str, Any]) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                self._url("/api/events/outreach"),
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    def heartbeat(self, status: str, last_error: str = "") -> None:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                self._url("/api/agent/runs"),
                headers=self._headers,
                json={
                    "machine_id": self.settings.machine_id,
                    "status": status,
                    "last_error": last_error,
                },
            )
            response.raise_for_status()
