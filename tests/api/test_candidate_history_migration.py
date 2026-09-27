from __future__ import annotations

from sqlalchemy import create_engine, text

from resume_api import models as _models  # noqa: F401
from resume_api.core.db import Base
from resume_api.migrations.runner import run_migrations


def test_candidate_history_migration_runs_after_existing_0003_database(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'already-0003.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE schema_migrations (
                    version VARCHAR(100) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO schema_migrations (version) VALUES "
                "('0001_add_must_change_password'), "
                "('0002_talent_records'), "
                "('0003_job_task_resume_archives')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, role, is_active) "
                "VALUES (1, 'owner', 'hash', 'member', 1)"
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO job_postings (
                    id, name, jd_text, score_threshold, greet_template, boss_entry_url,
                    hourly_greet_limit, min_action_delay_ms, max_action_delay_ms,
                    critical_fields_json, enabled
                ) VALUES (1, '工程师', 'Python', 80, '您好', '', 20, 1500, 4000, '[]', 1)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO candidates (
                    id, boss_id, fingerprint, name, job_segments_json, source
                ) VALUES
                (10, 'boss-success', 'fp-success', '已联系', '[]', 'boss'),
                (20, 'boss-history', 'fp-history', '未联系', '[]', 'boss')
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO candidate_jobs (candidate_id, job_id, status, review_reason_json) "
                "VALUES (10, 1, 'contacted', '[]'), (20, 1, 'scored', '[]')"
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO outreach_events (
                    candidate_id, job_id, message_snapshot, status,
                    failure_reason, greeted, attachment_received
                ) VALUES (10, 1, '您好', 'confirmed', '', 1, 0)
                """
            )
        )

    run_migrations(engine)
    run_migrations(engine)

    with engine.connect() as connection:
        versions = connection.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).scalars().all()
        assert versions[-1] == "0005_task_entry_url_snapshot"
        rows = connection.execute(
            text(
                "SELECT candidate_id, job_id, status, migration_review_required "
                "FROM screening_records ORDER BY candidate_id"
            )
        ).all()
        assert rows == [(20, 1, "historical_screening", 1)]
        assert connection.execute(text("SELECT COUNT(*) FROM candidates")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM candidate_jobs")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM outreach_events")).scalar_one() == 1
