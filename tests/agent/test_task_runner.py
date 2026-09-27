from __future__ import annotations

import pytest

from resume_domain.llm_schema import LlmScoreResult
from resume_agent.config import AgentSettings
from resume_agent.parse_page import RawCandidate
from resume_agent.runner import run_task_candidates


TERMINAL = {"needs_review", "below_threshold", "contacted", "duplicate_contact", "failed"}


class FakeApi:
    def __init__(self, *, greet_verified: bool = True, existing_status: str = "discovered") -> None:
        self.greet_verified = greet_verified
        self.existing_status = existing_status
        self.items = []
        self.completed_items = []
        self.failed_items = []
        self.completed_tasks = []
        self.scored = 0
        self.confirmed = []
        self.failed_outreach = []
        self.task_statuses = ["running"]
        self.control_acks = []

    def get_task(self, task_id):
        status = self.task_statuses.pop(0) if len(self.task_statuses) > 1 else self.task_statuses[0]
        return {"id": task_id, "status": status}

    def acknowledge_control(self, task_id):
        self.control_acks.append(task_id)
        return {"id": task_id, "status": "paused"}

    def upsert_candidate(self, payload):
        return {"id": len(self.items) + 1}

    def create_task_item(self, task_id, *, candidate_id, position_index):
        item = {"id": position_index, "candidate_id": candidate_id, "status": self.existing_status}
        self.items.append(item)
        return item

    def exchange_blocked(self, candidate_id):
        return False

    def score_candidate(self, jd, summary, *, threshold):
        self.scored += 1
        return LlmScoreResult(
            score=90,
            reason="匹配",
            evidence=["Python"],
            missing_fields=["期望薪资"],
            estimated_fields=["期望薪资"],
            critical_fields=[],
            confidence=0.9,
            decision="eligible",
            model="server-model",
        )

    def post_score(self, payload):
        assert payload["task_id"] == 7
        assert payload["estimated_fields"] == ["期望薪资"]
        return {"id": 30 + self.scored}

    def reserve_outreach(self, candidate_id, job_id, *, task_id, message):
        return {"id": 40 + candidate_id, "status": "sending"}

    def confirm_outreach(self, event_id):
        self.confirmed.append(event_id)

    def fail_outreach(self, event_id, reason):
        self.failed_outreach.append((event_id, reason))

    def complete_task_item(self, task_id, item_id, **payload):
        self.completed_items.append((item_id, payload))

    def fail_task_item(self, task_id, item_id, *, failure_code, failure_detail=""):
        self.failed_items.append((item_id, failure_code))

    def complete_task(self, task_id):
        self.completed_tasks.append(task_id)


class FakeGreeter:
    def __init__(self, verified: bool = True) -> None:
        self.verified = verified
        self.calls = 0

    def greet(self, candidate, message):
        self.calls += 1
        return self.verified


def _task(requested_count: int) -> dict:
    return {
        "id": 7,
        "job_id": 9,
        "requested_count": requested_count,
        "jd_text_snapshot": "Python",
        "score_threshold_snapshot": 80,
        "greet_template_snapshot": "您好 {{candidate_name}}",
        "critical_fields": [],
    }


def _candidates(count: int) -> list[RawCandidate]:
    return [RawCandidate(f"boss-{i}", f"候选人{i}", f"公司{i}", 30, 4, 2, 4) for i in range(count)]


def test_runner_processes_exact_requested_count_and_completes() -> None:
    api = FakeApi()
    processed = run_task_candidates(
        settings=AgentSettings(api_key="x", machine_id="mac-a"),
        api=api,
        task=_task(1),
        candidates=_candidates(3),
        greeter=FakeGreeter(),
    )
    assert processed == 1
    assert len(api.items) == 1
    assert api.completed_tasks == [7]
    assert api.completed_items[0][1]["status"] == "contacted"


def test_runner_completes_with_actual_count_when_page_is_short() -> None:
    api = FakeApi()
    processed = run_task_candidates(
        settings=AgentSettings(api_key="x", machine_id="mac-a"),
        api=api,
        task=_task(50),
        candidates=_candidates(3),
        greeter=FakeGreeter(),
    )
    assert processed == 3
    assert len(api.items) == 3
    assert api.completed_tasks == [7]


def test_runner_skips_terminal_item_during_resume() -> None:
    api = FakeApi(existing_status="contacted")
    greeter = FakeGreeter()
    processed = run_task_candidates(
        settings=AgentSettings(api_key="x", machine_id="mac-a"),
        api=api,
        task=_task(1),
        candidates=_candidates(1),
        greeter=greeter,
    )
    assert processed == 1
    assert api.scored == 0
    assert greeter.calls == 0


def test_runner_does_not_confirm_when_message_is_not_verified() -> None:
    api = FakeApi()
    greeter = FakeGreeter(verified=False)
    run_task_candidates(
        settings=AgentSettings(api_key="x", machine_id="mac-a"),
        api=api,
        task=_task(1),
        candidates=_candidates(1),
        greeter=greeter,
    )
    assert api.confirmed == []
    assert api.failed_outreach == [(41, "message_not_verified")]
    assert api.failed_items == [(1, "message_not_verified")]


def test_runner_stops_and_leaves_item_unfinished_on_scoring_api_error() -> None:
    api = FakeApi()

    def fail_score(*args, **kwargs):
        raise RuntimeError("api offline")

    api.score_candidate = fail_score
    with pytest.raises(RuntimeError, match="api offline"):
        run_task_candidates(
            settings=AgentSettings(api_key="x", machine_id="mac-a"),
            api=api,
            task=_task(2),
            candidates=_candidates(2),
            greeter=FakeGreeter(),
        )

    assert len(api.items) == 1
    assert api.failed_items == []
    assert api.completed_tasks == []


def test_runner_stops_before_next_candidate_and_acknowledges_pause() -> None:
    api = FakeApi()
    api.task_statuses = ["running", "pausing"]
    greeter = FakeGreeter()

    processed = run_task_candidates(
        settings=AgentSettings(api_key="x", machine_id="mac-a"),
        api=api,
        task=_task(2),
        candidates=_candidates(2),
        greeter=greeter,
    )

    assert processed == 0
    assert api.items == []
    assert api.scored == 0
    assert greeter.calls == 0
    assert api.control_acks == [7]
    assert api.completed_tasks == []


def test_runner_checks_control_before_reserving_or_sending_outreach() -> None:
    class PauseBeforeReserveApi(FakeApi):
        def __init__(self) -> None:
            super().__init__()
            self.control_checks = 0

        def get_task(self, task_id):
            self.control_checks += 1
            status = "pausing" if self.control_checks >= 3 else "running"
            return {"id": task_id, "status": status}

    api = PauseBeforeReserveApi()
    greeter = FakeGreeter()

    processed = run_task_candidates(
        settings=AgentSettings(api_key="x", machine_id="mac-a"),
        api=api,
        task=_task(1),
        candidates=_candidates(1),
        greeter=greeter,
    )

    assert processed == 0
    assert api.scored == 0
    assert greeter.calls == 0
    assert api.confirmed == []
    assert api.control_acks == [7]
    assert api.completed_tasks == []
