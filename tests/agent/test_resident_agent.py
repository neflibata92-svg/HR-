from __future__ import annotations

from pathlib import Path
from threading import Event
from time import monotonic
from unittest.mock import Mock

from resume_agent.config import AgentSettings
from resume_agent.resident import ResidentAgent
from resume_agent.resume_monitor import ResumeMonitor


class ResidentApi:
    def __init__(self, *, task_status: str = "ready") -> None:
        self.task_status = task_status
        self.heartbeats: list[dict[str, object]] = []
        self.claimed: list[int] = []

    def heartbeat(self, status: str, **payload):
        self.heartbeats.append({"status": status, **payload})
        return {
            "id": 5,
            "machine_id": "mac-a",
            "owner_user_id": 2,
            "status": status,
            "availability": payload.get("availability", "idle"),
            "current_task_id": 7,
            "current_job_id": 9,
            "boss_login_status": payload.get("boss_login_status", "logged_in"),
            "last_error": payload.get("last_error", ""),
            "last_heartbeat": "2026-09-23T00:00:00Z",
        }

    def get_task(self, task_id: int):
        return {
            "id": task_id,
            "job_id": 9,
            "status": self.task_status,
            "requested_count": 1,
            "boss_entry_url": "https://example/jobs/9",
        }

    def claim_task(self, task_id: int):
        self.claimed.append(task_id)
        task = self.get_task(task_id)
        task["status"] = "running"
        return task


def test_resident_agent_only_claims_server_assigned_task() -> None:
    api = ResidentApi()
    executed: list[int] = []
    monitored: list[bool] = []
    agent = ResidentAgent(
        AgentSettings(api_key="x", machine_id="mac-a"),
        api,
        run_task=lambda task: executed.append(task["id"]),
        poll_resumes=lambda: monitored.append(True),
        check_login_status=lambda: "logged_in",
    )

    agent.run_cycle()

    assert api.claimed == [7]
    assert executed == [7]
    assert monitored == [True]
    assert api.heartbeats[0] == {
        "status": "idle",
        "availability": "idle",
        "boss_login_status": "logged_in",
        "last_error": "",
    }
    assert api.heartbeats[1]["status"] == "running"
    assert api.heartbeats[1]["current_task_id"] == 7
    assert api.heartbeats[1]["current_job_id"] == 9


def test_resident_agent_does_not_run_boss_task_when_login_is_expired() -> None:
    api = ResidentApi()
    executed: list[int] = []
    agent = ResidentAgent(
        AgentSettings(api_key="x", machine_id="mac-a"),
        api,
        run_task=lambda task: executed.append(task["id"]),
        poll_resumes=lambda: None,
        check_login_status=lambda: "expired",
    )

    agent.run_cycle()

    assert api.claimed == []
    assert executed == []
    assert api.heartbeats[0]["boss_login_status"] == "expired"


def test_resident_agent_keeps_heartbeat_fresh_during_a_long_task() -> None:
    api = ResidentApi()
    task_started = Event()

    def run_task(_task) -> None:
        task_started.set()
        deadline = monotonic() + 0.5
        while len(api.heartbeats) < 3 and monotonic() < deadline:
            Event().wait(0.005)

    agent = ResidentAgent(
        AgentSettings(api_key="x", machine_id="mac-a", poll_interval_seconds=0.01),
        api,
        run_task=run_task,
        poll_resumes=lambda: None,
        check_login_status=lambda: "logged_in",
    )

    agent.run_cycle()

    assert task_started.is_set()
    running = [item for item in api.heartbeats if item["status"] == "running"]
    assert len(running) >= 2
    assert all(item["current_task_id"] == 7 for item in running)
    assert all(item["boss_login_status"] == "logged_in" for item in running)


def test_resident_agent_retries_heartbeat_after_a_transient_failure() -> None:
    api = ResidentApi()
    attempts = 0

    def heartbeat(status: str, **payload):
        nonlocal attempts
        if status == "running":
            attempts += 1
            if attempts == 2:
                raise ConnectionError("temporary")
        api.heartbeats.append({"status": status, **payload})
        return {"current_task_id": 7, "current_job_id": 9}

    api.heartbeat = heartbeat

    def run_task(_task) -> None:
        deadline = monotonic() + 0.5
        while attempts < 3 and monotonic() < deadline:
            Event().wait(0.005)

    agent = ResidentAgent(
        AgentSettings(api_key="x", machine_id="mac-a", poll_interval_seconds=0.01),
        api,
        run_task=run_task,
        poll_resumes=lambda: None,
        check_login_status=lambda: "logged_in",
    )

    agent.run_cycle()

    assert attempts >= 3
    assert api.heartbeats[-1]["status"] == "idle"
    assert api.heartbeats[-1]["current_task_id"] is None


def test_resident_agent_resumes_running_task_without_reclaiming() -> None:
    api = ResidentApi(task_status="running")
    executed: list[int] = []
    agent = ResidentAgent(
        AgentSettings(api_key="x", machine_id="mac-a"),
        api,
        run_task=lambda task: executed.append(task["id"]),
        poll_resumes=lambda: None,
        check_login_status=lambda: "logged_in",
    )

    agent.run_cycle()

    assert api.claimed == []
    assert executed == [7]


def test_resident_agent_monitors_resumes_even_without_active_task() -> None:
    api = ResidentApi()
    api.heartbeat = lambda status, **payload: {
        "current_task_id": None,
        "current_job_id": None,
    }
    monitored: list[bool] = []
    agent = ResidentAgent(
        AgentSettings(api_key="x", machine_id="mac-a"),
        api,
        run_task=lambda task: None,
        poll_resumes=lambda: monitored.append(True),
        check_login_status=lambda: "logged_in",
    )

    agent.run_cycle()

    assert monitored == [True]


def test_resident_agent_runs_continuously_at_configured_interval() -> None:
    api = ResidentApi()
    api.heartbeat = lambda status, **payload: {
        "current_task_id": None,
        "current_job_id": None,
    }
    monitored: list[bool] = []
    sleep = Mock()
    agent = ResidentAgent(
        AgentSettings(
            api_key="x",
            machine_id="mac-a",
            poll_interval_seconds=2.5,
        ),
        api,
        run_task=lambda task: None,
        poll_resumes=lambda: monitored.append(True),
        check_login_status=lambda: "logged_in",
        sleep=sleep,
    )

    agent.run_forever(stop_after_cycles=2)

    assert monitored == [True, True]
    sleep.assert_called_once_with(2.5)


class InboxApi:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, int, int]] = []

    def list_resume_inbox(self):
        return [
            {
                "candidate_id": 3,
                "candidate_name": "王五",
                "waiting_jobs": [
                    {"job_id": 9, "job_name": "后端", "contact_event_id": 21},
                    {"job_id": 10, "job_name": "平台", "contact_event_id": 22},
                ],
            }
        ]

    def upload_agent_resume(
        self, path: Path, *, candidate_id: int, contact_event_id: int
    ):
        self.uploads.append((path.name, candidate_id, contact_event_id))
        return {"resume_id": 31, "assignment_status": "pending_job_assignment"}


def test_resume_monitor_uploads_once_and_removes_local_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "王五.pdf"
    pdf.write_bytes(b"%PDF-1.4\nresume\n%%EOF")
    api = InboxApi()
    opened: list[tuple[int, str]] = []

    def download(candidate_id: int, candidate_name: str, boss_id: str) -> Path:
        del boss_id
        opened.append((candidate_id, candidate_name))
        return pdf

    monitor = ResumeMonitor(api, download_attachment=download)

    uploaded = monitor.poll_once()

    assert uploaded == 1
    assert opened == [(3, "王五")]
    assert api.uploads == [("王五.pdf", 3, 21)]
    assert not pdf.exists()
