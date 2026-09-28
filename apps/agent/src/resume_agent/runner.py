"""一轮筛选的共享执行逻辑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from resume_domain.fingerprint import candidate_fingerprint
from resume_agent.api_client import ApiClient
from resume_agent.config import AgentSettings
from resume_agent.parse_page import RawCandidate, parse_list_html, detect_risk_page
from resume_agent.pipeline import Scorer, SendOutcomeUnknown, process_candidate
from resume_agent.rate_limit import sleep_action_delay


class TaskControlStop(RuntimeError):
    """服务端已要求暂停或终止当前任务。"""


def _ensure_task_running(api: ApiClient, task_id: int) -> None:
    status = str(api.get_task(task_id).get("status") or "")
    if status in {"pausing", "cancelling"}:
        api.acknowledge_control(task_id)
        raise TaskControlStop(status)
    if status not in {"ready", "running"}:
        raise TaskControlStop(status)


class TaskGreeter:
    def __init__(
        self,
        api: ApiClient,
        *,
        task_id: int,
        job_id: int,
        candidate_id: int,
        task_item_id: int,
        greet_fn: Any,
    ) -> None:
        self.api = api
        self.task_id = task_id
        self.job_id = job_id
        self.candidate_id = candidate_id
        self.task_item_id = task_item_id
        self.greet_fn = greet_fn
        self.event_id: int | None = None
        self.outcome_unknown = False

    def greet(self, candidate: RawCandidate, message: str) -> bool:
        _ensure_task_running(self.api, self.task_id)
        event = self.api.reserve_outreach(
            self.candidate_id,
            self.job_id,
            task_id=self.task_id,
            task_item_id=self.task_item_id,
            message=message,
        )
        self.event_id = int(event["id"])
        if event.get("idempotent_hit"):
            if event.get("status") == "confirmed":
                return True
            if event.get("status") in {"sending", "unknown"}:
                self.outcome_unknown = True
                self.api.unknown_outreach(self.event_id, "existing_reservation_retry")
            return False
        try:
            _ensure_task_running(self.api, self.task_id)
        except TaskControlStop:
            self.api.fail_outreach(self.event_id, "task_control_requested")
            raise
        try:
            outcome = self.greet_fn(candidate, message)
        except SendOutcomeUnknown:
            self.api.unknown_outreach(self.event_id, "send_result_unknown")
            self.outcome_unknown = True
            return False
        except Exception:
            self.api.fail_outreach(self.event_id, "greet_failed_before_send")
            raise
        if outcome is None:
            self.api.unknown_outreach(self.event_id, "send_result_unknown")
            self.outcome_unknown = True
            return False
        if outcome:
            self.api.confirm_outreach(self.event_id)
        else:
            self.api.fail_outreach(self.event_id, "send_not_started")
        return bool(outcome)


def _render_greeting(template: str, candidate: RawCandidate, task: dict[str, Any]) -> str:
    return (
        template.replace("{{candidate_name}}", candidate.name)
        .replace("{{ candidate_name }}", candidate.name)
        .replace("{{job_name}}", str(task.get("job_name_snapshot") or ""))
        .replace("{{ job_name }}", str(task.get("job_name_snapshot") or ""))
    )


def run_task_candidates(
    *,
    settings: AgentSettings,
    api: ApiClient,
    task: dict[str, Any],
    candidates: list[RawCandidate],
    greeter: Any,
) -> int:
    """按服务端任务快照处理当前页候选人。"""

    del settings
    requested = int(task["requested_count"])
    selected = candidates[:requested]
    terminal = {"needs_review", "below_threshold", "contacted", "duplicate_contact", "failed"}
    task_id = int(task["id"])
    completed_count = 0
    try:
        _ensure_task_running(api, task_id)
        for position, raw in enumerate(selected, start=1):
            _ensure_task_running(api, task_id)
            fingerprint = candidate_fingerprint(raw.name, raw.org or raw.boss_id or "unknown")
            candidate = api.upsert_candidate(
                {
                    "boss_id": raw.boss_id or None,
                    "fingerprint": fingerprint,
                    "name": raw.name,
                    "age": raw.age,
                    "years_of_experience": raw.years,
                    "job_segments_json": "[]",
                    "source": "boss",
                }
            )
            item = api.create_task_item(
                task_id,
                candidate_id=int(candidate["id"]),
                position_index=position,
            )
            if item.get("status") in terminal:
                completed_count += 1
                continue

            _ensure_task_running(api, task_id)
            message = _render_greeting(str(task["greet_template_snapshot"]), raw, task)
            task_greeter = TaskGreeter(
                api,
                task_id=task_id,
                job_id=int(task["job_id"]),
                candidate_id=int(candidate["id"]),
                task_item_id=int(item["id"]),
                greet_fn=greeter.greet,
            )
            result = process_candidate(
                raw,
                jd_text=str(task["jd_text_snapshot"]),
                threshold=int(task["score_threshold_snapshot"]),
                greet_template=message,
                exchanged_within_30_days=api.exchange_blocked(int(candidate["id"])),
                already_greeted=False,
                scorer=api,
                greeter=task_greeter,
            )
            if result.action == "score_error":
                raise RuntimeError(";".join(result.reasons))
            score_event = api.post_score(
                {
                    "candidate_id": candidate["id"],
                    "job_id": task["job_id"],
                    "candidate_job_id": item.get("candidate_job_id"),
                    "task_id": task_id,
                    "hard_filter_passed": result.action != "hard_filter_reject",
                    "hard_filter_reasons": result.reasons
                    if result.action == "hard_filter_reject"
                    else [],
                    "score": result.score,
                    "reason": ";".join(result.reasons),
                    "evidence": result.evidence or [],
                    "missing_fields": result.missing_fields or [],
                    "estimated_fields": result.estimated_fields or [],
                    "critical_fields": result.critical_fields or [],
                    "confidence": result.confidence,
                    "decision": result.action
                    if result.action in {"needs_review", "below_threshold"}
                    else "eligible"
                    if result.action == "greeted"
                    else "needs_review"
                    if result.action == "greet_failed" and task_greeter.outcome_unknown
                    else "eligible"
                    if result.action == "greet_failed"
                    else "error",
                    "model": result.model,
                }
            )
            if result.action == "greet_failed":
                if task_greeter.outcome_unknown:
                    api.complete_task_item(
                        task_id,
                        int(item["id"]),
                        status="needs_review",
                        score_event_id=int(score_event["id"]),
                        outreach_event_id=task_greeter.event_id,
                    )
                    completed_count += 1
                    continue
                api.fail_task_item(
                    task_id,
                    int(item["id"]),
                    failure_code="message_not_verified",
                    failure_detail=";".join(result.reasons),
                )
                completed_count += 1
                continue
            if result.action in {"hard_filter_reject", "score_error"}:
                api.fail_task_item(
                    task_id,
                    int(item["id"]),
                    failure_code=result.action,
                    failure_detail=";".join(result.reasons),
                )
                completed_count += 1
                continue
            status = "contacted" if result.action == "greeted" else result.action
            api.complete_task_item(
                task_id,
                int(item["id"]),
                status=status,
                score_event_id=int(score_event["id"]),
                outreach_event_id=task_greeter.event_id,
            )
            completed_count += 1
    except TaskControlStop:
        return completed_count

    api.complete_task(task_id)
    return completed_count


class PipelineGreeter:
    def __init__(self, greet_fn: Any) -> None:
        self._greet_fn = greet_fn
        self.last_ok = False

    def greet(self, candidate: RawCandidate, message: str) -> bool:
        self.last_ok = bool(self._greet_fn(candidate, message))
        return self.last_ok


def process_job_candidates(
    *,
    settings: AgentSettings,
    api: ApiClient,
    scorer: Scorer,
    job: dict[str, Any],
    candidates: list[RawCandidate],
    greeter: PipelineGreeter | None = None,
    on_greeted: Any | None = None,
) -> int:
    """处理一批候选人，返回处理人数。"""

    hourly_limit = int(job.get("hourly_greet_limit") or 20)
    greeted_count = 0

    for raw in candidates:
        fingerprint = candidate_fingerprint(raw.name, raw.org or raw.boss_id or "unknown")
        upserted = api.upsert_candidate(
            {
                "boss_id": raw.boss_id or None,
                "fingerprint": fingerprint,
                "name": raw.name,
                "age": raw.age,
                "years_of_experience": raw.years,
                "job_segments_json": "[]",
                "source": "boss",
            }
        )
        already = api.outreach_exists(job["id"], upserted["id"])
        blocked = api.exchange_blocked(upserted["id"])
        result = process_candidate(
            raw,
            jd_text=job["jd_text"],
            threshold=int(job["score_threshold"]),
            greet_template=job["greet_template"],
            exchanged_within_30_days=blocked,
            already_greeted=already,
            scorer=scorer,
            greeter=greeter,
        )
        api.post_score(
            {
                "candidate_id": upserted["id"],
                "job_id": job["id"],
                "hard_filter_passed": result.action != "hard_filter_reject",
                "hard_filter_reasons": result.reasons
                if result.action == "hard_filter_reject"
                else [],
                "score": result.score,
                "reason": ";".join(result.reasons),
                "model": result.model,
            }
        )
        if result.action == "greeted":
            api.post_outreach(
                {
                    "candidate_id": upserted["id"],
                    "job_id": job["id"],
                    "greeted": True,
                }
            )
            greeted_count += 1
            if on_greeted is not None:
                on_greeted(raw, upserted)
            if greeted_count >= hourly_limit:
                print(f"已达本轮招呼上限 {hourly_limit}，停止")
                break
        print(f"{raw.name}: {result.action} score={result.score} reasons={result.reasons}")
        sleep_action_delay(
            int(job.get("min_action_delay_ms") or 1500),
            int(job.get("max_action_delay_ms") or 4000),
        )
    return len(candidates)


def run_fixture_round(
    settings: AgentSettings,
    api: ApiClient,
    scorer: Scorer,
    fixture: Path,
) -> int:
    html = fixture.read_text(encoding="utf-8")
    if detect_risk_page(html):
        api.heartbeat("paused", last_error="risk_page_detected")
        print("检测到风控/验证码页，已停机")
        return 3
    jobs = api.list_enabled_jobs()
    if not jobs:
        print("无启用岗位")
        api.heartbeat("idle")
        return 0
    process_job_candidates(
        settings=settings,
        api=api,
        scorer=scorer,
        job=jobs[0],
        candidates=parse_list_html(html),
        greeter=None,
    )
    api.heartbeat("idle")
    return 0
