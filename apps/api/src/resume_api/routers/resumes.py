"""简历上传路由。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from resume_api.core.auth import require_api_token
from resume_api.core.config import Settings, get_settings
from resume_api.core.db import get_db
from resume_api.schemas import ResumeOut
from resume_api.services.ingest import store_resume_file

router = APIRouter(prefix="/api/resumes", tags=["resumes"], dependencies=[Depends(require_api_token)])


@router.post("/upload", response_model=ResumeOut)
async def upload_resume(
    file: UploadFile = File(...),
    candidate_id: int | None = Form(default=None),
    source: str = Form(default="upload"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResumeOut:
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
        )
    finally:
        tmp_path.unlink(missing_ok=True)
    return ResumeOut.model_validate(resume)
