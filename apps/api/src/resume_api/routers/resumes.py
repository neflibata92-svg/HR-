"""简历上传与查询路由。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.auth import CurrentUser, require_password_change_complete
from resume_api.core.config import Settings, get_settings
from resume_api.core.db import get_db
from resume_api.models import Candidate, CandidateJob, JobPosting, Resume, ResumeJobArchive
from resume_api.schemas import (
    AgentResumeUploadOut,
    ResumeBatchImportItemOut,
    ResumeBatchImportOut,
    ResumeBatchImportSummaryOut,
    ResumeJobAssignmentRequest,
    ResumeOut,
)
from resume_api.services import resume_inbox as resume_inbox_service
from resume_api.services.ingest import (
    MAX_MANUAL_PDF_BYTES,
    store_manual_resume_for_job,
    store_resume_file,
)

router = APIRouter(
    prefix="/api/resumes",
    tags=["resumes"],
    dependencies=[Depends(require_password_change_complete)],
)


@router.get("", response_model=list[ResumeOut])
def list_resumes(
    candidate_id: int | None = Query(default=None),
    job_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ResumeOut]:
    if job_id is not None:
        archived_resume_ids = select(ResumeJobArchive.resume_id).where(
            ResumeJobArchive.job_id == job_id
        )
        stmt = select(Resume).where(Resume.id.in_(archived_resume_ids))
        if candidate_id is not None:
            stmt = stmt.where(Resume.candidate_id == candidate_id)
    else:
        stmt = select(Resume)
        if candidate_id is not None:
            stmt = stmt.where(Resume.candidate_id == candidate_id)
    rows = db.scalars(
        stmt.order_by(
            Resume.version_number.desc().nulls_last(),
            Resume.created_at.desc(),
            Resume.id.desc(),
        )
    ).all()
    return [ResumeOut.model_validate(resume) for resume in rows]


@router.get("/{resume_id}/file", response_class=FileResponse)
def get_resume_file(
    resume_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    resume = db.get(Resume, resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="resume not found")
    file_path = Path(resume.file_path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="resume file not found")
    media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "application/octet-stream"
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=resume.original_filename or file_path.name,
    )


@router.post("/agent-upload", response_model=AgentResumeUploadOut)
async def upload_agent_resume(
    response: Response,
    file: UploadFile = File(...),
    candidate_id: int = Form(...),
    contact_event_id: int = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_password_change_complete),
) -> AgentResumeUploadOut:
    original_name = Path(file.filename or "resume.pdf").name
    content = await file.read(MAX_MANUAL_PDF_BYTES + 1)
    if Path(original_name).suffix.lower() != ".pdf":
        raise HTTPException(status_code=422, detail="仅支持 PDF 文件")
    if not content or not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="文件内容不是有效 PDF")
    if len(content) > MAX_MANUAL_PDF_BYTES:
        raise HTTPException(status_code=413, detail="单个 PDF 不能超过 20 MB")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        resume, job_ids, hit = resume_inbox_service.store_agent_resume(
            db,
            settings,
            src_path=tmp_path,
            original_name=original_name,
            candidate_id=candidate_id,
            contact_event_id=contact_event_id,
            owner_user_id=user.id,
        )
    except resume_inbox_service.ResumeInboxError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    response.status_code = status.HTTP_200_OK if hit else status.HTTP_201_CREATED
    return AgentResumeUploadOut(
        resume_id=resume.id,
        candidate_id=candidate_id,
        assignment_status=resume.assignment_status,
        job_ids=job_ids,
        idempotent_hit=hit,
    )


@router.post("/{resume_id}/assign-job", response_model=AgentResumeUploadOut)
def assign_resume_job(
    resume_id: int,
    payload: ResumeJobAssignmentRequest,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_password_change_complete),
) -> AgentResumeUploadOut:
    try:
        resume = resume_inbox_service.assign_resume_job(
            db,
            resume_id=resume_id,
            job_id=payload.job_id,
            owner_user_id=user.id,
        )
    except resume_inbox_service.ResumeInboxError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AgentResumeUploadOut(
        resume_id=resume.id,
        candidate_id=resume.candidate_id,
        assignment_status=resume.assignment_status,
        job_ids=resume_inbox_service.archived_job_ids(db, resume.id),
    )


@router.post("/batch-import", response_model=ResumeBatchImportOut)
async def batch_import_resumes(
    files: list[UploadFile] = File(...),
    job_id: int = Form(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ResumeBatchImportOut:
    if db.get(JobPosting, job_id) is None:
        raise HTTPException(status_code=404, detail="job not found")
    items: list[ResumeBatchImportItemOut] = []
    counts = {"imported": 0, "duplicate": 0, "failed": 0}
    for file in files:
        original_name = Path(file.filename or "resume.pdf").name
        error = ""
        content = await file.read(MAX_MANUAL_PDF_BYTES + 1)
        if Path(original_name).suffix.lower() != ".pdf":
            error = "仅支持 PDF 文件"
        elif not content:
            error = "PDF 文件为空"
        elif len(content) > MAX_MANUAL_PDF_BYTES:
            error = "单个 PDF 不能超过 20 MB"
        elif not content.startswith(b"%PDF-"):
            error = "文件内容不是有效 PDF"
        if error:
            counts["failed"] += 1
            items.append(
                ResumeBatchImportItemOut(
                    original_filename=original_name,
                    status="failed",
                    error=error,
                )
            )
            continue

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            resume, duplicate = store_manual_resume_for_job(
                db,
                settings,
                src_path=tmp_path,
                original_name=original_name,
                job_id=job_id,
                uploaded_by_user_id=user.id,
            )
            item_status = "duplicate" if duplicate else "imported"
            counts[item_status] += 1
            items.append(
                ResumeBatchImportItemOut(
                    original_filename=original_name,
                    status=item_status,
                    resume_id=resume.id,
                )
            )
        except Exception:
            db.rollback()
            counts["failed"] += 1
            items.append(
                ResumeBatchImportItemOut(
                    original_filename=original_name,
                    status="failed",
                    error="文件保存失败，请重试",
                )
            )
        finally:
            tmp_path.unlink(missing_ok=True)
    return ResumeBatchImportOut(
        job_id=job_id,
        summary=ResumeBatchImportSummaryOut(**counts),
        items=items,
    )


@router.post("/upload", response_model=ResumeOut)
async def upload_resume(
    file: UploadFile = File(...),
    candidate_id: int = Form(...),
    job_id: int | None = Form(default=None),
    source: str = Form(default="upload"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_password_change_complete),
) -> ResumeOut:
    if db.get(Candidate, candidate_id) is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    suffix = Path(file.filename or "resume.bin").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        resume = store_resume_file(
            db,
            settings,
            src_path=tmp_path,
            original_name=file.filename or "resume.bin",
            source=source,
            candidate_id=candidate_id,
            job_id=job_id,
            uploaded_by_user_id=user.id,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    return ResumeOut.model_validate(resume)
