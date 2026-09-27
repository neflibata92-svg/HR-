"""候选人路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_password_change_complete
from resume_api.core.db import get_db
from resume_api.models import CandidateJob, JobPosting, Resume
from resume_api.schemas import (
    ActiveResumeUpdate,
    CandidateJobOut,
    CandidateOut,
    CandidateUpsert,
    ExchangeBlockedOut,
    ExchangeCreate,
    ResumeInboxCandidateOut,
)
from resume_api.services import audit as audit_service
from resume_api.services import candidates as candidates_service
from resume_api.services import events as events_service
from resume_api.services import resume_inbox as resume_inbox_service

router = APIRouter(
    prefix="/api/candidates",
    tags=["candidates"],
    dependencies=[Depends(require_password_change_complete)],
)


@router.get("/resume-inbox", response_model=list[ResumeInboxCandidateOut])
def resume_inbox(
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> list[ResumeInboxCandidateOut]:
    return [
        ResumeInboxCandidateOut.model_validate(item)
        for item in resume_inbox_service.list_waiting_candidates(
            db, owner_user_id=user.id
        )
    ]


@router.get("", response_model=list[CandidateOut])
def list_candidates(
    q: str | None = Query(default=None),
    job_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    min_score: int | None = Query(default=None),
    needs_review: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[CandidateOut]:
    rows = candidates_service.search_candidates(
        db,
        q,
        job_id=job_id,
        status=status,
        min_score=min_score,
        needs_review=needs_review,
    )
    return [CandidateOut.model_validate(candidate) for candidate in rows]


@router.post("", response_model=CandidateOut)
def upsert(payload: CandidateUpsert, db: Session = Depends(get_db)) -> CandidateOut:
    return CandidateOut.model_validate(candidates_service.upsert_candidate(db, payload))


@router.post("/{candidate_id}/jobs/{job_id}", response_model=CandidateJobOut)
def attach_candidate_job(
    candidate_id: int,
    job_id: int,
    db: Session = Depends(get_db),
) -> CandidateJobOut:
    candidate = candidates_service.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    if db.get(JobPosting, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    link = candidates_service.get_or_create_candidate_job(
        db,
        candidate_id=candidate.id,
        job_id=job_id,
    )
    return CandidateJobOut.model_validate(link)


@router.get("/{candidate_id}/jobs", response_model=list[CandidateJobOut])
def candidate_jobs(candidate_id: int, db: Session = Depends(get_db)) -> list[CandidateJobOut]:
    candidate = candidates_service.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    return [
        CandidateJobOut.model_validate(link)
        for link in candidates_service.list_candidate_jobs(db, candidate.id)
    ]


@router.patch(
    "/{candidate_id}/jobs/{job_id}/active-resume",
    response_model=CandidateJobOut,
)
def change_active_resume(
    candidate_id: int,
    job_id: int,
    payload: ActiveResumeUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> CandidateJobOut:
    candidate = candidates_service.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    link = db.query(CandidateJob).filter_by(
        candidate_id=candidate.id, job_id=job_id
    ).one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="candidate job not found")
    resume = db.get(Resume, payload.resume_id)
    if resume is None or resume.candidate_id != candidate.id:
        raise HTTPException(status_code=422, detail="resume does not belong to candidate")
    previous_resume_id = link.active_resume_id
    link.active_resume_id = resume.id
    audit_service.add_audit_event(
        db,
        actor_user_id=user.id,
        action="candidate_job.active_resume_changed",
        entity_type="candidate_job",
        entity_id=str(link.id),
        details={"previous_resume_id": previous_resume_id, "resume_id": resume.id},
    )
    db.commit()
    db.refresh(link)
    return CandidateJobOut.model_validate(link)


@router.post("/{candidate_id}/exchanges")
def create_exchange(
    candidate_id: int,
    payload: ExchangeCreate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> dict[str, int]:
    candidate = candidates_service.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    if not payload.operator:
        payload = ExchangeCreate(operator=user.username, type=payload.type)
    event = events_service.add_exchange(
        db,
        candidate.id,
        payload,
        actor_user_id=user.id,
    )
    return {"id": event.id}


@router.get("/{candidate_id}/exchange-blocked", response_model=ExchangeBlockedOut)
def exchange_blocked(
    candidate_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
) -> ExchangeBlockedOut:
    candidate = candidates_service.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    blocked = events_service.is_exchange_blocked(db, candidate.id, days=days)
    return ExchangeBlockedOut(blocked=blocked)
