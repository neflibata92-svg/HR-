"""打分、招呼、交换事件服务。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.models import ExchangeEvent, OutreachEvent, ScoreEvent
from resume_api.schemas import ExchangeCreate, OutreachCreate, ScoreEventCreate


def add_exchange(
    db: Session,
    candidate_id: int,
    payload: ExchangeCreate,
    *,
    actor_user_id: int | None = None,
) -> ExchangeEvent:
    event = ExchangeEvent(
        candidate_id=candidate_id,
        operator=payload.operator,
        type=payload.type,
        actor_user_id=actor_user_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def is_exchange_blocked(
    db: Session,
    candidate_id: int,
    *,
    days: int = 30,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = current - timedelta(days=days)
    events = list(
        db.scalars(select(ExchangeEvent).where(ExchangeEvent.candidate_id == candidate_id)).all()
    )
    for event in events:
        created = event.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= cutoff:
            return True
    return False


def add_score_event(db: Session, payload: ScoreEventCreate) -> ScoreEvent:
    event = ScoreEvent(
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        hard_filter_passed=payload.hard_filter_passed,
        hard_filter_reasons=json.dumps(payload.hard_filter_reasons, ensure_ascii=False),
        score=payload.score,
        reason=payload.reason,
        model=payload.model,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def add_outreach(db: Session, payload: OutreachCreate) -> tuple[OutreachEvent, bool]:
    existing = db.scalar(
        select(OutreachEvent).where(
            OutreachEvent.candidate_id == payload.candidate_id,
            OutreachEvent.job_id == payload.job_id,
        )
    )
    if existing is not None:
        return existing, True
    event = OutreachEvent(
        candidate_id=payload.candidate_id,
        job_id=payload.job_id,
        greeted=payload.greeted,
        attachment_received=payload.attachment_received,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event, False
