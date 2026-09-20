"""打分与招呼事件路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.auth import get_current_user
from resume_api.core.db import get_db
from resume_api.models import OutreachEvent
from resume_api.schemas import OutreachCreate, OutreachOut, ScoreEventCreate, ScoreEventOut
from resume_api.services import events as events_service

router = APIRouter(prefix="/api/events", tags=["events"], dependencies=[Depends(get_current_user)])


@router.post("/scores", response_model=ScoreEventOut)
def post_score(payload: ScoreEventCreate, db: Session = Depends(get_db)) -> ScoreEventOut:
    return ScoreEventOut.model_validate(events_service.add_score_event(db, payload))


@router.post("/outreach", response_model=OutreachOut)
def post_outreach(payload: OutreachCreate, db: Session = Depends(get_db)) -> OutreachOut:
    event, hit = events_service.add_outreach(db, payload)
    if payload.attachment_received and hit:
        event.attachment_received = True
        db.commit()
        db.refresh(event)
    out = OutreachOut.model_validate(event)
    out.idempotent_hit = hit
    return out


@router.get("/outreach")
def get_outreach(
    job_id: int = Query(...),
    candidate_id: int = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    existing = db.scalar(
        select(OutreachEvent).where(
            OutreachEvent.candidate_id == candidate_id,
            OutreachEvent.job_id == job_id,
        )
    )
    return {"exists": existing is not None}
