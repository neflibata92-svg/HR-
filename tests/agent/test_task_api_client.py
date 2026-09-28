from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings


def _client() -> ApiClient:
    return ApiClient(
        AgentSettings(
            api_base_url="https://backend.example",
            api_key="agent-key",
            machine_id="mac-a",
        )
    )


def _response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def test_task_api_client_uses_machine_and_task_endpoints() -> None:
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.side_effect = [
        _response({"id": 7, "status": "running"}),
        _response({"id": 11, "status": "discovered"}),
        _response({"id": 11, "status": "below_threshold"}),
        _response({"id": 7, "status": "completed"}),
    ]

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        api = _client()
        assert api.claim_task(7)["id"] == 7
        api.create_task_item(7, candidate_id=3, position_index=1)
        api.complete_task_item(7, 11, status="below_threshold", score_event_id=5)
        api.complete_task(7)

    calls = http_client.post.call_args_list
    assert calls[0].args[0].endswith("/api/screening-tasks/7/claim")
    assert calls[0].kwargs["json"] == {"machine_id": "mac-a"}
    assert calls[1].kwargs["json"]["machine_id"] == "mac-a"
    assert calls[2].kwargs["json"] == {
        "machine_id": "mac-a",
        "status": "below_threshold",
        "score_event_id": 5,
        "outreach_event_id": None,
    }
    assert calls[3].args[0].endswith("/api/screening-tasks/7/complete")


def test_outreach_api_client_supports_two_phase_confirmation() -> None:
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.side_effect = [
        _response({"id": 21, "status": "sending"}),
        _response({"id": 21, "status": "confirmed"}),
        _response({"id": 22, "status": "failed"}),
        _response({"id": 23, "status": "unknown"}),
    ]

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        api = _client()
        event = api.reserve_outreach(3, 4, task_id=7, task_item_id=11, message="您好")
        api.confirm_outreach(event["id"])
        api.fail_outreach(22, "message_not_verified")
        api.unknown_outreach(23, "send_result_unknown")

    calls = http_client.post.call_args_list
    assert calls[0].args[0].endswith("/api/outreach/reservations")
    assert calls[0].kwargs["json"] == {
        "candidate_id": 3,
        "job_id": 4,
        "task_id": 7,
        "task_item_id": 11,
        "message": "您好",
    }
    assert calls[1].args[0].endswith("/api/outreach/21/confirm")
    assert calls[2].kwargs["json"] == {"reason": "message_not_verified"}
    assert calls[3].args[0].endswith("/api/outreach/23/unknown")
    assert calls[3].kwargs["json"] == {"reason": "send_result_unknown"}


def test_outreach_reservation_retry_reuses_task_item_id_after_timeout() -> None:
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.side_effect = [
        httpx.ReadTimeout("response timed out"),
        _response({"id": 21, "status": "sending"}),
    ]

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        api = _client()
        with pytest.raises(httpx.ReadTimeout):
            api.reserve_outreach(3, 4, task_id=7, task_item_id=11, message="您好")
        event = api.reserve_outreach(3, 4, task_id=7, task_item_id=11, message="您好")

    assert event["id"] == 21
    assert http_client.post.call_count == 2
    payloads = [call.kwargs["json"] for call in http_client.post.call_args_list]
    assert payloads[0] == payloads[1]
    assert payloads[0]["task_item_id"] == 11


def test_agent_api_client_uses_explicit_assignment_and_control_endpoints() -> None:
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.side_effect = [
        _response({"id": 5, "current_task_id": 7}),
        _response({"id": 7, "status": "running"}),
        _response({"id": 7, "status": "paused"}),
    ]
    http_client.get.return_value = _response({"id": 7, "status": "ready"})

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        api = _client()
        run = api.heartbeat(
            "running",
            availability="busy",
            current_task_id=7,
            current_job_id=9,
            boss_login_status="logged_in",
        )
        task = api.get_task(7)
        claimed = api.claim_task(7)
        paused = api.acknowledge_control(7)

    assert run["current_task_id"] == 7
    assert task["id"] == claimed["id"] == paused["id"] == 7
    assert http_client.post.call_args_list[0].kwargs["json"] == {
        "machine_id": "mac-a",
        "status": "running",
        "availability": "busy",
        "current_task_id": 7,
        "current_job_id": 9,
        "boss_login_status": "logged_in",
        "last_error": "",
    }
    assert http_client.get.call_args.args[0].endswith("/api/screening-tasks/7")
    assert http_client.post.call_args_list[1].args[0].endswith(
        "/api/screening-tasks/7/claim"
    )
    assert http_client.post.call_args_list[2].args[0].endswith(
        "/api/screening-tasks/7/control/ack"
    )


def test_agent_heartbeat_distinguishes_omitted_and_cleared_assignment() -> None:
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.post.side_effect = [
        _response({"id": 5, "current_task_id": 7}),
        _response({"id": 5, "current_task_id": None}),
    ]

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client) as client_factory:
        api = _client()
        api.heartbeat("idle", availability="idle", boss_login_status="logged_in")
        api.heartbeat(
            "idle",
            availability="idle",
            current_task_id=None,
            current_job_id=None,
            boss_login_status="logged_in",
        )

    initial = http_client.post.call_args_list[0].kwargs["json"]
    cleared = http_client.post.call_args_list[1].kwargs["json"]
    assert "current_task_id" not in initial
    assert "current_job_id" not in initial
    assert cleared["current_task_id"] is None
    assert cleared["current_job_id"] is None
    assert client_factory.call_args_list[0].kwargs["timeout"] <= 10.0


def test_agent_api_client_lists_inbox_and_uploads_pdf(tmp_path: Path) -> None:
    resume = tmp_path / "candidate.pdf"
    resume.write_bytes(b"%PDF-1.4\nresume\n%%EOF")
    http_client = Mock()
    http_client.__enter__ = Mock(return_value=http_client)
    http_client.__exit__ = Mock(return_value=False)
    http_client.get.return_value = _response(
        [
            {
                "candidate_id": 3,
                "candidate_name": "王五",
                "waiting_jobs": [
                    {"job_id": 9, "job_name": "后端", "contact_event_id": 21}
                ],
            }
        ]
    )
    http_client.post.return_value = _response(
        {
            "resume_id": 31,
            "candidate_id": 3,
            "assignment_status": "assigned",
            "job_ids": [9],
            "idempotent_hit": False,
        }
    )

    with patch("resume_agent.api_client.httpx.Client", return_value=http_client):
        api = _client()
        inbox = api.list_resume_inbox()
        result = api.upload_agent_resume(
            resume, candidate_id=3, contact_event_id=21
        )

    assert inbox[0]["candidate_name"] == "王五"
    assert result["resume_id"] == 31
    assert http_client.get.call_args.args[0].endswith("/api/candidates/resume-inbox")
    upload = http_client.post.call_args
    assert upload.args[0].endswith("/api/resumes/agent-upload")
    assert upload.kwargs["data"] == {
        "candidate_id": "3",
        "contact_event_id": "21",
    }
    assert upload.kwargs["files"]["file"][0] == "candidate.pdf"
