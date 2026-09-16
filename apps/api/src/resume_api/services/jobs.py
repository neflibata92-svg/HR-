"""岗位服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.models import JobPosting
from resume_api.schemas import JobCreate, JobUpdate


def create_job(db: Session, payload: JobCreate) -> JobPosting:
    job = JobPosting(**payload.model_dump())
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
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return job
