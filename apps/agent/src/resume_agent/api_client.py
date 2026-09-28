"""内网 API 客户端。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from resume_domain.llm_schema import LlmScoreResult
from resume_agent.config import AgentSettings


_UNSET = object()


class ApiClient:
    def __init__(self, settings: AgentSettings) -> None:
        if not settings.api_key.strip():
            raise ValueError("API_KEY is required; create a personal Agent API Key in the web console")
        self.settings = settings
        self._headers = {"X-Api-Key": settings.api_key}

    def _url(self, path: str) -> str:
        return f"{self.settings.api_base_url.rstrip('/')}{path}"

    def get_task(self, task_id: int) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                self._url(f"/api/screening-tasks/{task_id}"),
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    def claim_task(self, task_id: int) -> dict[str, Any]:
        return self._post(
            f"/api/screening-tasks/{task_id}/claim",
            {"machine_id": self.settings.machine_id},
        )

    def acknowledge_control(self, task_id: int) -> dict[str, Any]:
        return self._post(
            f"/api/screening-tasks/{task_id}/control/ack",
            {"machine_id": self.settings.machine_id},
        )

    def create_task_item(
        self, task_id: int, *, candidate_id: int, position_index: int
    ) -> dict[str, Any]:
        return self._post(
            f"/api/screening-tasks/{task_id}/items",
            {
                "machine_id": self.settings.machine_id,
                "candidate_id": candidate_id,
                "position_index": position_index,
            },
        )

    def complete_task_item(
        self,
        task_id: int,
        item_id: int,
        *,
        status: str,
        score_event_id: int | None = None,
        outreach_event_id: int | None = None,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/screening-tasks/{task_id}/items/{item_id}/complete",
            {
                "machine_id": self.settings.machine_id,
                "status": status,
                "score_event_id": score_event_id,
                "outreach_event_id": outreach_event_id,
            },
        )

    def fail_task_item(
        self,
        task_id: int,
        item_id: int,
        *,
        failure_code: str,
        failure_detail: str = "",
    ) -> dict[str, Any]:
        return self._post(
            f"/api/screening-tasks/{task_id}/items/{item_id}/fail",
            {
                "machine_id": self.settings.machine_id,
                "failure_code": failure_code,
                "failure_detail": failure_detail,
            },
        )

    def pause_task(self, task_id: int, reason: str) -> dict[str, Any]:
        return self._post(f"/api/screening-tasks/{task_id}/pause", {"reason": reason})

    def complete_task(self, task_id: int) -> dict[str, Any]:
        return self._post(
            f"/api/screening-tasks/{task_id}/complete",
            {"machine_id": self.settings.machine_id},
        )

    def reserve_outreach(
        self,
        candidate_id: int,
        job_id: int,
        *,
        task_id: int,
        task_item_id: int,
        message: str,
    ) -> dict[str, Any]:
        return self._post(
            "/api/outreach/reservations",
            {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "task_id": task_id,
                "task_item_id": task_item_id,
                "message": message,
            },
        )

    def confirm_outreach(self, event_id: int) -> dict[str, Any]:
        return self._post(f"/api/outreach/{event_id}/confirm", None)

    def fail_outreach(self, event_id: int, reason: str) -> dict[str, Any]:
        return self._post(f"/api/outreach/{event_id}/fail", {"reason": reason})

    def unknown_outreach(self, event_id: int, reason: str) -> dict[str, Any]:
        return self._post(f"/api/outreach/{event_id}/unknown", {"reason": reason})

    def _post(self, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(self._url(path), headers=self._headers, json=payload)
            response.raise_for_status()
            return response.json()

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

    def score_candidate(
        self,
        jd: str,
        summary: str,
        *,
        threshold: int,
    ) -> LlmScoreResult:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                self._url("/api/scoring/evaluate"),
                headers=self._headers,
                json={
                    "jd": jd,
                    "summary": summary,
                    "threshold": threshold,
                },
            )
            response.raise_for_status()
            return LlmScoreResult.model_validate(response.json())

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

    def outreach_exists(self, job_id: int, candidate_id: int) -> bool:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                self._url("/api/events/outreach"),
                headers=self._headers,
                params={"job_id": job_id, "candidate_id": candidate_id},
            )
            response.raise_for_status()
            return bool(response.json().get("exists"))

    def upload_resume_file(
        self,
        path: Path,
        *,
        candidate_id: int | None = None,
        source: str = "boss_attachment",
    ) -> dict[str, Any]:
        with path.open("rb") as handle:
            files = {"file": (path.name, handle)}
            data: dict[str, str] = {"source": source}
            if candidate_id is not None:
                data["candidate_id"] = str(candidate_id)
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    self._url("/api/resumes/upload"),
                    headers=self._headers,
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                return response.json()

    def mark_attachment_received(self, job_id: int, candidate_id: int) -> dict[str, Any]:
        return self.post_outreach(
            {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "greeted": True,
                "attachment_received": True,
            }
        )

    def list_resume_inbox(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(
                self._url("/api/candidates/resume-inbox"),
                headers=self._headers,
            )
            response.raise_for_status()
            return response.json()

    def upload_agent_resume(
        self,
        path: Path,
        *,
        candidate_id: int,
        contact_event_id: int,
    ) -> dict[str, Any]:
        with path.open("rb") as handle:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
                    self._url("/api/resumes/agent-upload"),
                    headers=self._headers,
                    files={"file": (path.name, handle, "application/pdf")},
                    data={
                        "candidate_id": str(candidate_id),
                        "contact_event_id": str(contact_event_id),
                    },
                )
                response.raise_for_status()
                return response.json()

    def heartbeat(
        self,
        status: str,
        last_error: str = "",
        *,
        availability: str | None = None,
        current_task_id: int | None | object = _UNSET,
        current_job_id: int | None | object = _UNSET,
        boss_login_status: str = "unknown",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "machine_id": self.settings.machine_id,
            "status": status,
            "boss_login_status": boss_login_status,
            "last_error": last_error,
        }
        if availability is not None:
            payload["availability"] = availability
        if current_task_id is not _UNSET:
            payload["current_task_id"] = current_task_id
        if current_job_id is not _UNSET:
            payload["current_job_id"] = current_job_id
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                self._url("/api/agent/runs"),
                headers=self._headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()
