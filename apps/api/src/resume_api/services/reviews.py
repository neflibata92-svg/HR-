"""人工复核队列、复核动作与手动重评事务。"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.config import Settings
from resume_api.models import Candidate, CandidateJob, JobPosting, Resume, ScoreEvent
from resume_api.schemas import ReEvaluateRequest
from resume_api.services import llm as llm_service
from resume_api.services.audit import add_audit_event


class ReviewError(ValueError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _json_list(raw: str | None) -> list:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def list_reviews(db: Session, *, job_id: int | None = None) -> list[dict[str, object]]:
    stmt = (
        select(CandidateJob, Candidate, JobPosting, ScoreEvent)
        .join(Candidate, Candidate.id == CandidateJob.candidate_id)
        .join(JobPosting, JobPosting.id == CandidateJob.job_id)
        .join(ScoreEvent, ScoreEvent.id == CandidateJob.latest_score_event_id)
        .where(CandidateJob.status == "needs_review")
        .order_by(ScoreEvent.created_at.desc(), CandidateJob.id.desc())
    )
    if job_id is not None:
        stmt = stmt.where(CandidateJob.job_id == job_id)
    result: list[dict[str, object]] = []
    for link, candidate, job, score in db.execute(stmt).all():
        critical = _json_list(score.critical_fields_json)
        missing_critical = [
            item.get("key")
            for item in critical
            if isinstance(item, dict) and item.get("present") is False and item.get("key")
        ]
        result.append(
            {
                "candidate_job_id": link.id,
                "candidate": {"id": candidate.id, "name": candidate.name},
                "job": {"id": job.id, "name": job.name},
                "score": score.score,
                "reason": score.reason,
                "threshold": job.score_threshold,
                "confidence": score.confidence,
                "missing_critical_fields": missing_critical,
                "estimated_fields": _json_list(score.estimated_fields_json),
                "evidence": _json_list(score.evidence_json),
                "model": score.model,
                "task_id": score.task_id,
                "scored_at": score.created_at,
            }
        )
    return result


def apply_review_action(
    db: Session,
    candidate_job_id: int,
    *,
    action: str,
    actor_user_id: int,
) -> CandidateJob:
    link = db.scalar(
        select(CandidateJob)
        .where(CandidateJob.id == candidate_job_id)
        .with_for_update()
    )
    if link is None:
        raise ReviewError(404, "candidate job not found")
    if link.status != "needs_review":
        raise ReviewError(409, "candidate job is not pending review")
    if action == "keep_pending":
        link.status = "needs_review"
        audit_action = "candidate_job.review_kept_pending"
    elif action == "archive":
        link.status = "archived"
        audit_action = "candidate_job.review_archived"
    else:
        raise ReviewError(422, "invalid review action")
    add_audit_event(
        db,
        actor_user_id=actor_user_id,
        action=audit_action,
        entity_type="candidate_job",
        entity_id=str(link.id),
        details={"candidate_id": link.candidate_id, "job_id": link.job_id},
    )
    db.commit()
    db.refresh(link)
    return link


def re_evaluate(
    db: Session,
    candidate_id: int,
    job_id: int,
    payload: ReEvaluateRequest,
    *,
    settings: Settings,
    actor_user_id: int,
) -> ScoreEvent:
    link = db.scalar(
        select(CandidateJob)
        .where(
            CandidateJob.candidate_id == candidate_id,
            CandidateJob.job_id == job_id,
        )
        .with_for_update()
    )
    if link is None:
        raise ReviewError(404, "candidate job not found")
    candidate = db.get(Candidate, candidate_id)
    job = db.get(JobPosting, job_id)
    resume = db.get(Resume, payload.resume_id)
    if resume is None or resume.candidate_id != candidate_id:
        raise ReviewError(422, "resume does not belong to candidate")
    result = llm_service.score_candidate(
        settings,
        job.jd_text,
        resume.parsed_text,
    )
    result = llm_service.finalize_score(
        result,
        threshold=job.score_threshold,
    )
    decision = result.decision
    event = ScoreEvent(
        candidate_id=candidate_id,
        job_id=job_id,
        candidate_job_id=link.id,
        resume_id=resume.id,
        hard_filter_passed=True,
        hard_filter_reasons="[]",
        score=result.score,
        reason=result.reason,
        evidence_json=json.dumps(result.evidence, ensure_ascii=False),
        missing_fields_json=json.dumps(result.missing_fields, ensure_ascii=False),
        estimated_fields_json=json.dumps(result.estimated_fields, ensure_ascii=False),
        critical_fields_json=json.dumps(
            [item.model_dump() for item in result.critical_fields], ensure_ascii=False
        ),
        confidence=result.confidence,
        decision=decision,
        model=result.model,
    )
    db.add(event)
    db.flush()
    link.latest_score_event_id = event.id
    link.active_resume_id = resume.id
    link.review_reason_json = "[]"
    link.status = "needs_review" if decision == "needs_review" else "scored"
    add_audit_event(
        db,
        actor_user_id=actor_user_id,
        action="candidate_job.re_evaluated",
        entity_type="candidate_job",
        entity_id=str(link.id),
        details={
            "candidate_id": candidate_id,
            "job_id": job_id,
            "resume_id": resume.id,
            "score_event_id": event.id,
            "decision": decision,
        },
    )
    db.commit()
    db.refresh(event)
    return event
