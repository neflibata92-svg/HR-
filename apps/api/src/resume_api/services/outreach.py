"""全局联系去重、两阶段发送与人工重发授权。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.models import (
    Candidate,
    CandidateJob,
    JobPosting,
    OutreachEvent,
    OutreachOverride,
    ScreeningRecord,
    ScreeningTask,
)
from resume_api.schemas import CandidateUpsert, OutreachOverrideCreate, OutreachReservationCreate
from resume_api.services import candidates as candidate_service
from resume_api.services import screening_tasks as task_service
from resume_api.services.audit import add_audit_event


class OutreachError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def create_override(
    db: Session,
    payload: OutreachOverrideCreate,
    *,
    user_id: int,
) -> OutreachOverride:
    override = OutreachOverride(
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        authorized_by_user_id=user_id,
        reason=payload.reason,
    )
    db.add(override)
    db.flush()
    add_audit_event(
        db,
        actor_user_id=user_id,
        action="outreach.override_created",
        entity_type="outreach_override",
        entity_id=str(override.id),
        details={"candidate_id": payload.candidate_id, "job_id": payload.job_id},
    )
    db.commit()
    db.refresh(override)
    return override


def reserve(
    db: Session,
    payload: OutreachReservationCreate,
    *,
    now: datetime | None = None,
) -> OutreachEvent:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(minutes=30)
    candidate: Candidate | None = None
    record: ScreeningRecord | None = None
    if payload.screening_record_id is not None:
        record = db.scalar(
            select(ScreeningRecord)
            .where(ScreeningRecord.id == payload.screening_record_id)
            .with_for_update()
        )
        if record is None:
            raise OutreachError(404, "screening record not found")
        if record.job_id != payload.job_id:
            raise OutreachError(409, "screening record does not match outreach")
        if payload.task_id is not None and record.task_id != payload.task_id:
            raise OutreachError(409, "screening record does not match task")
        if record.candidate_id is not None:
            candidate = db.get(Candidate, record.candidate_id)
    elif payload.candidate_id is not None:
        candidate = db.scalar(
            select(Candidate)
            .where(Candidate.id == payload.candidate_id)
            .with_for_update()
        )
        if candidate is None:
            raise OutreachError(404, "candidate not found")
    else:
        raise OutreachError(422, "candidate_id or screening_record_id is required")
    if db.get(JobPosting, payload.job_id) is None:
        raise OutreachError(404, "job not found")
    if payload.task_id is not None:
        task = db.get(ScreeningTask, payload.task_id)
        if task is None or task.job_id != payload.job_id:
            raise OutreachError(409, "task does not match outreach")
    events_query = select(OutreachEvent)
    if candidate is not None:
        events_query = events_query.where(OutreachEvent.candidate_id == candidate.id)
    else:
        events_query = events_query.where(
            OutreachEvent.screening_record_id == payload.screening_record_id
        )
    events = list(
        db.scalars(events_query.order_by(OutreachEvent.id).with_for_update()).all()
    )
    if any(event.status == "sending" and _aware(event.created_at) <= cutoff for event in events):
        raise OutreachError(409, "outreach verification required")
    blocked = any(event.status in {"sending", "sent", "confirmed"} for event in events)
    override = None
    if blocked:
        override = db.scalar(
            select(OutreachOverride).where(
                OutreachOverride.candidate_id == payload.candidate_id,
                OutreachOverride.job_id == payload.job_id,
                OutreachOverride.status == "available",
            ).order_by(OutreachOverride.id).with_for_update()
        )
        if override is None:
            if any(event.status == "confirmed" for event in events):
                raise OutreachError(409, "candidate already contacted")
            raise OutreachError(409, "outreach already sending")
    event = OutreachEvent(
        candidate_id=candidate.id if candidate is not None else None,
        screening_record_id=record.id if record is not None else None,
        job_id=payload.job_id,
        task_id=payload.task_id,
        message_snapshot=payload.message,
        status="sending",
        manual_override_by_user_id=(override.authorized_by_user_id if override else None),
        greeted=False,
    )
    db.add(event)
    db.flush()
    if override is not None:
        override.status = "consumed"
        override.consumed_by_outreach_event_id = event.id
        override.consumed_at = current
    db.commit()
    db.refresh(event)
    return event


def require_outreach_access(
    db: Session,
    event_id: int,
    *,
    actor_user_id: int,
    actor_role: str,
) -> OutreachEvent:
    event = db.get(OutreachEvent, event_id)
    if event is None:
        raise OutreachError(404, "outreach event not found")
    if event.task_id is None:
        if actor_role != "admin":
            raise OutreachError(404, "outreach event not found")
        return event
    try:
        task_service.require_task_access(
            db,
            event.task_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
    except task_service.ScreeningTaskError as exc:
        raise OutreachError(exc.status_code, exc.detail) from exc
    return event


def confirm(db: Session, event_id: int) -> OutreachEvent:
    event = db.scalar(
        select(OutreachEvent).where(OutreachEvent.id == event_id).with_for_update()
    )
    if event is None:
        raise OutreachError(404, "outreach event not found")
    if event.status == "confirmed":
        return event
    if event.status != "sending":
        raise OutreachError(409, "outreach event is not sending")
    if event.screening_record_id is not None and event.candidate_id is None:
        record = db.scalar(
            select(ScreeningRecord)
            .where(ScreeningRecord.id == event.screening_record_id)
            .with_for_update()
        )
        if record is None:
            raise OutreachError(409, "screening record not found")
        source = _record_source(record)
        segments = source.get("job_segments", [])
        candidate = candidate_service.upsert_candidate(
            db,
            CandidateUpsert(
                boss_id=record.boss_id,
                fingerprint=record.fingerprint,
                name=record.display_name,
                phone=_optional_text(source.get("phone")),
                email=_optional_text(source.get("email")),
                age=_optional_int(source.get("age")),
                years_of_experience=_optional_float(source.get("years_of_experience")),
                job_segments_json=_json_value(segments, fallback="[]"),
                source="boss",
            ),
            commit=False,
        )
        link = db.scalar(
            select(CandidateJob).where(
                CandidateJob.candidate_id == candidate.id,
                CandidateJob.job_id == event.job_id,
            )
        )
        if link is None:
            link = CandidateJob(
                candidate_id=candidate.id,
                job_id=event.job_id,
                status="waiting_resume",
            )
            db.add(link)
        else:
            link.status = "waiting_resume"
        event.candidate_id = candidate.id
        record.candidate_id = candidate.id
        record.outreach_event_id = event.id
        record.status = "contacted"
    event.status = "confirmed"
    event.greeted = True
    event.confirmed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(event)
    return event


def _record_source(record: ScreeningRecord) -> dict[str, object]:
    import json

    try:
        value = json.loads(record.source_payload_json or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _optional_text(value: object) -> str | None:
    return str(value) if value not in (None, "") else None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _json_value(value: object, *, fallback: str) -> str:
    import json

    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return fallback



def fail(db: Session, event_id: int, *, reason: str) -> OutreachEvent:
    event = _get_sending(db, event_id)
    event.status = "failed"
    event.failure_reason = reason
    db.commit()
    db.refresh(event)
    return event


def _get_sending(db: Session, event_id: int) -> OutreachEvent:
    event = db.scalar(
        select(OutreachEvent).where(OutreachEvent.id == event_id).with_for_update()
    )
    if event is None:
        raise OutreachError(404, "outreach event not found")
    if event.status != "sending":
        raise OutreachError(409, "outreach event is not sending")
    return event


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
