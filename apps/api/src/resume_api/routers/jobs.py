"""岗位路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from resume_api.core.auth import require_password_change_complete
from resume_api.core.db import get_db
from resume_api.schemas import JobCreate, JobOut, JobUpdate
from resume_api.services import jobs as jobs_service

router = APIRouter(
    prefix="/api/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_password_change_complete)],
)


@router.get("", response_model=list[JobOut])
def get_jobs(db: Session = Depends(get_db)) -> list[JobOut]:
    return [JobOut.model_validate(j) for j in jobs_service.list_jobs(db)]


@router.get("/enabled", response_model=list[JobOut])
def get_enabled_jobs(db: Session = Depends(get_db)) -> list[JobOut]:
    return [JobOut.model_validate(j) for j in jobs_service.list_enabled_jobs(db)]


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def post_job(payload: JobCreate, db: Session = Depends(get_db)) -> JobOut:
    return JobOut.model_validate(jobs_service.create_job(db, payload))


@router.patch("/{job_id}", response_model=JobOut)
def patch_job(job_id: int, payload: JobUpdate, db: Session = Depends(get_db)) -> JobOut:
    job = jobs_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobOut.model_validate(jobs_service.update_job(db, job, payload))
