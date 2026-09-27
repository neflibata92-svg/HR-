from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from resume_api.core.config import Settings
from resume_api.models import (
    Candidate,
    CandidateJob,
    JobPosting,
    OutreachEvent,
    Resume,
    ResumeJobArchive,
    ScreeningTask,
)


class ResumeInboxError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_waiting_candidates(db: Session, *, owner_user_id: int) -> list[dict[str, object]]:
    rows = db.execute(
        select(Candidate, CandidateJob, JobPosting, OutreachEvent)
        .join(CandidateJob, CandidateJob.candidate_id == Candidate.id)
        .join(JobPosting, JobPosting.id == CandidateJob.job_id)
        .join(
            OutreachEvent,
            (OutreachEvent.candidate_id == Candidate.id)
            & (OutreachEvent.job_id == CandidateJob.job_id),
        )
        .join(ScreeningTask, ScreeningTask.id == OutreachEvent.task_id)
        .where(
            ScreeningTask.created_by_user_id == owner_user_id,
            OutreachEvent.status == "confirmed",
            OutreachEvent.greeted.is_(True),
            CandidateJob.status == "waiting_resume",
        )
        .order_by(Candidate.id, JobPosting.id, OutreachEvent.id.desc())
    ).all()
    grouped: dict[int, dict[str, object]] = {}
    seen_jobs: set[tuple[int, int]] = set()
    for candidate, link, job, event in rows:
        item = grouped.setdefault(
            candidate.id,
            {
                "candidate_id": candidate.id,
                "candidate_name": candidate.name,
                "boss_id": candidate.boss_id,
                "waiting_jobs": [],
            },
        )
        key = (candidate.id, job.id)
        if key in seen_jobs:
            continue
        seen_jobs.add(key)
        item["waiting_jobs"].append(
            {"job_id": job.id, "job_name": job.name, "contact_event_id": event.id}
        )
    return list(grouped.values())


def _owned_contact_event(
    db: Session,
    *,
    owner_user_id: int,
    candidate_id: int,
    contact_event_id: int,
) -> OutreachEvent:
    event = db.scalar(
        select(OutreachEvent)
        .join(ScreeningTask, ScreeningTask.id == OutreachEvent.task_id)
        .where(
            OutreachEvent.id == contact_event_id,
            OutreachEvent.candidate_id == candidate_id,
            OutreachEvent.status == "confirmed",
            OutreachEvent.greeted.is_(True),
            ScreeningTask.created_by_user_id == owner_user_id,
        )
        .with_for_update()
    )
    if event is None:
        raise ResumeInboxError(404, "waiting contact not found")
    return event


def store_agent_resume(
    db: Session,
    settings: Settings,
    *,
    src_path: Path,
    original_name: str,
    candidate_id: int,
    contact_event_id: int,
    owner_user_id: int,
) -> tuple[Resume, list[int], bool]:
    event = _owned_contact_event(
        db,
        owner_user_id=owner_user_id,
        candidate_id=candidate_id,
        contact_event_id=contact_event_id,
    )
    existing = db.scalar(
        select(Resume).where(
            Resume.candidate_id == candidate_id,
            Resume.contact_event_id == contact_event_id,
        )
    )
    if existing is not None:
        job_ids = list(
            db.scalars(
                select(ResumeJobArchive.job_id).where(
                    ResumeJobArchive.resume_id == existing.id
                )
            ).all()
        )
        if not job_ids:
            job_ids = list(
                db.scalars(
                    select(CandidateJob.job_id)
                    .join(JobPosting, JobPosting.id == CandidateJob.job_id)
                    .where(
                        CandidateJob.candidate_id == candidate_id,
                        CandidateJob.status == "pending_job_assignment",
                    )
                    .order_by(CandidateJob.job_id)
                ).all()
            )
        return existing, job_ids, True

    waiting_links = list(
        db.scalars(
            select(CandidateJob)
            .join(OutreachEvent, OutreachEvent.job_id == CandidateJob.job_id)
            .join(ScreeningTask, ScreeningTask.id == OutreachEvent.task_id)
            .where(
                CandidateJob.candidate_id == candidate_id,
                CandidateJob.status == "waiting_resume",
                OutreachEvent.candidate_id == candidate_id,
                OutreachEvent.status == "confirmed",
                OutreachEvent.greeted.is_(True),
                ScreeningTask.created_by_user_id == owner_user_id,
            )
            .distinct()
            .order_by(CandidateJob.job_id)
            .with_for_update()
        ).all()
    )
    if not waiting_links:
        raise ResumeInboxError(409, "candidate is not waiting for resume")

    file_hash = _sha256(src_path)
    storage = Path(settings.storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    safe_name = Path(original_name).name or "resume.pdf"
    temp_dest = storage / f".{uuid.uuid4().hex}_{safe_name}"
    final_dest = storage / f"{uuid.uuid4().hex}_{safe_name}"
    shutil.copy2(src_path, temp_dest)
    try:
        next_version = (
            db.scalar(
                select(Resume.version_number)
                .where(Resume.candidate_id == candidate_id)
                .order_by(Resume.version_number.desc())
                .limit(1)
            )
            or 0
        ) + 1
        assignment_status = "assigned" if len(waiting_links) == 1 else "pending_job_assignment"
        resume = Resume(
            candidate_id=candidate_id,
            version_number=next_version,
            original_filename=safe_name,
            file_path=str(final_dest),
            file_hash=file_hash,
            parsed_text="",
            source="boss_attachment",
            parse_status="not_parsed",
            assignment_status=assignment_status,
            contact_event_id=contact_event_id,
            uploaded_by_user_id=owner_user_id,
        )
        db.add(resume)
        db.flush()
        job_ids = [link.job_id for link in waiting_links]
        if len(waiting_links) == 1:
            link = waiting_links[0]
            db.add(
                ResumeJobArchive(
                    resume_id=resume.id,
                    job_id=link.job_id,
                    source="boss_attachment",
                    file_hash=file_hash,
                    assigned_by_user_id=owner_user_id,
                )
            )
            link.status = "resume_received"
            link.active_resume_id = resume.id
        else:
            for link in waiting_links:
                link.status = "pending_job_assignment"
        event.attachment_received = True
        temp_dest.replace(final_dest)
        db.commit()
        db.refresh(resume)
        return resume, job_ids, False
    except Exception:
        db.rollback()
        temp_dest.unlink(missing_ok=True)
        final_dest.unlink(missing_ok=True)
        raise


def assign_resume_job(
    db: Session,
    *,
    resume_id: int,
    job_id: int,
    owner_user_id: int,
) -> Resume:
    resume = db.scalar(select(Resume).where(Resume.id == resume_id).with_for_update())
    if resume is None or resume.candidate_id is None:
        raise ResumeInboxError(404, "resume not found")
    if resume.assignment_status == "assigned":
        existing = db.scalar(
            select(ResumeJobArchive).where(
                ResumeJobArchive.resume_id == resume.id,
                ResumeJobArchive.job_id == job_id,
            )
        )
        if existing is not None:
            return resume
        raise ResumeInboxError(409, "resume already assigned")
    allowed = db.scalar(
        select(CandidateJob)
        .join(OutreachEvent, OutreachEvent.job_id == CandidateJob.job_id)
        .join(ScreeningTask, ScreeningTask.id == OutreachEvent.task_id)
        .where(
            CandidateJob.candidate_id == resume.candidate_id,
            CandidateJob.job_id == job_id,
            CandidateJob.status == "pending_job_assignment",
            OutreachEvent.candidate_id == resume.candidate_id,
            OutreachEvent.status == "confirmed",
            ScreeningTask.created_by_user_id == owner_user_id,
        )
        .with_for_update()
    )
    if allowed is None:
        raise ResumeInboxError(404, "pending job assignment not found")
    db.add(
        ResumeJobArchive(
            resume_id=resume.id,
            job_id=job_id,
            source="boss_attachment",
            file_hash=resume.file_hash or _sha256(Path(resume.file_path)),
            assigned_by_user_id=owner_user_id,
        )
    )
    links = list(
        db.scalars(
            select(CandidateJob)
            .where(
                CandidateJob.candidate_id == resume.candidate_id,
                CandidateJob.status == "pending_job_assignment",
            )
            .with_for_update()
        ).all()
    )
    for link in links:
        if link.job_id == job_id:
            link.status = "resume_received"
            link.active_resume_id = resume.id
        else:
            link.status = "waiting_resume"
    resume.assignment_status = "assigned"
    db.commit()
    db.refresh(resume)
    return resume


def archived_job_ids(db: Session, resume_id: int) -> list[int]:
    return list(
        db.scalars(
            select(ResumeJobArchive.job_id)
            .where(ResumeJobArchive.resume_id == resume_id)
            .order_by(ResumeJobArchive.job_id)
        ).all()
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
