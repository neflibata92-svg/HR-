"""简历入库。"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_api.core.config import Settings
from resume_api.models import Candidate, CandidateJob, JobPosting, Resume, ResumeJobArchive
from resume_api.parsing import parse_resume_file


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _claim_archived_resume(
    db: Session,
    *,
    resume: Resume,
    candidate: Candidate,
    src_path: Path,
    source: str,
    uploaded_by_user_id: int | None,
) -> Resume:
    if resume.candidate_id == candidate.id:
        return resume
    if resume.candidate_id is not None:
        raise ValueError("resume already belongs to another candidate")
    latest = db.scalar(
        select(Resume)
        .where(Resume.candidate_id == candidate.id)
        .order_by(Resume.version_number.desc(), Resume.id.desc())
    )
    parsed_text, parse_status = parse_resume_file(src_path)
    version_number = (latest.version_number or 0) + 1 if latest is not None else 1
    result = db.execute(
        update(Resume)
        .where(Resume.id == resume.id, Resume.candidate_id.is_(None))
        .values(
            candidate_id=candidate.id,
            version_number=version_number,
            supersedes_resume_id=latest.id if latest is not None else None,
            parsed_text=parsed_text,
            parse_status=parse_status,
            source=source,
            uploaded_by_user_id=uploaded_by_user_id,
        )
    )
    if result.rowcount != 1:
        db.expire_all()
        winner = db.get(Resume, resume.id)
        if winner is None:
            raise ValueError("archived resume not found")
        if winner.candidate_id != candidate.id:
            raise ValueError("resume already belongs to another candidate")
        return winner
    db.expire(resume)
    db.refresh(resume)
    return resume


def _associate_resume_with_job(
    db: Session,
    *,
    resume: Resume,
    candidate_id: int,
    job_id: int,
    source: str,
    uploaded_by_user_id: int | None,
) -> None:
    if db.get(JobPosting, job_id) is None:
        raise ValueError("job not found")
    link = db.scalar(
        select(CandidateJob).where(
            CandidateJob.candidate_id == candidate_id,
            CandidateJob.job_id == job_id,
        )
    )
    if link is None:
        try:
            with db.begin_nested():
                db.add(CandidateJob(candidate_id=candidate_id, job_id=job_id))
                db.flush()
        except IntegrityError:
            link = db.scalar(
                select(CandidateJob).where(
                    CandidateJob.candidate_id == candidate_id,
                    CandidateJob.job_id == job_id,
                )
            )
            if link is None:
                raise
    archive = db.scalar(
        select(ResumeJobArchive).where(
            ResumeJobArchive.resume_id == resume.id,
            ResumeJobArchive.job_id == job_id,
        )
    )
    if archive is None:
        db.add(
            ResumeJobArchive(
                resume_id=resume.id,
                job_id=job_id,
                source=source,
                file_hash=resume.file_hash or "",
                assigned_by_user_id=uploaded_by_user_id,
            )
        )


def store_resume_file(
    db: Session,
    settings: Settings,
    *,
    src_path: Path,
    original_name: str,
    source: str,
    candidate_id: int | None = None,
    job_id: int | None = None,
    uploaded_by_user_id: int | None = None,
) -> Resume:
    candidate: Candidate | None = None
    if candidate_id is not None:
        candidate = db.scalar(
            select(Candidate).where(Candidate.id == candidate_id).with_for_update()
        )
        if candidate is None:
            raise ValueError("candidate not found")
    if job_id is not None:
        if candidate_id is None:
            raise ValueError("candidate is required for job assignment")
        if db.get(JobPosting, job_id) is None:
            raise ValueError("job not found")

    file_hash = _sha256(src_path)
    if candidate is not None and job_id is not None:
        archived = db.scalar(
            select(ResumeJobArchive).where(
                ResumeJobArchive.job_id == job_id,
                ResumeJobArchive.file_hash == file_hash,
            )
        )
        if archived is not None:
            existing = db.get(Resume, archived.resume_id)
            if existing is None:
                raise ValueError("archived resume not found")
            existing = _claim_archived_resume(
                db,
                resume=existing,
                candidate=candidate,
                src_path=src_path,
                source=source,
                uploaded_by_user_id=uploaded_by_user_id,
            )
            _associate_resume_with_job(
                db,
                resume=existing,
                candidate_id=candidate.id,
                job_id=job_id,
                source=source,
                uploaded_by_user_id=uploaded_by_user_id,
            )
            db.commit()
            db.refresh(existing)
            return existing
    if candidate is not None:
        existing = db.scalar(
            select(Resume).where(
                Resume.candidate_id == candidate_id,
                Resume.file_hash == file_hash,
            )
        )
        if existing is not None:
            if job_id is not None:
                _associate_resume_with_job(
                    db,
                    resume=existing,
                    candidate_id=candidate.id,
                    job_id=job_id,
                    source=source,
                    uploaded_by_user_id=uploaded_by_user_id,
                )
                db.commit()
            return existing

    storage = Path(settings.storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    safe_name = Path(original_name).name or "resume.bin"
    temp_dest = storage / f".{uuid.uuid4().hex}_{safe_name}"
    final_dest = storage / f"{uuid.uuid4().hex}_{safe_name}"
    shutil.copy2(src_path, temp_dest)
    try:
        parsed_text, parse_status = parse_resume_file(temp_dest)
        version_number: int | None = None
        supersedes_resume_id: int | None = None
        if candidate_id is not None:
            latest = db.scalar(
                select(Resume)
                .where(Resume.candidate_id == candidate_id)
                .order_by(Resume.version_number.desc(), Resume.id.desc())
            )
            version_number = (latest.version_number or 0) + 1 if latest is not None else 1
            supersedes_resume_id = latest.id if latest is not None else None

        resume = Resume(
            candidate_id=candidate_id,
            version_number=version_number,
            original_filename=safe_name,
            file_path=str(final_dest),
            file_hash=file_hash,
            parsed_text=parsed_text,
            source=source,
            parse_status=parse_status,
            uploaded_by_user_id=uploaded_by_user_id,
            supersedes_resume_id=supersedes_resume_id,
        )
        db.add(resume)
        db.flush()
        db.refresh(resume)
        if job_id is not None and candidate is not None:
            _associate_resume_with_job(
                db,
                resume=resume,
                candidate_id=candidate.id,
                job_id=job_id,
                source=source,
                uploaded_by_user_id=uploaded_by_user_id,
            )
        temp_dest.replace(final_dest)
        db.commit()
        return resume
    except IntegrityError:
        db.rollback()
        temp_dest.unlink(missing_ok=True)
        final_dest.unlink(missing_ok=True)
        if job_id is None or candidate is None:
            raise
        archived = db.scalar(
            select(ResumeJobArchive).where(
                ResumeJobArchive.job_id == job_id,
                ResumeJobArchive.file_hash == file_hash,
            )
        )
        if archived is None:
            raise
        existing = db.get(Resume, archived.resume_id)
        if existing is None:
            raise ValueError("archived resume not found")
        existing = _claim_archived_resume(
            db,
            resume=existing,
            candidate=candidate,
            src_path=src_path,
            source=source,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        _associate_resume_with_job(
            db,
            resume=existing,
            candidate_id=candidate.id,
            job_id=job_id,
            source=source,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        db.commit()
        db.refresh(existing)
        return existing
    except Exception:
        db.rollback()
        temp_dest.unlink(missing_ok=True)
        final_dest.unlink(missing_ok=True)
        raise


MAX_MANUAL_PDF_BYTES = 20 * 1024 * 1024


def store_manual_resume_for_job(
    db: Session,
    settings: Settings,
    *,
    src_path: Path,
    original_name: str,
    job_id: int,
    uploaded_by_user_id: int,
) -> tuple[Resume, bool]:
    if db.get(JobPosting, job_id) is None:
        raise ValueError("job not found")
    file_hash = _sha256(src_path)
    existing_archive = db.scalar(
        select(ResumeJobArchive).where(
            ResumeJobArchive.job_id == job_id,
            ResumeJobArchive.file_hash == file_hash,
        )
    )
    if existing_archive is not None:
        existing = db.get(Resume, existing_archive.resume_id)
        if existing is None:
            raise ValueError("archived resume not found")
        return existing, True

    storage = Path(settings.storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    safe_name = Path(original_name).name or "resume.pdf"
    temp_dest = storage / f".{uuid.uuid4().hex}_{safe_name}"
    final_dest = storage / f"{uuid.uuid4().hex}_{safe_name}"
    shutil.copy2(src_path, temp_dest)
    try:
        resume = Resume(
            candidate_id=None,
            version_number=None,
            original_filename=safe_name,
            file_path=str(final_dest),
            file_hash=file_hash,
            parsed_text="",
            source="manual_upload",
            parse_status="not_parsed",
            assignment_status="assigned",
            uploaded_by_user_id=uploaded_by_user_id,
        )
        db.add(resume)
        db.flush()
        db.add(
            ResumeJobArchive(
                resume_id=resume.id,
                job_id=job_id,
                source="manual_upload",
                file_hash=file_hash,
                assigned_by_user_id=uploaded_by_user_id,
            )
        )
        db.flush()
        temp_dest.replace(final_dest)
        db.commit()
        db.refresh(resume)
        return resume, False
    except IntegrityError:
        db.rollback()
        temp_dest.unlink(missing_ok=True)
        final_dest.unlink(missing_ok=True)
        existing_archive = db.scalar(
            select(ResumeJobArchive).where(
                ResumeJobArchive.job_id == job_id,
                ResumeJobArchive.file_hash == file_hash,
            )
        )
        if existing_archive is None:
            raise
        existing = db.get(Resume, existing_archive.resume_id)
        if existing is None:
            raise ValueError("archived resume not found")
        return existing, True
    except Exception:
        db.rollback()
        temp_dest.unlink(missing_ok=True)
        final_dest.unlink(missing_ok=True)
        raise
