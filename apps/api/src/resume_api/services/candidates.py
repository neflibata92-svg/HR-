"""候选人服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.models import Candidate
from resume_api.schemas import CandidateUpsert


def upsert_candidate(db: Session, payload: CandidateUpsert) -> Candidate:
    existing: Candidate | None = None
    if payload.boss_id:
        existing = db.scalar(select(Candidate).where(Candidate.boss_id == payload.boss_id))
    if existing is None:
        existing = db.scalar(select(Candidate).where(Candidate.fingerprint == payload.fingerprint))
    if existing is None:
        candidate = Candidate(**payload.model_dump())
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        return candidate
    for key, value in payload.model_dump().items():
        setattr(existing, key, value)
    db.commit()
    db.refresh(existing)
    return existing


def get_candidate(db: Session, candidate_id: int) -> Candidate | None:
    return db.get(Candidate, candidate_id)


def search_candidates(db: Session, q: str | None = None) -> list[Candidate]:
    stmt = select(Candidate).order_by(Candidate.id.desc())
    rows = list(db.scalars(stmt).all())
    if not q:
        return rows
    needle = q.strip().lower()
    return [c for c in rows if needle in (c.name or "").lower() or needle in (c.boss_id or "").lower()]
