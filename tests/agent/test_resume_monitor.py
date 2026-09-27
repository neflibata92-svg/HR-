from __future__ import annotations

from pathlib import Path

import pytest

from resume_agent.resume_monitor import ResumeMonitor


class FakeInboxApi:
    def __init__(self, *, waiting_jobs: list[dict[str, object]] | None = None) -> None:
        self.waiting_jobs = waiting_jobs or [
            {"job_id": 9, "job_name": "后端", "contact_event_id": 21}
        ]
        self.uploads: list[tuple[str, int, int]] = []
        self.fail_upload = False

    def list_resume_inbox(self):
        return [
            {
                "candidate_id": 3,
                "candidate_name": "王五",
                "waiting_jobs": self.waiting_jobs,
            }
        ]

    def upload_agent_resume(
        self, path: Path, *, candidate_id: int, contact_event_id: int
    ):
        self.uploads.append((path.name, candidate_id, contact_event_id))
        if self.fail_upload:
            raise RuntimeError("cloud unavailable")
        return {
            "resume_id": 31,
            "assignment_status": "pending_job_assignment"
            if len(self.waiting_jobs) > 1
            else "assigned",
            "job_ids": [item["job_id"] for item in self.waiting_jobs],
        }


def _pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\nresume\n%%EOF")
    return path


def test_upload_failure_keeps_pdf_and_next_poll_reuses_it(tmp_path: Path) -> None:
    api = FakeInboxApi()
    api.fail_upload = True
    pdf = _pdf(tmp_path / "candidate.pdf")
    downloads: list[int] = []

    def download(candidate_id: int, candidate_name: str, boss_id: str) -> Path:
        del candidate_name, boss_id
        downloads.append(candidate_id)
        return pdf

    monitor = ResumeMonitor(api, download_attachment=download)

    assert monitor.poll_once() == 0
    assert pdf.exists()
    api.fail_upload = False
    assert monitor.poll_once() == 1

    assert downloads == [3]
    assert len(api.uploads) == 2
    assert not pdf.exists()


def test_non_pdf_download_is_not_uploaded(tmp_path: Path) -> None:
    api = FakeInboxApi()
    html = tmp_path / "candidate.pdf"
    html.write_text("<html>login page</html>", encoding="utf-8")
    monitor = ResumeMonitor(
        api,
        download_attachment=lambda candidate_id, candidate_name, boss_id: html,
    )

    assert monitor.poll_once() == 0

    assert api.uploads == []
    assert not html.exists()


def test_multiple_waiting_jobs_upload_one_file_for_manual_assignment(
    tmp_path: Path,
) -> None:
    api = FakeInboxApi(
        waiting_jobs=[
            {"job_id": 9, "job_name": "后端", "contact_event_id": 21},
            {"job_id": 10, "job_name": "平台", "contact_event_id": 22},
        ]
    )
    pdf = _pdf(tmp_path / "candidate.pdf")
    monitor = ResumeMonitor(
        api,
        download_attachment=lambda candidate_id, candidate_name, boss_id: pdf,
    )

    assert monitor.poll_once() == 1

    assert api.uploads == [("candidate.pdf", 3, 21)]


@pytest.mark.parametrize("task_status", ["paused", "completed", "cancelled"])
def test_terminal_or_paused_task_does_not_block_resume_polling(task_status: str) -> None:
    from resume_agent.config import AgentSettings
    from resume_agent.resident import ResidentAgent

    class Api:
        def heartbeat(self, status: str, **payload):
            return {"current_task_id": 7, "current_job_id": 9}

        def get_task(self, task_id: int):
            return {"id": task_id, "job_id": 9, "status": task_status}

    polled: list[bool] = []
    ResidentAgent(
        AgentSettings(api_key="x", machine_id="mac-a"),
        Api(),
        run_task=lambda task: pytest.fail("inactive task must not run"),
        poll_resumes=lambda: polled.append(True),
        check_login_status=lambda: "logged_in",
    ).run_cycle()

    assert polled == [True]
