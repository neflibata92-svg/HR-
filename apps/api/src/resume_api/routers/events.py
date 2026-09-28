"""打分与招呼事件路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_password_change_complete
from resume_api.core.db import get_db
from resume_api.models import OutreachEvent
from resume_api.schemas import OutreachCreate, OutreachOut, ScoreEventCreate, ScoreEventOut
from resume_api.services import events as events_service
from resume_api.services import outreach as outreach_service
from resume_api.services import screening_tasks as task_service

router = APIRouter(
    prefix="/api/events",
    tags=["events"],
    dependencies=[Depends(require_password_change_complete)],
)


@router.post("/scores", response_model=ScoreEventOut)
def post_score(
    payload: ScoreEventCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ScoreEventOut:
    if payload.task_id is not None:
        try:
            task_service.require_task_access(
                db, payload.task_id, actor_user_id=user.id, actor_role=user.role
            )
        except task_service.ScreeningTaskError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    event = events_service.add_score_event(db, payload)
    return ScoreEventOut(
        id=event.id,
        candidate_id=event.candidate_id,
        job_id=event.job_id,
        candidate_job_id=event.candidate_job_id,
        resume_id=event.resume_id,
        task_id=event.task_id,
        hard_filter_passed=event.hard_filter_passed,
        hard_filter_reasons=json.loads(event.hard_filter_reasons or "[]"),
        score=event.score,
        reason=event.reason,
        evidence=json.loads(event.evidence_json or "[]"),
        missing_fields=json.loads(event.missing_fields_json or "[]"),
        estimated_fields=json.loads(event.estimated_fields_json or "[]"),
        critical_fields=json.loads(event.critical_fields_json or "[]"),
        confidence=event.confidence,
        decision=event.decision,
        model=event.model,
        created_at=event.created_at,
    )


@router.post("/outreach", response_model=OutreachOut)
def post_outreach(
    payload: OutreachCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> OutreachOut:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="task-based outreach is required for members")
    try:
        event, hit = events_service.add_outreach(db, payload, actor_user_id=user.id)
    except outreach_service.OutreachError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
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
