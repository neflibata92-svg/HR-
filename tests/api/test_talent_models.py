from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_api.core.config import Settings
from resume_api.core.db import Base, create_engine_from_settings
from resume_api.models import (
    Candidate,
    CandidateJob,
    JobPosting,
    OutreachEvent,
    Resume,
    ScreeningTask,
    ScreeningTaskItem,
    User,
)


@pytest.fixture()
def db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'talent.db'}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session, engine


def seed_core(db: Session) -> tuple[User, Candidate, Candidate, JobPosting, JobPosting]:
    user = User(username="owner", password_hash="hash", role="member")
    first_candidate = Candidate(fingerprint="candidate-1", name="甲")
    second_candidate = Candidate(fingerprint="candidate-2", name="乙")
    first_job = JobPosting(name="工程师", jd_text="Python")
    second_job = JobPosting(name="产品经理", jd_text="产品")
    db.add_all([user, first_candidate, second_candidate, first_job, second_job])
    db.commit()
    return user, first_candidate, second_candidate, first_job, second_job


def test_application_sqlite_engine_enforces_foreign_keys(tmp_path: Path) -> None:
    engine = create_engine_from_settings(
        Settings(database_url=f"sqlite:///{tmp_path / 'factory.db'}")
    )
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(CandidateJob(candidate_id=999, job_id=999))
        with pytest.raises(IntegrityError):
            session.commit()


def test_claimed_resume_requires_version_number(db) -> None:
    session, _engine = db
    _user, candidate, _other, _job, _other_job = seed_core(session)
    session.add(
        Resume(
            candidate_id=candidate.id,
            version_number=None,
            file_path="/tmp/unversioned.pdf",
            source="upload",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_candidate_job_is_unique_per_candidate_and_job(db) -> None:
    session, _engine = db
    _user, candidate, _other, first_job, second_job = seed_core(session)
    session.add_all(
        [
            CandidateJob(candidate_id=candidate.id, job_id=first_job.id, status="scored"),
            CandidateJob(candidate_id=candidate.id, job_id=second_job.id, status="needs_review"),
        ]
    )
    session.commit()

    session.add(CandidateJob(candidate_id=candidate.id, job_id=first_job.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    links = session.scalars(
        select(CandidateJob).where(CandidateJob.candidate_id == candidate.id)
    ).all()
    assert {link.status for link in links} == {"scored", "needs_review"}


def test_resume_versions_and_hashes_are_unique_within_candidate(db) -> None:
    session, _engine = db
    _user, first, second, _first_job, _second_job = seed_core(session)
    session.add_all(
        [
            Resume(
                candidate_id=first.id,
                version_number=1,
                original_filename="v1.pdf",
                file_path="/tmp/v1.pdf",
                file_hash="same-hash",
                source="upload",
            ),
            Resume(
                candidate_id=second.id,
                version_number=1,
                original_filename="v1.pdf",
                file_path="/tmp/other-v1.pdf",
                file_hash="same-hash",
                source="upload",
            ),
            Resume(file_path="/tmp/unclaimed.pdf", source="watch"),
        ]
    )
    session.commit()

    session.add(
        Resume(
            candidate_id=first.id,
            version_number=1,
            original_filename="duplicate-version.pdf",
            file_path="/tmp/duplicate-version.pdf",
            file_hash="different-hash",
            source="upload",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        Resume(
            candidate_id=first.id,
            version_number=2,
            original_filename="duplicate-hash.pdf",
            file_path="/tmp/duplicate-hash.pdf",
            file_hash="same-hash",
            source="upload",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_screening_task_count_and_item_idempotency_are_database_constraints(db) -> None:
    session, _engine = db
    user, candidate, _other, job, _other_job = seed_core(session)
    task = ScreeningTask(
        job_id=job.id,
        created_by_user_id=user.id,
        requested_count=1,
        critical_fields_json='["experience"]',
    )
    session.add(task)
    session.commit()

    link = CandidateJob(candidate_id=candidate.id, job_id=job.id)
    session.add(link)
    session.commit()
    session.add(
        ScreeningTaskItem(
            task_id=task.id,
            candidate_id=candidate.id,
            candidate_job_id=link.id,
            position_index=0,
        )
    )
    session.commit()

    session.add(
        ScreeningTaskItem(
            task_id=task.id,
            candidate_id=candidate.id,
            candidate_job_id=link.id,
            position_index=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        ScreeningTask(
            job_id=job.id,
            created_by_user_id=user.id,
            requested_count=0,
            critical_fields_json='["experience"]',
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_outreach_keeps_multiple_attempts_and_global_status_index(db) -> None:
    session, engine = db
    _user, candidate, _other, job, _other_job = seed_core(session)
    session.add_all(
        [
            OutreachEvent(candidate_id=candidate.id, job_id=job.id, status="failed"),
            OutreachEvent(candidate_id=candidate.id, job_id=job.id, status="confirmed"),
        ]
    )
    session.commit()

    attempts = session.scalars(
        select(OutreachEvent)
        .where(OutreachEvent.candidate_id == candidate.id)
        .order_by(OutreachEvent.id)
    ).all()
    assert [attempt.status for attempt in attempts] == ["failed", "confirmed"]

    unique_sets = {
        tuple(constraint["column_names"])
        for constraint in inspect(engine).get_unique_constraints("outreach_events")
    }
    assert ("candidate_id", "job_id") not in unique_sets
    indexes = {
        tuple(index["column_names"])
        for index in inspect(engine).get_indexes("outreach_events")
    }
    assert ("candidate_id", "status") in indexes
