"""候选人服务。"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.models import (
    Candidate,
    CandidateJob,
    CandidateMergeSuggestion,
    OutreachEvent,
    ScoreEvent,
)
from resume_api.schemas import CandidateUpsert


def _normalize_boss_id(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_phone(value: str | None) -> str | None:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    return digits or None


def _normalize_email(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return normalized or None


def _resolve_merged_candidate(db: Session, candidate: Candidate) -> Candidate:
    seen: set[int] = set()
    current = candidate
    while current.merged_into_candidate_id is not None and current.id not in seen:
        seen.add(current.id)
        target = db.get(Candidate, current.merged_into_candidate_id)
        if target is None:
            break
        current = target
    return current


def _create_merge_suggestions(
    db: Session,
    candidate: Candidate,
    *,
    phone: str | None,
    email: str | None,
) -> None:
    matches: dict[int, set[str]] = {}
    if phone:
        for row in db.scalars(
            select(Candidate).where(
                Candidate.phone_normalized == phone,
                Candidate.id != candidate.id,
                Candidate.merged_into_candidate_id.is_(None),
            )
        ):
            matches.setdefault(row.id, set()).add("phone")
    if email:
        for row in db.scalars(
            select(Candidate).where(
                Candidate.email_normalized == email,
                Candidate.id != candidate.id,
                Candidate.merged_into_candidate_id.is_(None),
            )
        ):
            matches.setdefault(row.id, set()).add("email")

    for target_id, reasons in matches.items():
        source_id, normalized_target_id = sorted((candidate.id, target_id))
        existing = db.scalar(
            select(CandidateMergeSuggestion).where(
                CandidateMergeSuggestion.source_candidate_id == source_id,
                CandidateMergeSuggestion.target_candidate_id == normalized_target_id,
            )
        )
        if existing is None:
            db.add(
                CandidateMergeSuggestion(
                    source_candidate_id=source_id,
                    target_candidate_id=normalized_target_id,
                    match_reason_json=json.dumps(sorted(reasons)),
                )
            )


def upsert_candidate(
    db: Session,
    payload: CandidateUpsert,
    *,
    commit: bool = True,
) -> Candidate:
    boss_id = _normalize_boss_id(payload.boss_id)
    phone = _normalize_phone(payload.phone)
    email = _normalize_email(payload.email)
    existing: Candidate | None = None
    matched_merged_source = False
    if boss_id:
        existing = db.scalar(select(Candidate).where(Candidate.boss_id == boss_id))
    else:
        existing = db.scalar(
            select(Candidate).where(
                Candidate.fingerprint == payload.fingerprint,
                Candidate.boss_id.is_(None),
            )
        )
    if existing is not None:
        resolved = _resolve_merged_candidate(db, existing)
        matched_merged_source = resolved.id != existing.id
        existing = resolved
        if not matched_merged_source:
            existing.boss_id = boss_id or existing.boss_id
            existing.fingerprint = payload.fingerprint
        existing.name = payload.name
        existing.phone_normalized = phone or existing.phone_normalized
        existing.email_normalized = email or existing.email_normalized
        existing.age = payload.age
        existing.years_of_experience = payload.years_of_experience
        existing.job_segments_json = payload.job_segments_json
        existing.source = payload.source
        if commit:
            db.commit()
            db.refresh(existing)
        else:
            db.flush()
        return existing

    candidate = Candidate(
        boss_id=boss_id,
        fingerprint=payload.fingerprint,
        name=payload.name,
        phone_normalized=phone,
        email_normalized=email,
        age=payload.age,
        years_of_experience=payload.years_of_experience,
        job_segments_json=payload.job_segments_json,
        source=payload.source,
    )
    db.add(candidate)
    db.flush()
    _create_merge_suggestions(db, candidate, phone=phone, email=email)
    if commit:
        db.commit()
        db.refresh(candidate)
    return candidate


def get_candidate(db: Session, candidate_id: int) -> Candidate | None:
    candidate = db.get(Candidate, candidate_id)
    return _resolve_merged_candidate(db, candidate) if candidate is not None else None


def search_candidates(
    db: Session,
    q: str | None = None,
    *,
    job_id: int | None = None,
    status: str | None = None,
    min_score: int | None = None,
    needs_review: bool | None = None,
) -> list[Candidate]:
    stmt = (
        select(Candidate)
        .join(OutreachEvent, OutreachEvent.candidate_id == Candidate.id)
        .where(
            Candidate.merged_into_candidate_id.is_(None),
            OutreachEvent.status == "confirmed",
            OutreachEvent.greeted.is_(True),
        )
    )
    if job_id is not None or status is not None or min_score is not None or needs_review is not None:
        stmt = stmt.join(CandidateJob, CandidateJob.candidate_id == Candidate.id)
    if job_id is not None:
        stmt = stmt.where(CandidateJob.job_id == job_id)
    if status is not None:
        stmt = stmt.where(CandidateJob.status == status)
    if needs_review is True:
        stmt = stmt.where(CandidateJob.status == "needs_review")
    elif needs_review is False:
        stmt = stmt.where(CandidateJob.status != "needs_review")
    if min_score is not None:
        stmt = stmt.join(
            ScoreEvent,
            ScoreEvent.id == CandidateJob.latest_score_event_id,
        ).where(ScoreEvent.score >= min_score)
    rows = list(db.scalars(stmt.order_by(Candidate.id.desc())).unique().all())
    if not q:
        return rows
    needle = q.strip().lower()
    return [
        candidate
        for candidate in rows
        if needle in (candidate.name or "").lower()
        or needle in (candidate.boss_id or "").lower()
    ]


def get_or_create_candidate_job(
    db: Session,
    *,
    candidate_id: int,
    job_id: int,
) -> CandidateJob:
    existing = db.scalar(
        select(CandidateJob).where(
            CandidateJob.candidate_id == candidate_id,
            CandidateJob.job_id == job_id,
        )
    )
    if existing is not None:
        return existing
    link = CandidateJob(candidate_id=candidate_id, job_id=job_id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def list_candidate_jobs(db: Session, candidate_id: int) -> list[CandidateJob]:
    return list(
        db.scalars(
            select(CandidateJob)
            .where(CandidateJob.candidate_id == candidate_id)
            .order_by(CandidateJob.id)
        ).all()
    )
