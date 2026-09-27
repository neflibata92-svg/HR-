from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from resume_api import models
from resume_api.core.db import Base


def test_core_archive_models_expose_required_fields_and_tables(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert {"screening_records", "resume_job_archives"} <= set(inspector.get_table_names())
    assert {
        "default_requested_count",
        "critical_fields_json",
        "critical_fields_confirmed_at",
    } <= {column["name"] for column in inspector.get_columns("job_postings")}
    assert {"contact_event_id", "assignment_status"} <= {
        column["name"] for column in inspector.get_columns("resumes")
    }
    assert {"assigned_agent_run_id", "control_requested_at"} <= {
        column["name"] for column in inspector.get_columns("screening_tasks")
    }
    assert {
        "owner_user_id",
        "current_task_id",
        "current_job_id",
        "availability",
        "boss_login_status",
    } <= {column["name"] for column in inspector.get_columns("agent_runs")}


def test_resume_archive_constraints_allow_manual_resume_and_cross_job_reuse(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'archives.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = models.User(username="owner", password_hash="hash")
        first_job = models.JobPosting(name="工程师", jd_text="Python")
        second_job = models.JobPosting(name="产品经理", jd_text="产品")
        db.add_all([user, first_job, second_job])
        db.commit()

        first_resume = models.Resume(
            candidate_id=None,
            version_number=None,
            original_filename="人才.pdf",
            file_path="/tmp/first.pdf",
            file_hash="same-file-hash",
            source="manual_upload",
            parse_status="not_parsed",
            uploaded_by_user_id=user.id,
        )
        second_resume = models.Resume(
            candidate_id=None,
            version_number=None,
            original_filename="人才.pdf",
            file_path="/tmp/second.pdf",
            file_hash="same-file-hash",
            source="manual_upload",
            parse_status="not_parsed",
            uploaded_by_user_id=user.id,
        )
        db.add_all([first_resume, second_resume])
        db.flush()
        db.add_all(
            [
                models.ResumeJobArchive(
                    resume_id=first_resume.id,
                    job_id=first_job.id,
                    source="manual_upload",
                    file_hash="same-file-hash",
                    assigned_by_user_id=user.id,
                ),
                models.ResumeJobArchive(
                    resume_id=second_resume.id,
                    job_id=second_job.id,
                    source="manual_upload",
                    file_hash="same-file-hash",
                    assigned_by_user_id=user.id,
                ),
            ]
        )
        db.commit()

        duplicate = models.Resume(
            original_filename="重复.pdf",
            file_path="/tmp/duplicate.pdf",
            file_hash="same-file-hash",
            source="manual_upload",
            parse_status="not_parsed",
        )
        db.add(duplicate)
        db.flush()
        db.add(
            models.ResumeJobArchive(
                resume_id=duplicate.id,
                job_id=first_job.id,
                source="manual_upload",
                file_hash="same-file-hash",
                assigned_by_user_id=user.id,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("同一岗位必须按文件哈希阻止重复归档")


def test_database_prevents_two_active_tasks_for_one_job(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'active-tasks.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = models.User(username="owner", password_hash="hash")
        job = models.JobPosting(name="工程师", jd_text="Python")
        db.add_all([user, job])
        db.commit()
        db.add(
            models.ScreeningTask(
                job_id=job.id,
                created_by_user_id=user.id,
                requested_count=10,
                status="ready",
                active_job_guard=job.id,
            )
        )
        db.commit()
        db.add(
            models.ScreeningTask(
                job_id=job.id,
                created_by_user_id=user.id,
                requested_count=10,
                status="paused",
                active_job_guard=job.id,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("同一岗位不能同时存在两个活动任务")


def test_terminal_tasks_do_not_hold_active_job_guard(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'terminal-tasks.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = models.User(username="owner", password_hash="hash")
        job = models.JobPosting(name="工程师", jd_text="Python")
        db.add_all([user, job])
        db.commit()
        db.add_all(
            [
                models.ScreeningTask(
                    job_id=job.id,
                    created_by_user_id=user.id,
                    requested_count=10,
                    status="completed",
                    active_job_guard=None,
                ),
                models.ScreeningTask(
                    job_id=job.id,
                    created_by_user_id=user.id,
                    requested_count=10,
                    status="cancelled",
                    active_job_guard=None,
                ),
            ]
        )
        db.commit()
        count = db.execute(text("SELECT COUNT(*) FROM screening_tasks")).scalar_one()
        assert count == 2
