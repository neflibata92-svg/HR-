"""每位 HR 的累计联系额度与原子预留。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from resume_api.models import (
    OutreachQuotaLedger,
    OutreachQuotaReservation,
    ScreeningTask,
    ScreeningTaskItem,
)


class OutreachQuotaError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _ledger(db: Session, user_id: int, *, lock: bool = False) -> OutreachQuotaLedger:
    statement = select(OutreachQuotaLedger).where(OutreachQuotaLedger.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    ledger = db.scalar(statement)
    if ledger is not None:
        return ledger

    values = {"user_id": user_id, "hard_limit": 200, "confirmed_count": 0, "reserved_count": 0}
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        db.execute(sqlite_insert(OutreachQuotaLedger).values(**values).on_conflict_do_nothing(
            index_elements=["user_id"]
        ))
    elif dialect == "postgresql":
        db.execute(pg_insert(OutreachQuotaLedger).values(**values).on_conflict_do_nothing(
            index_elements=["user_id"]
        ))
    else:
        db.add(OutreachQuotaLedger(**values))
        db.flush()
    ledger = db.scalar(statement)
    if ledger is None:
        raise OutreachQuotaError(500, "quota ledger unavailable")
    return ledger


def get_usage(db: Session, user_id: int) -> dict[str, int]:
    ledger = _ledger(db, user_id)
    return {
        "limit": ledger.hard_limit,
        "confirmed": ledger.confirmed_count,
        "reserved": ledger.reserved_count,
        "remaining": ledger.hard_limit - ledger.confirmed_count - ledger.reserved_count,
    }


def remaining_for_task_admission(db: Session, user_id: int) -> int:
    """Return available quota after reserving capacity for existing active batches."""
    ledger = _ledger(db, user_id, lock=True)
    # SQLite ignores SELECT FOR UPDATE; this write serializes task admission in its transaction.
    db.execute(
        update(OutreachQuotaLedger)
        .where(OutreachQuotaLedger.id == ledger.id)
        .values(updated_at=func.now())
    )
    active_statuses = ("ready", "running", "pausing", "paused", "cancelling")
    tasks = db.execute(
        select(ScreeningTask.id, ScreeningTask.requested_count, ScreeningTask.processed_count)
        .where(
            ScreeningTask.created_by_user_id == user_id,
            ScreeningTask.status.in_(active_statuses),
        )
    ).all()
    reserved_by_task = dict(
        db.execute(
            select(OutreachQuotaReservation.task_id, func.count(OutreachQuotaReservation.id))
            .where(
                OutreachQuotaReservation.task_id.is_not(None),
                OutreachQuotaReservation.status.in_(("reserved", "unknown")),
            )
            .group_by(OutreachQuotaReservation.task_id)
        ).all()
    )
    processed_unknown_by_task = dict(
        db.execute(
            select(OutreachQuotaReservation.task_id, func.count(OutreachQuotaReservation.id))
            .join(
                ScreeningTaskItem,
                ScreeningTaskItem.id == OutreachQuotaReservation.task_item_id,
            )
            .where(
                OutreachQuotaReservation.task_id.is_not(None),
                OutreachQuotaReservation.status == "unknown",
                ScreeningTaskItem.status.in_(
                    ("needs_review", "below_threshold", "contacted", "duplicate_contact", "failed")
                ),
            )
            .group_by(OutreachQuotaReservation.task_id)
        ).all()
    )
    unreserved_batch_capacity = sum(
        max(
            requested
            - processed
            - reserved_by_task.get(task_id, 0)
            + processed_unknown_by_task.get(task_id, 0),
            0,
        )
        for task_id, requested, processed in tasks
    )
    usage_remaining = ledger.hard_limit - ledger.confirmed_count - ledger.reserved_count
    return max(usage_remaining - unreserved_batch_capacity, 0)


def reserve(
    db: Session,
    *,
    user_id: int,
    outreach_event_id: int | None,
    task_id: int | None = None,
    task_item_id: int | None = None,
) -> OutreachQuotaReservation:
    existing = None
    if outreach_event_id is not None:
        existing = db.scalar(
            select(OutreachQuotaReservation).where(
                OutreachQuotaReservation.outreach_event_id == outreach_event_id
            )
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise OutreachQuotaError(409, "outreach quota owner mismatch")
            return existing
    if task_item_id is not None:
        existing = db.scalar(
            select(OutreachQuotaReservation).where(
                OutreachQuotaReservation.task_item_id == task_item_id
            )
        )
        if existing is not None:
            if existing.user_id != user_id:
                raise OutreachQuotaError(409, "outreach quota owner mismatch")
            return existing

    ledger = _ledger(db, user_id, lock=True)
    result = db.execute(
        update(OutreachQuotaLedger)
        .where(
            OutreachQuotaLedger.id == ledger.id,
            OutreachQuotaLedger.confirmed_count + OutreachQuotaLedger.reserved_count
            < OutreachQuotaLedger.hard_limit,
        )
        .values(reserved_count=OutreachQuotaLedger.reserved_count + 1)
    )
    if result.rowcount != 1:
        raise OutreachQuotaError(409, "outreach quota exhausted")
    reservation = OutreachQuotaReservation(
        user_id=user_id,
        task_id=task_id,
        task_item_id=task_item_id,
        outreach_event_id=outreach_event_id,
        status="reserved",
    )
    db.add(reservation)
    db.flush()
    return reservation


def confirm(db: Session, outreach_event_id: int) -> OutreachQuotaReservation | None:
    reservation = _reservation(db, outreach_event_id)
    if reservation is None or reservation.status == "confirmed":
        return reservation
    if reservation.status not in {"reserved", "unknown"}:
        raise OutreachQuotaError(409, "quota reservation is not confirmable")
    ledger = _ledger(db, reservation.user_id, lock=True)
    result = db.execute(
        update(OutreachQuotaLedger)
        .where(
            OutreachQuotaLedger.id == ledger.id,
            OutreachQuotaLedger.reserved_count > 0,
        )
        .values(
            reserved_count=OutreachQuotaLedger.reserved_count - 1,
            confirmed_count=OutreachQuotaLedger.confirmed_count + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        raise OutreachQuotaError(409, "quota reservation counters are inconsistent")
    reservation.status = "confirmed"
    reservation.resolved_at = datetime.now(timezone.utc)
    db.flush()
    return reservation


def release_before_send(db: Session, outreach_event_id: int) -> OutreachQuotaReservation | None:
    reservation = _reservation(db, outreach_event_id)
    if reservation is None or reservation.status == "released":
        return reservation
    if reservation.status != "reserved":
        raise OutreachQuotaError(409, "unknown send outcome cannot release quota")
    ledger = _ledger(db, reservation.user_id, lock=True)
    result = db.execute(
        update(OutreachQuotaLedger)
        .where(
            OutreachQuotaLedger.id == ledger.id,
            OutreachQuotaLedger.reserved_count > 0,
        )
        .values(
            reserved_count=OutreachQuotaLedger.reserved_count - 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        raise OutreachQuotaError(409, "quota reservation counters are inconsistent")
    reservation.status = "released"
    reservation.resolved_at = datetime.now(timezone.utc)
    db.flush()
    return reservation


def release_unknown_after_admin_review(
    db: Session, outreach_event_id: int
) -> OutreachQuotaReservation:
    reservation = _reservation(db, outreach_event_id)
    if reservation is None or reservation.status != "unknown":
        raise OutreachQuotaError(409, "outreach quota is not awaiting admin review")
    ledger = _ledger(db, reservation.user_id, lock=True)
    result = db.execute(
        update(OutreachQuotaLedger)
        .where(
            OutreachQuotaLedger.id == ledger.id,
            OutreachQuotaLedger.reserved_count > 0,
        )
        .values(
            reserved_count=OutreachQuotaLedger.reserved_count - 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    if result.rowcount != 1:
        raise OutreachQuotaError(409, "quota reservation counters are inconsistent")
    reservation.status = "released"
    reservation.resolved_at = datetime.now(timezone.utc)
    db.flush()
    return reservation


def keep_pending_for_review(db: Session, outreach_event_id: int) -> OutreachQuotaReservation | None:
    reservation = _reservation(db, outreach_event_id)
    if reservation is None or reservation.status == "unknown":
        return reservation
    if reservation.status != "reserved":
        raise OutreachQuotaError(409, "quota reservation is not awaiting review")
    reservation.status = "unknown"
    db.flush()
    return reservation


def _reservation(db: Session, outreach_event_id: int) -> OutreachQuotaReservation | None:
    return db.scalar(
        select(OutreachQuotaReservation)
        .where(OutreachQuotaReservation.outreach_event_id == outreach_event_id)
        .with_for_update()
    )
