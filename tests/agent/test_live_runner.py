from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import Mock, patch

import httpx

from resume_agent.boss_live import PageStateError
from resume_agent.config import AgentSettings
from resume_agent import live_runner
from resume_agent.live_runner import run_live_round


@contextmanager
def _context(page):
    yield Mock(pages=[page])


def test_login_probe_reports_real_profile_state() -> None:
    page = Mock(url="https://www.zhipin.com/web/chat/recommend")
    session = Mock()
    with (
        patch("resume_agent.live_runner.open_persistent_browser", return_value=_context(page)),
        patch("resume_agent.live_runner.BossLiveSession", return_value=session),
    ):
        status = live_runner.check_boss_login_status(AgentSettings(api_key="x"), Mock())

    assert status == "logged_in"
    session.goto.assert_called_once()
    session.ensure_task_page.assert_called_once()


def test_login_probe_keeps_non_login_page_errors_unknown() -> None:
    page = Mock(url="https://www.zhipin.com/web/chat/recommend")
    session = Mock()
    session.goto.side_effect = PageStateError("captcha")
    with (
        patch("resume_agent.live_runner.open_persistent_browser", return_value=_context(page)),
        patch("resume_agent.live_runner.BossLiveSession", return_value=session),
    ):
        status = live_runner.check_boss_login_status(AgentSettings(api_key="x"), Mock())

    assert status == "unknown"


def test_live_runner_marks_login_redirect_as_expired() -> None:
    api = Mock()
    task = {
        "id": 7,
        "job_id": 9,
        "requested_count": 1,
        "boss_entry_url": "https://www.zhipin.com/web/geek/job?query=python",
    }
    api.get_task.return_value = task
    api.claim_task.return_value = task
    page = Mock(url="https://www.zhipin.com/login")
    session = Mock()
    session.goto.side_effect = PageStateError("login_required")
    with (
        patch("resume_agent.live_runner.open_persistent_browser", return_value=_context(page)),
        patch("resume_agent.live_runner.BossLiveSession", return_value=session),
    ):
        code = live_runner.run_live_round(AgentSettings(api_key="x"), api, api, task_id=7)

    assert code == 3
    api.claim_task.assert_not_called()
    api.pause_task.assert_not_called()
    api.acknowledge_control.assert_not_called()
    assert any(
        call.kwargs.get("boss_login_status") == "expired"
        for call in api.heartbeat.call_args_list
    )
    assert not any(
        call.kwargs.get("boss_login_status") == "logged_in"
        for call in api.heartbeat.call_args_list
    )


def test_live_runner_claims_explicit_task_and_navigates_to_job_entry() -> None:
    api = Mock()
    task = {
        "id": 7,
        "job_id": 9,
        "requested_count": 1,
        "jd_text_snapshot": "Python",
        "score_threshold_snapshot": 80,
        "greet_template_snapshot": "您好",
        "critical_fields": [{"key": "degree", "label": "学历"}],
        "boss_entry_url": "https://www.zhipin.com/web/geek/job?query=python",
    }
    api.get_task.return_value = task
    api.claim_task.return_value = task
    page = Mock(url="https://www.zhipin.com/web/chat/recommend")
    session = Mock()
    session.extract_candidates.return_value = []

    with (
        patch("resume_agent.live_runner.open_persistent_browser", return_value=_context(page)),
        patch("resume_agent.live_runner.BossLiveSession", return_value=session),
    ):
        code = run_live_round(AgentSettings(api_key="x"), api, api, task_id=7)

    assert code == 4
    api.claim_task.assert_called_once_with(7)
    session.goto.assert_called_once_with(
        "https://www.zhipin.com/web/geek/job?query=python"
    )
    session.extract_candidates.assert_called_once_with(limit=1)
    api.pause_task.assert_called_once_with(7, "no_cards")
    api.acknowledge_control.assert_called_once_with(7)


def test_live_runner_stops_before_browser_when_api_is_unreachable() -> None:
    api = Mock()
    api.heartbeat.side_effect = httpx.ConnectError("offline")
    with patch("resume_agent.live_runner.open_persistent_browser") as browser:
        code = run_live_round(AgentSettings(api_key="x"), api, api, task_id=7)
    assert code == 2
    browser.assert_not_called()
