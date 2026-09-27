"""人工复核和手动重评路由。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_password_change_complete
from resume_api.core.config import Settings, get_settings
from resume_api.core.db import get_db
from resume_api.models import ScoreEvent
from resume_api.schemas import (
    ReEvaluateRequest,
    ReviewActionOut,
    ReviewActionRequest,
    ReviewItemOut,
    ScoreEventOut,
)
from resume_api.services import llm as llm_service
from resume_api.services import reviews as review_service

router = APIRouter(
    prefix="/api",
    tags=["reviews"],
    dependencies=[Depends(require_password_change_complete)],
)


def _translate(exc: review_service.ReviewError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _score_out(event: ScoreEvent) -> ScoreEventOut:
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


@router.get("/reviews", response_model=list[ReviewItemOut])
def get_reviews(
    job_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[ReviewItemOut]:
    return [ReviewItemOut.model_validate(item) for item in review_service.list_reviews(db, job_id=job_id)]


@router.patch("/reviews/{candidate_job_id}", response_model=ReviewActionOut)
def patch_review(
    candidate_job_id: int,
    payload: ReviewActionRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_password_change_complete),
) -> ReviewActionOut:
    try:
        link = review_service.apply_review_action(
            db,
            candidate_job_id,
            action=payload.action,
            actor_user_id=current_user.id,
        )
    except review_service.ReviewError as exc:
        raise _translate(exc) from exc
    return ReviewActionOut(candidate_job_id=link.id, status=link.status)


@router.post(
    "/candidates/{candidate_id}/jobs/{job_id}/re-evaluate",
    response_model=ScoreEventOut,
    status_code=status.HTTP_201_CREATED,
)
def re_evaluate(
    candidate_id: int,
    job_id: int,
    payload: ReEvaluateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: CurrentUser = Depends(require_password_change_complete),
) -> ScoreEventOut:
    try:
        event = review_service.re_evaluate(
            db,
            candidate_id,
            job_id,
            payload,
            settings=settings,
            actor_user_id=current_user.id,
        )
    except review_service.ReviewError as exc:
        db.rollback()
        raise _translate(exc) from exc
    except llm_service.LlmNotConfiguredError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider is not configured",
        ) from exc
    except llm_service.LlmUpstreamError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM provider request failed",
        ) from exc
    return _score_out(event)
