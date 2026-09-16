"""候选人路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from resume_api.core.auth import require_api_token
from resume_api.core.db import get_db
from resume_api.schemas import CandidateOut, CandidateUpsert, ExchangeBlockedOut, ExchangeCreate
from resume_api.services import candidates as candidates_service
from resume_api.services import events as events_service

router = APIRouter(
    prefix="/api/candidates",
    tags=["candidates"],
    dependencies=[Depends(require_api_token)],
)


@router.get("", response_model=list[CandidateOut])
def list_candidates(q: str | None = Query(default=None), db: Session = Depends(get_db)) -> list[CandidateOut]:
    return [CandidateOut.model_validate(c) for c in candidates_service.search_candidates(db, q)]


@router.post("", response_model=CandidateOut)
def upsert(payload: CandidateUpsert, db: Session = Depends(get_db)) -> CandidateOut:
    return CandidateOut.model_validate(candidates_service.upsert_candidate(db, payload))


@router.post("/{candidate_id}/exchanges")
def create_exchange(
    candidate_id: int,
    payload: ExchangeCreate,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if candidates_service.get_candidate(db, candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    event = events_service.add_exchange(db, candidate_id, payload)
    return {"id": event.id}


@router.get("/{candidate_id}/exchange-blocked", response_model=ExchangeBlockedOut)
def exchange_blocked(
    candidate_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
) -> ExchangeBlockedOut:
    if candidates_service.get_candidate(db, candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    blocked = events_service.is_exchange_blocked(db, candidate_id, days=days)
    return ExchangeBlockedOut(blocked=blocked)
