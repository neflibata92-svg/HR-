"""筛选任务状态机、领取与任务项服务。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_api.models import (
    AgentRun,
    Candidate,
    CandidateJob,
    JobPosting,
    OutreachEvent,
    ScoreEvent,
    ScreeningRecord,
    ScreeningTask,
    ScreeningTaskItem,
)
from resume_api.schemas import ScreeningTaskCreate
from resume_api.services import jobs as jobs_service


class ScreeningTaskError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _require_assignable_agent(agent: AgentRun) -> None:
    if agent.availability != "idle" or agent.current_task_id is not None:
        raise ScreeningTaskError(409, "assigned agent is not idle")
    if agent.boss_login_status != "logged_in":
        raise ScreeningTaskError(409, "assigned agent is not logged in")
    heartbeat = agent.last_heartbeat
    if heartbeat is None:
        raise ScreeningTaskError(409, "assigned agent is offline")
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    if heartbeat < datetime.now(timezone.utc) - timedelta(seconds=45):
        raise ScreeningTaskError(409, "assigned agent is offline")


def create_task(db: Session, payload: ScreeningTaskCreate, *, user_id: int) -> ScreeningTask:
    job = db.get(JobPosting, payload.job_id)
    if job is None:
        raise ScreeningTaskError(404, "job not found")
    if not job.enabled:
        raise ScreeningTaskError(409, "job is disabled")

    uses_job_defaults = payload.requested_count is None
    assigned_agent: AgentRun | None = None
    if uses_job_defaults:
        readiness = jobs_service.readiness(job)
        if not readiness["ready"]:
            missing = ", ".join(readiness["missing"])
            raise ScreeningTaskError(409, f"job configuration incomplete: {missing}")
        if payload.assigned_agent_run_id is None:
            raise ScreeningTaskError(422, "assigned_agent_run_id is required")
        assigned_agent = db.scalar(
            select(AgentRun)
            .where(
                AgentRun.id == payload.assigned_agent_run_id,
                AgentRun.owner_user_id == user_id,
            )
            .with_for_update()
        )
        if assigned_agent is None:
            raise ScreeningTaskError(409, "assigned agent is unavailable")
        _require_assignable_agent(assigned_agent)
    elif payload.assigned_agent_run_id is not None:
        assigned_agent = db.scalar(
            select(AgentRun)
            .where(
                AgentRun.id == payload.assigned_agent_run_id,
                AgentRun.owner_user_id == user_id,
            )
            .with_for_update()
        )
        if assigned_agent is None:
            raise ScreeningTaskError(409, "assigned agent is unavailable")
        _require_assignable_agent(assigned_agent)

    requested_count = job.default_requested_count if uses_job_defaults else payload.requested_count
    critical_fields = []
    critical_fields_source: dict[str, object] = {"source": "jd"}

    task = ScreeningTask(
        job_id=job.id,
        created_by_user_id=user_id,
        machine_id=assigned_agent.machine_id if assigned_agent is not None else None,
        assigned_agent_run_id=assigned_agent.id if assigned_agent is not None else None,
        active_job_guard=job.id,
        requested_count=requested_count,
        critical_fields_json=json.dumps(
            [item.model_dump() for item in critical_fields], ensure_ascii=False
        ),
        critical_fields_source_json=json.dumps(
            critical_fields_source, ensure_ascii=False
        ),
        job_name_snapshot=job.name,
        jd_text_snapshot=job.jd_text,
        score_threshold_snapshot=job.score_threshold,
        greet_template_snapshot=job.greet_template,
        boss_entry_url_snapshot=job.boss_entry_url,
        status="ready",
    )
    db.add(task)
    try:
        db.flush()
        if assigned_agent is not None:
            assigned_agent.status = "assigned"
            assigned_agent.availability = "busy"
            assigned_agent.current_task_id = task.id
            assigned_agent.current_job_id = task.job_id
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ScreeningTaskError(409, "job already has an active task") from exc
    db.refresh(task)
    return task


def get_task(db: Session, task_id: int) -> ScreeningTask:
    task = db.get(ScreeningTask, task_id)
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    return task


def require_task_access(
    db: Session,
    task_id: int,
    *,
    actor_user_id: int,
    actor_role: str,
) -> ScreeningTask:
    task = get_task(db, task_id)
    if actor_role != "admin" and task.created_by_user_id != actor_user_id:
        raise ScreeningTaskError(404, "screening task not found")
    return task


def claim_task(
    db: Session,
    *,
    machine_id: str,
    actor_user_id: int,
    actor_role: str,
    task_id: int | None = None,
) -> ScreeningTask:
    recovery = select(ScreeningTask).where(
        ScreeningTask.status == "running",
        ScreeningTask.machine_id == machine_id,
    )
    if actor_role != "admin":
        recovery = recovery.where(ScreeningTask.created_by_user_id == actor_user_id)
    if task_id is not None:
        require_task_access(
            db,
            task_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        recovery = recovery.where(ScreeningTask.id == task_id)
    task = db.scalar(recovery.order_by(ScreeningTask.id).with_for_update())
    if task is not None:
        return task

    query = select(ScreeningTask).where(ScreeningTask.status == "ready")
    if actor_role != "admin":
        query = query.where(ScreeningTask.created_by_user_id == actor_user_id)
    if task_id is not None:
        query = query.where(ScreeningTask.id == task_id)
    task = db.scalar(query.order_by(ScreeningTask.id).with_for_update())
    if task is None:
        if task_id is not None and db.get(ScreeningTask, task_id) is None:
            raise ScreeningTaskError(404, "screening task not found")
        raise ScreeningTaskError(409, "screening task cannot be claimed")
    if task.machine_id is not None and task.machine_id != machine_id:
        raise ScreeningTaskError(409, "task is assigned to another machine")
    if task.assigned_agent_run_id is not None:
        agent = db.scalar(
            select(AgentRun)
            .where(AgentRun.id == task.assigned_agent_run_id)
            .with_for_update()
        )
        if agent is None or agent.machine_id != machine_id:
            raise ScreeningTaskError(409, "assigned agent is unavailable")
        if agent.owner_user_id != task.created_by_user_id:
            raise ScreeningTaskError(409, "assigned agent belongs to another user")
        if agent.availability not in {"idle", "busy"}:
            raise ScreeningTaskError(409, "assigned agent is unavailable")
        agent.status = "running"
        agent.availability = "busy"
        agent.current_task_id = task.id
        agent.current_job_id = task.job_id
    task.machine_id = machine_id
    task.status = "running"
    task.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(task)
    return task


def transition(
    db: Session,
    task_id: int,
    action: str,
    *,
    pause_reason: str = "",
) -> ScreeningTask:
    task = db.scalar(
        select(ScreeningTask).where(ScreeningTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    allowed = {
        "pause": ({"running"}, "pausing"),
        "resume": ({"paused"}, "running"),
        "cancel": ({"ready", "running", "paused"}, "cancelling"),
    }
    sources, target = allowed[action]
    if task.status not in sources:
        raise ScreeningTaskError(409, "invalid task state transition")
    if action == "cancel" and task.status == "ready":
        task.status = "cancelled"
        task.finished_at = datetime.now(timezone.utc)
        task.control_requested_at = None
        _release_task_resources(db, task)
        db.commit()
        db.refresh(task)
        return task
    task.status = target
    task.pause_reason = pause_reason if action == "pause" else ""
    task.control_requested_at = (
        datetime.now(timezone.utc) if target in {"pausing", "cancelling"} else None
    )
    db.commit()
    db.refresh(task)
    return task


def acknowledge_control(
    db: Session, task_id: int, *, machine_id: str
) -> ScreeningTask:
    task = db.scalar(
        select(ScreeningTask).where(ScreeningTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    if task.machine_id != machine_id:
        raise ScreeningTaskError(409, "task is not owned by this machine")
    if task.status == "pausing":
        task.status = "paused"
        task.control_requested_at = None
    elif task.status == "cancelling":
        task.status = "cancelled"
        task.control_requested_at = None
        task.finished_at = datetime.now(timezone.utc)
        _release_task_resources(db, task)
    else:
        raise ScreeningTaskError(409, "task has no pending control request")
    db.commit()
    db.refresh(task)
    return task


def _release_task_resources(db: Session, task: ScreeningTask) -> None:
    task.active_job_guard = None
    if task.assigned_agent_run_id is None:
        return
    agent = db.get(AgentRun, task.assigned_agent_run_id)
    if agent is None or agent.current_task_id != task.id:
        return
    agent.status = "idle"
    agent.availability = "idle"
    agent.current_task_id = None
    agent.current_job_id = None


def complete_task(db: Session, task_id: int, *, machine_id: str) -> ScreeningTask:
    task = db.scalar(
        select(ScreeningTask).where(ScreeningTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    if task.status == "completed" and task.machine_id == machine_id:
        return task
    _require_owner(task, machine_id)
    unfinished_count = db.scalar(
        select(func.count(ScreeningTaskItem.id)).where(
            ScreeningTaskItem.task_id == task_id,
            ScreeningTaskItem.status.not_in(
                {"needs_review", "below_threshold", "contacted", "duplicate_contact", "failed"}
            ),
        )
    ) or 0
    if unfinished_count:
        raise ScreeningTaskError(409, "task has unfinished items")
    _recalculate(db, task)
    task.status = "completed"
    task.finished_at = datetime.now(timezone.utc)
    _release_task_resources(db, task)
    db.commit()
    db.refresh(task)
    return task


def _require_owner(task: ScreeningTask, machine_id: str) -> None:
    if task.status != "running" or task.machine_id != machine_id:
        raise ScreeningTaskError(409, "task is not owned by this machine")


def add_screening_record(
    db: Session,
    task_id: int,
    *,
    machine_id: str,
    boss_id: str | None,
    fingerprint: str,
    display_name: str,
    source_payload: dict[str, object],
    position_index: int,
) -> tuple[ScreeningRecord, bool]:
    task = db.scalar(
        select(ScreeningTask).where(ScreeningTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    _require_owner(task, machine_id)
    identity_key = f"boss:{boss_id.strip()}" if boss_id and boss_id.strip() else f"fingerprint:{fingerprint}"
    existing = db.scalar(
        select(ScreeningRecord).where(
            ScreeningRecord.task_id == task_id,
            ScreeningRecord.identity_key == identity_key,
        )
    )
    if existing is not None:
        return existing, True
    record_count = db.scalar(
        select(func.count(ScreeningRecord.id)).where(ScreeningRecord.task_id == task_id)
    ) or 0
    if position_index > task.requested_count or record_count >= task.requested_count:
        raise ScreeningTaskError(409, "task requested count exceeded")
    record = ScreeningRecord(
        task_id=task.id,
        job_id=task.job_id,
        boss_id=boss_id.strip() if boss_id and boss_id.strip() else None,
        fingerprint=fingerprint,
        identity_key=identity_key,
        display_name=display_name,
        source_payload_json=json.dumps(source_payload, ensure_ascii=False),
        position_index=position_index,
        status="discovered",
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ScreeningRecord).where(
                ScreeningRecord.task_id == task_id,
                ScreeningRecord.identity_key == identity_key,
            )
        )
        if existing is None:
            raise
        return existing, True
    db.refresh(record)
    return record, False


def finish_screening_record(
    db: Session,
    task_id: int,
    record_id: int,
    *,
    machine_id: str,
    status: str,
    score_snapshot: dict[str, object],
    outreach_event_id: int | None = None,
    failure_code: str = "",
    failure_detail: str = "",
) -> ScreeningRecord:
    task = db.scalar(
        select(ScreeningTask).where(ScreeningTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    _require_owner(task, machine_id)
    record = db.scalar(
        select(ScreeningRecord).where(
            ScreeningRecord.id == record_id,
            ScreeningRecord.task_id == task_id,
        ).with_for_update()
    )
    if record is None:
        raise ScreeningTaskError(404, "screening record not found")
    terminal = {"needs_review", "below_threshold", "contacted", "duplicate_contact", "failed"}
    if record.status in terminal:
        if record.status != status:
            raise ScreeningTaskError(409, "screening record already completed")
        return record
    if status == "contacted":
        event = db.get(OutreachEvent, outreach_event_id) if outreach_event_id is not None else None
        if (
            event is None
            or event.screening_record_id != record.id
            or event.task_id != task.id
            or event.status != "confirmed"
            or not event.greeted
            or event.candidate_id is None
        ):
            raise ScreeningTaskError(409, "contacted record requires confirmed outreach event")
        record.candidate_id = event.candidate_id
    record.status = status
    record.score_snapshot_json = json.dumps(score_snapshot, ensure_ascii=False)
    record.outreach_event_id = outreach_event_id
    if failure_code or failure_detail:
        payload = json.loads(record.source_payload_json or "{}")
        payload["failure_code"] = failure_code
        payload["failure_detail"] = failure_detail
        record.source_payload_json = json.dumps(payload, ensure_ascii=False)
    db.commit()
    db.refresh(record)
    return record



def add_item(
    db: Session,
    task_id: int,
    *,
    machine_id: str,
    candidate_id: int,
    position_index: int,
) -> tuple[ScreeningTaskItem, bool]:
    task = db.scalar(
        select(ScreeningTask).where(ScreeningTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    _require_owner(task, machine_id)
    candidate = db.scalar(
        select(Candidate).where(Candidate.id == candidate_id).with_for_update()
    )
    if candidate is None:
        raise ScreeningTaskError(404, "candidate not found")
    existing = db.scalar(
        select(ScreeningTaskItem).where(
            ScreeningTaskItem.task_id == task_id,
            ScreeningTaskItem.candidate_id == candidate_id,
        )
    )
    if existing is not None:
        return existing, True
    item_count = db.scalar(
        select(func.count(ScreeningTaskItem.id)).where(
            ScreeningTaskItem.task_id == task_id
        )
    ) or 0
    if position_index > task.requested_count or item_count >= task.requested_count:
        raise ScreeningTaskError(409, "task requested count exceeded")
    link = db.scalar(
        select(CandidateJob).where(
            CandidateJob.candidate_id == candidate_id,
            CandidateJob.job_id == task.job_id,
        )
    )
    if link is None:
        link = CandidateJob(candidate_id=candidate_id, job_id=task.job_id)
        db.add(link)
        db.flush()
    item = ScreeningTaskItem(
        task_id=task.id,
        candidate_id=candidate_id,
        candidate_job_id=link.id,
        position_index=position_index,
        status="discovered",
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ScreeningTaskItem).where(
                ScreeningTaskItem.task_id == task_id,
                ScreeningTaskItem.candidate_id == candidate_id,
            )
        )
        if existing is None:
            raise
        return existing, True
    db.refresh(item)
    return item, False


def _recalculate(db: Session, task: ScreeningTask) -> None:
    statuses = list(
        db.scalars(
            select(ScreeningTaskItem.status).where(ScreeningTaskItem.task_id == task.id)
        ).all()
    )
    terminal = {
        "needs_review", "below_threshold", "contacted", "duplicate_contact", "failed"
    }
    task.processed_count = sum(status in terminal for status in statuses)
    task.eligible_count = sum(status in {"contacted", "duplicate_contact"} for status in statuses)
    task.contacted_count = statuses.count("contacted")
    task.review_count = statuses.count("needs_review")
    task.skipped_count = statuses.count("duplicate_contact")
    task.failed_count = statuses.count("failed")
    if task.processed_count >= task.requested_count:
        task.status = "completed"
        task.finished_at = datetime.now(timezone.utc)
        _release_task_resources(db, task)


def _validate_event_ownership(
    db: Session,
    *,
    task: ScreeningTask,
    item: ScreeningTaskItem,
    score_event_id: int | None,
    outreach_event_id: int | None,
) -> None:
    if score_event_id is not None:
        event = db.get(ScoreEvent, score_event_id)
        if event is None or event.candidate_id != item.candidate_id or event.job_id != task.job_id:
            raise ScreeningTaskError(409, "score event does not belong to task item")
        if event.task_id is not None and event.task_id != task.id:
            raise ScreeningTaskError(409, "score event does not belong to task item")
    if outreach_event_id is not None:
        event = db.get(OutreachEvent, outreach_event_id)
        if event is None or event.candidate_id != item.candidate_id or event.job_id != task.job_id:
            raise ScreeningTaskError(409, "outreach event does not belong to task item")
        if event.task_id is not None and event.task_id != task.id:
            raise ScreeningTaskError(409, "outreach event does not belong to task item")


def finish_item(
    db: Session,
    task_id: int,
    item_id: int,
    *,
    machine_id: str,
    status: str,
    score_event_id: int | None = None,
    outreach_event_id: int | None = None,
    failure_code: str = "",
    failure_detail: str = "",
) -> ScreeningTaskItem:
    task = db.scalar(
        select(ScreeningTask).where(ScreeningTask.id == task_id).with_for_update()
    )
    if task is None:
        raise ScreeningTaskError(404, "screening task not found")
    _require_owner(task, machine_id)
    item = db.scalar(
        select(ScreeningTaskItem).where(
            ScreeningTaskItem.id == item_id,
            ScreeningTaskItem.task_id == task_id,
        ).with_for_update()
    )
    if item is None:
        raise ScreeningTaskError(404, "screening task item not found")
    terminal = {
        "needs_review", "below_threshold", "contacted", "duplicate_contact", "failed"
    }
    if item.status in terminal:
        if item.status != status:
            raise ScreeningTaskError(409, "task item already completed")
        return item
    _validate_event_ownership(
        db,
        task=task,
        item=item,
        score_event_id=score_event_id,
        outreach_event_id=outreach_event_id,
    )
    if status == "contacted" and outreach_event_id is None:
        raise ScreeningTaskError(409, "contacted item requires confirmed outreach event")
    if status == "contacted":
        event = db.get(OutreachEvent, outreach_event_id)
        if (
            event is None
            or event.task_id != task.id
            or event.status != "confirmed"
            or not event.greeted
        ):
            raise ScreeningTaskError(409, "contacted item requires confirmed outreach event")
    item.status = status
    item.score_event_id = score_event_id
    item.outreach_event_id = outreach_event_id
    item.failure_code = failure_code
    item.failure_detail = failure_detail
    db.flush()
    _recalculate(db, task)
    db.commit()
    db.refresh(item)
    return item
