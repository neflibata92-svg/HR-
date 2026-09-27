"""岗位服务。"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.models import JobPosting
from resume_api.schemas import JobCreate, JobUpdate


_VIRTUAL_FIELDS = {"critical_fields", "critical_fields_confirmed"}


def create_job(db: Session, payload: JobCreate) -> JobPosting:
    values = payload.model_dump(exclude=_VIRTUAL_FIELDS)
    job = JobPosting(
        **values,
        critical_fields_json=json.dumps(
            [item.model_dump() for item in payload.critical_fields], ensure_ascii=False
        ),
        critical_fields_confirmed_at=(
            datetime.now(timezone.utc) if payload.critical_fields_confirmed else None
        ),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_jobs(db: Session) -> list[JobPosting]:
    return list(db.scalars(select(JobPosting).order_by(JobPosting.id.desc())).all())


def list_enabled_jobs(db: Session) -> list[JobPosting]:
    return list(
        db.scalars(select(JobPosting).where(JobPosting.enabled.is_(True)).order_by(JobPosting.id)).all()
    )


def get_job(db: Session, job_id: int) -> JobPosting | None:
    return db.get(JobPosting, job_id)


def update_job(db: Session, job: JobPosting, payload: JobUpdate) -> JobPosting:
    values = payload.model_dump(exclude_unset=True, exclude=_VIRTUAL_FIELDS)
    for key, value in values.items():
        setattr(job, key, value)
    if payload.critical_fields is not None:
        job.critical_fields_json = json.dumps(
            [item.model_dump() for item in payload.critical_fields], ensure_ascii=False
        )
        if payload.critical_fields_confirmed is None:
            job.critical_fields_confirmed_at = None
    if payload.critical_fields_confirmed is not None:
        job.critical_fields_confirmed_at = (
            datetime.now(timezone.utc) if payload.critical_fields_confirmed else None
        )
    db.commit()
    db.refresh(job)
    return job


def critical_fields(job: JobPosting) -> list[dict[str, object]]:
    try:
        value = json.loads(job.critical_fields_json or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def readiness(job: JobPosting) -> dict[str, object]:
    missing: list[str] = []
    if not job.jd_text.strip():
        missing.append("jd_text")
    if not job.boss_entry_url.strip():
        missing.append("boss_entry_url")
    if job.default_requested_count is None:
        missing.append("default_requested_count")
    return {"ready": not missing and job.enabled, "missing": missing}


def job_out(job: JobPosting) -> dict[str, object]:
    return {
        "id": job.id,
        "name": job.name,
        "jd_text": job.jd_text,
        "score_threshold": job.score_threshold,
        "greet_template": job.greet_template,
        "boss_entry_url": job.boss_entry_url,
        "hourly_greet_limit": job.hourly_greet_limit,
        "min_action_delay_ms": job.min_action_delay_ms,
        "max_action_delay_ms": job.max_action_delay_ms,
        "default_requested_count": job.default_requested_count,
        "critical_fields": critical_fields(job),
        "critical_fields_confirmed": job.critical_fields_confirmed_at is not None,
        "readiness": readiness(job),
        "enabled": job.enabled,
        "created_at": job.created_at,
    }
