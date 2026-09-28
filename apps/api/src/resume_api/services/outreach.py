"""全局联系去重、两阶段发送与人工重发授权。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_api.models import (
    Candidate,
    CandidateJob,
    JobPosting,
    OutreachEvent,
    OutreachOverride,
    OutreachQuotaReservation,
    ScreeningRecord,
    ScreeningTask,
    ScreeningTaskItem,
    User,
)
from resume_api.schemas import CandidateUpsert, OutreachOverrideCreate, OutreachReservationCreate
from resume_api.services import candidates as candidate_service
from resume_api.services import screening_tasks as task_service
from resume_api.services.audit import add_audit_event
from resume_api.services import outreach_quota as quota_service


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
    actor_user_id: int,
    now: datetime | None = None,
) -> OutreachEvent:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(minutes=30)
    candidate: Candidate | None = None
    record: ScreeningRecord | None = None
    task_item: ScreeningTaskItem | None = None
    effective_task_id = payload.task_id
    if payload.task_item_id is not None:
        task_item = db.scalar(
            select(ScreeningTaskItem)
            .where(ScreeningTaskItem.id == payload.task_item_id)
            .with_for_update()
        )
        if task_item is None:
            raise OutreachError(404, "screening task item not found")
        if effective_task_id is not None and effective_task_id != task_item.task_id:
            raise OutreachError(409, "task item does not match task")
        effective_task_id = task_item.task_id
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
        if effective_task_id is not None and record.task_id != effective_task_id:
            raise OutreachError(409, "screening record does not match task")
        if effective_task_id is None:
            effective_task_id = record.task_id
        if record.candidate_id is not None:
            candidate = db.get(Candidate, record.candidate_id)
        if task_item is not None and record.task_id != task_item.task_id:
            raise OutreachError(409, "screening record does not match task item")
    elif task_item is not None:
        candidate = db.get(Candidate, task_item.candidate_id)
        if candidate is None:
            raise OutreachError(409, "task item candidate not found")
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
    if task_item is not None and candidate is not None and task_item.candidate_id != candidate.id:
        raise OutreachError(409, "candidate does not match task item")
    if db.get(JobPosting, payload.job_id) is None:
        raise OutreachError(404, "job not found")
    task = None
    if effective_task_id is not None:
        task = db.get(ScreeningTask, effective_task_id)
        if task is None or task.job_id != payload.job_id:
            raise OutreachError(409, "task does not match outreach")
        quota_owner_user_id = task.created_by_user_id
    else:
        quota_owner_user_id = actor_user_id
    if task_item is not None:
        existing_reservation = db.scalar(
            select(OutreachQuotaReservation).where(
                OutreachQuotaReservation.task_item_id == task_item.id
            )
        )
        if existing_reservation is not None:
            if existing_reservation.user_id != quota_owner_user_id:
                raise OutreachError(409, "outreach quota owner mismatch")
            existing_event = db.get(OutreachEvent, existing_reservation.outreach_event_id)
            if existing_event is None:
                raise OutreachError(409, "task item already has a quota reservation")
            existing_event.idempotent_hit = True
            return existing_event
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
    if any(event.status == "unknown" for event in events):
        raise OutreachError(409, "outreach verification required")
    if any(event.status == "sending" and _aware(event.created_at) <= cutoff for event in events):
        raise OutreachError(409, "outreach verification required")
    blocked = any(event.status in {"sending", "unknown", "sent", "confirmed"} for event in events)
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
        task_id=effective_task_id,
        quota_owner_user_id=quota_owner_user_id,
        message_snapshot=payload.message,
        status="sending",
        manual_override_by_user_id=(override.authorized_by_user_id if override else None),
        greeted=False,
    )
    db.add(event)
    db.flush()
    try:
        quota_service.reserve(
            db,
            user_id=quota_owner_user_id,
            outreach_event_id=event.id,
            task_id=effective_task_id,
            task_item_id=task_item.id if task_item is not None else None,
        )
    except quota_service.OutreachQuotaError as exc:
        db.rollback()
        raise OutreachError(exc.status_code, exc.detail) from exc
    except IntegrityError as exc:
        db.rollback()
        if task_item is not None:
            existing_reservation = db.scalar(
                select(OutreachQuotaReservation).where(
                    OutreachQuotaReservation.task_item_id == task_item.id
                )
            )
            if existing_reservation is not None and existing_reservation.user_id == quota_owner_user_id:
                existing_event = db.get(OutreachEvent, existing_reservation.outreach_event_id)
                if existing_event is not None:
                    existing_event.idempotent_hit = True
                    return existing_event
        raise OutreachError(409, "outreach reservation already exists") from exc
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
    if event.status not in {"sending", "unknown"}:
        raise OutreachError(409, "outreach event is not awaiting verification")
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
    try:
        quota_service.confirm(db, event_id)
    except quota_service.OutreachQuotaError as exc:
        db.rollback()
        raise OutreachError(exc.status_code, exc.detail) from exc
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
    try:
        quota_service.release_before_send(db, event_id)
    except quota_service.OutreachQuotaError as exc:
        db.rollback()
        raise OutreachError(exc.status_code, exc.detail) from exc
    event.status = "failed"
    event.failure_reason = reason
    db.commit()
    db.refresh(event)
    return event


def mark_unknown(db: Session, event_id: int, *, reason: str) -> OutreachEvent:
    event = _get_sending(db, event_id)
    if event.status == "unknown":
        return event
    try:
        quota_service.keep_pending_for_review(db, event_id)
    except quota_service.OutreachQuotaError as exc:
        db.rollback()
        raise OutreachError(exc.status_code, exc.detail) from exc
    event.status = "unknown"
    event.failure_reason = reason
    db.commit()
    db.refresh(event)
    return event


def list_unknown_outreach(db: Session) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            OutreachEvent.id,
            OutreachEvent.candidate_id,
            func.coalesce(Candidate.name, "").label("candidate_name"),
            OutreachEvent.job_id,
            JobPosting.name.label("job_name"),
            func.coalesce(User.username, "").label("quota_owner_username"),
            OutreachEvent.task_id,
            OutreachEvent.failure_reason,
            OutreachEvent.created_at,
        )
        .outerjoin(Candidate, Candidate.id == OutreachEvent.candidate_id)
        .join(JobPosting, JobPosting.id == OutreachEvent.job_id)
        .outerjoin(User, User.id == OutreachEvent.quota_owner_user_id)
        .where(OutreachEvent.status == "unknown")
        .order_by(OutreachEvent.created_at, OutreachEvent.id)
    ).mappings().all()
    return [dict(row) for row in rows]


def release_unknown_after_admin_review(
    db: Session,
    event_id: int,
    *,
    admin_user_id: int,
    reason: str,
) -> OutreachEvent:
    event = db.scalar(
        select(OutreachEvent).where(OutreachEvent.id == event_id).with_for_update()
    )
    if event is None:
        raise OutreachError(404, "outreach event not found")
    if event.status != "unknown":
        raise OutreachError(409, "outreach event is not awaiting admin review")
    original_reason = event.failure_reason
    try:
        quota_service.release_unknown_after_admin_review(db, event_id)
    except quota_service.OutreachQuotaError as exc:
        db.rollback()
        raise OutreachError(exc.status_code, exc.detail) from exc
    event.status = "failed"
    event.greeted = False
    event.failure_reason = f"admin_verified_not_sent: {reason}"
    add_audit_event(
        db,
        actor_user_id=admin_user_id,
        action="outreach.unknown_resolved_not_sent",
        entity_type="outreach_event",
        entity_id=str(event.id),
        details={
            "reason": reason,
            "previous_failure_reason": original_reason,
            "quota_owner_user_id": event.quota_owner_user_id,
        },
    )
    db.commit()
    db.refresh(event)
    return event


def _get_sending(db: Session, event_id: int) -> OutreachEvent:
    event = db.scalar(
        select(OutreachEvent).where(OutreachEvent.id == event_id).with_for_update()
    )
    if event is None:
        raise OutreachError(404, "outreach event not found")
    if event.status not in {"sending", "unknown"}:
        raise OutreachError(409, "outreach event is not awaiting verification")
    return event


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
