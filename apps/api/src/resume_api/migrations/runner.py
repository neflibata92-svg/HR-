"""轻量、可重复执行的数据库迁移。"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path

from sqlalchemy import Connection, Engine, inspect, text

Migration = tuple[str, Callable[[Connection], bool]]


def _column_names(connection: Connection, table_name: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table_name)}


def _add_column(connection: Connection, table_name: str, definition: str) -> None:
    column_name = definition.split()[0]
    if column_name not in _column_names(connection, table_name):
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {definition}"))


def _create_model_table(connection: Connection, table_name: str) -> None:
    from resume_api.core.db import Base
    from resume_api import models  # noqa: F401

    Base.metadata.tables[table_name].create(connection, checkfirst=True)


def _add_must_change_password(connection: Connection) -> bool:
    _add_column(
        connection,
        "users",
        "must_change_password BOOLEAN NOT NULL DEFAULT FALSE",
    )
    return True


def _create_sqlite_outreach_events_without_screening_record(
    connection: Connection,
) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE outreach_events (
                id INTEGER NOT NULL PRIMARY KEY,
                candidate_id INTEGER REFERENCES candidates(id),
                job_id INTEGER NOT NULL REFERENCES job_postings(id),
                task_id INTEGER REFERENCES screening_tasks(id),
                message_snapshot TEXT NOT NULL DEFAULT '',
                status VARCHAR(30) NOT NULL DEFAULT 'confirmed',
                failure_reason TEXT NOT NULL DEFAULT '',
                manual_override_by_user_id INTEGER REFERENCES users(id),
                greeted BOOLEAN NOT NULL DEFAULT TRUE,
                attachment_received BOOLEAN NOT NULL DEFAULT FALSE,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                confirmed_at DATETIME
            )
            """
        )
    )
    connection.execute(
        text(
            "CREATE INDEX ix_outreach_candidate_status "
            "ON outreach_events (candidate_id, status)"
        )
    )


def _rebuild_sqlite_outreach_events(connection: Connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    columns = _column_names(connection, "outreach_events")
    screening_records_exist = "screening_records" in table_names
    has_legacy_unique = any(
        set(constraint.get("column_names") or []) == {"candidate_id", "job_id"}
        for constraint in inspector.get_unique_constraints("outreach_events")
    )
    candidate_column = next(
        (column for column in inspector.get_columns("outreach_events") if column["name"] == "candidate_id"),
        None,
    )
    required_columns = {
        "task_id",
        "message_snapshot",
        "status",
        "failure_reason",
        "manual_override_by_user_id",
        "confirmed_at",
    }
    base_structure_is_current = (
        required_columns <= columns
        and not has_legacy_unique
        and candidate_column is not None
        and candidate_column.get("nullable") is True
    )
    if (
        screening_records_exist
        and base_structure_is_current
        and "screening_record_id" not in columns
    ):
        connection.execute(
            text(
                "ALTER TABLE outreach_events ADD COLUMN screening_record_id INTEGER "
                "REFERENCES screening_records(id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_outreach_events_screening_record_id "
                "ON outreach_events (screening_record_id)"
            )
        )
        return
    if screening_records_exist:
        required_columns.add("screening_record_id")
    if base_structure_is_current and required_columns <= columns:
        return

    status_expression = (
        "status" if "status" in columns
        else "CASE WHEN greeted THEN 'confirmed' ELSE 'failed' END"
    )
    confirmed_expression = (
        "confirmed_at" if "confirmed_at" in columns
        else "CASE WHEN greeted THEN created_at ELSE NULL END"
    )
    message_expression = "message_snapshot" if "message_snapshot" in columns else "''"
    failure_expression = "failure_reason" if "failure_reason" in columns else "''"

    task_expression = "task_id" if "task_id" in columns else "NULL"
    screening_record_expression = (
        "screening_record_id" if "screening_record_id" in columns else "NULL"
    )
    override_expression = (
        "manual_override_by_user_id" if "manual_override_by_user_id" in columns else "NULL"
    )
    connection.execute(text("ALTER TABLE outreach_events RENAME TO outreach_events_legacy"))
    connection.execute(text("DROP INDEX IF EXISTS ix_outreach_candidate_status"))
    connection.execute(text("DROP INDEX IF EXISTS ix_outreach_events_screening_record_id"))
    if screening_records_exist:
        _create_model_table(connection, "outreach_events")
        target_columns = """
                id, candidate_id, screening_record_id, job_id, task_id,
                message_snapshot, status, failure_reason, manual_override_by_user_id,
                greeted, attachment_received, created_at, confirmed_at
        """
        source_columns = f"""
                id, candidate_id, {screening_record_expression}, job_id, {task_expression},
                {message_expression}, {status_expression}, {failure_expression},
                {override_expression}, greeted, attachment_received, created_at,
                {confirmed_expression}
        """
    else:
        _create_sqlite_outreach_events_without_screening_record(connection)
        target_columns = """
                id, candidate_id, job_id, task_id,
                message_snapshot, status, failure_reason, manual_override_by_user_id,
                greeted, attachment_received, created_at, confirmed_at
        """
        source_columns = f"""
                id, candidate_id, job_id, {task_expression},
                {message_expression}, {status_expression}, {failure_expression},
                {override_expression}, greeted, attachment_received, created_at,
                {confirmed_expression}
        """
    connection.execute(
        text(
            f"""
            INSERT INTO outreach_events ({target_columns})
            SELECT {source_columns}
            FROM outreach_events_legacy
            """
        )
    )
    connection.execute(text("DROP TABLE outreach_events_legacy"))


def _upgrade_postgresql_outreach_events(connection: Connection) -> None:
    for definition in (
        "task_id INTEGER REFERENCES screening_tasks(id)",
        "message_snapshot TEXT NOT NULL DEFAULT ''",
        "status VARCHAR(30) NOT NULL DEFAULT 'confirmed'",
        "failure_reason TEXT NOT NULL DEFAULT ''",
        "manual_override_by_user_id INTEGER REFERENCES users(id)",
        "confirmed_at TIMESTAMP",
    ):
        _add_column(connection, "outreach_events", definition)
    connection.execute(
        text(
            "UPDATE outreach_events SET "
            "status = CASE WHEN greeted THEN 'confirmed' ELSE 'failed' END, "
            "confirmed_at = CASE WHEN greeted THEN created_at ELSE NULL END"
        )
    )
    connection.execute(
        text("ALTER TABLE outreach_events DROP CONSTRAINT IF EXISTS uq_outreach_candidate_job")
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_outreach_candidate_status "
            "ON outreach_events (candidate_id, status)"
        )
    )


def _backfill_resume_versions(connection: Connection) -> None:
    candidate_ids = list(
        connection.execute(
            text("SELECT DISTINCT candidate_id FROM resumes WHERE candidate_id IS NOT NULL")
        ).scalars()
    )
    connection.execute(
        text("UPDATE resumes SET version_number = NULL WHERE candidate_id IS NOT NULL")
    )
    for candidate_id in candidate_ids:
        resume_ids = connection.execute(
            text(
                "SELECT id FROM resumes WHERE candidate_id = :candidate_id "
                "ORDER BY created_at, id"
            ),
            {"candidate_id": candidate_id},
        ).scalars()
        for version_number, resume_id in enumerate(resume_ids, start=1):
            connection.execute(
                text("UPDATE resumes SET version_number = :version_number WHERE id = :resume_id"),
                {"version_number": version_number, "resume_id": resume_id},
            )


def _backfill_original_filenames(connection: Connection) -> None:
    rows = connection.execute(
        text("SELECT id, file_path FROM resumes WHERE original_filename = ''")
    ).all()
    for row in rows:
        connection.execute(
            text("UPDATE resumes SET original_filename = :name WHERE id = :resume_id"),
            {"name": Path(row.file_path).name, "resume_id": row.id},
        )


def _backfill_resume_hashes(connection: Connection) -> None:
    rows = connection.execute(
        text("SELECT id, file_path FROM resumes WHERE file_hash IS NULL")
    ).all()
    for row in rows:
        path = Path(row.file_path)
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        connection.execute(
            text("UPDATE resumes SET file_hash = :file_hash WHERE id = :resume_id"),
            {"file_hash": digest.hexdigest(), "resume_id": row.id},
        )


def _upgrade_talent_records(connection: Connection) -> bool:
    required = {
        "users",
        "job_postings",
        "candidates",
        "resumes",
        "score_events",
        "outreach_events",
    }
    if not required <= set(inspect(connection).get_table_names()):
        return False

    for definition in (
        "phone_normalized VARCHAR(32)",
        "email_normalized VARCHAR(320)",
        "merged_into_candidate_id INTEGER REFERENCES candidates(id)",
        "updated_at TIMESTAMP",
    ):
        _add_column(connection, "candidates", definition)
    connection.execute(text("UPDATE candidates SET updated_at = COALESCE(updated_at, created_at)"))
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_candidates_phone_normalized "
            "ON candidates (phone_normalized)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_candidates_email_normalized "
            "ON candidates (email_normalized)"
        )
    )
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_candidates_merged_into_candidate_id "
            "ON candidates (merged_into_candidate_id)"
        )
    )

    for definition in (
        "version_number INTEGER",
        "original_filename VARCHAR(500) NOT NULL DEFAULT ''",
        "file_hash VARCHAR(64)",
        "uploaded_by_user_id INTEGER REFERENCES users(id)",
        "supersedes_resume_id INTEGER REFERENCES resumes(id)",
    ):
        _add_column(connection, "resumes", definition)
    _backfill_resume_versions(connection)
    _backfill_original_filenames(connection)
    _backfill_resume_hashes(connection)
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_resume_candidate_version "
            "ON resumes (candidate_id, version_number)"
        )
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_resume_candidate_hash "
            "ON resumes (candidate_id, file_hash)"
        )
    )

    _create_model_table(connection, "screening_tasks")
    _create_model_table(connection, "candidate_jobs")

    for definition in (
        "candidate_job_id INTEGER REFERENCES candidate_jobs(id)",
        "resume_id INTEGER REFERENCES resumes(id)",
        "task_id INTEGER REFERENCES screening_tasks(id)",
        "evidence_json TEXT NOT NULL DEFAULT '[]'",
        "missing_fields_json TEXT NOT NULL DEFAULT '[]'",
        "estimated_fields_json TEXT NOT NULL DEFAULT '[]'",
        "critical_fields_json TEXT NOT NULL DEFAULT '[]'",
        "confidence FLOAT",
        "decision VARCHAR(30) NOT NULL DEFAULT 'error'",
    ):
        _add_column(connection, "score_events", definition)

    connection.execute(
        text(
            """
            INSERT INTO candidate_jobs (candidate_id, job_id, status, review_reason_json)
            SELECT pairs.candidate_id, pairs.job_id,
                CASE
                    WHEN EXISTS (
                        SELECT 1 FROM outreach_events outreach
                        WHERE outreach.candidate_id = pairs.candidate_id
                          AND outreach.job_id = pairs.job_id
                          AND outreach.greeted
                    ) THEN 'contacted'
                    WHEN EXISTS (
                        SELECT 1 FROM score_events score
                        WHERE score.candidate_id = pairs.candidate_id
                          AND score.job_id = pairs.job_id
                    ) THEN 'scored'
                    ELSE 'discovered'
                END,
                '[]'
            FROM (
                SELECT candidate_id, job_id FROM score_events
                UNION
                SELECT candidate_id, job_id FROM outreach_events
            ) AS pairs
            WHERE NOT EXISTS (
                SELECT 1 FROM candidate_jobs existing
                WHERE existing.candidate_id = pairs.candidate_id
                  AND existing.job_id = pairs.job_id
            )
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE candidate_jobs
            SET latest_score_event_id = (
                SELECT MAX(score_events.id) FROM score_events
                WHERE score_events.candidate_id = candidate_jobs.candidate_id
                  AND score_events.job_id = candidate_jobs.job_id
            ),
            active_resume_id = (
                SELECT resumes.id FROM resumes
                WHERE resumes.candidate_id = candidate_jobs.candidate_id
                ORDER BY resumes.version_number DESC, resumes.id DESC
                LIMIT 1
            )
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE score_events
            SET candidate_job_id = (
                SELECT candidate_jobs.id FROM candidate_jobs
                WHERE candidate_jobs.candidate_id = score_events.candidate_id
                  AND candidate_jobs.job_id = score_events.job_id
            )
            WHERE candidate_job_id IS NULL
            """
        )
    )

    if connection.dialect.name == "sqlite":
        _rebuild_sqlite_outreach_events(connection)
    else:
        _upgrade_postgresql_outreach_events(connection)

    for table_name in (
        "screening_task_items",
        "candidate_merges",
        "candidate_merge_suggestions",
        "outreach_overrides",
        "audit_events",
        "agent_runs",
    ):
        _create_model_table(connection, table_name)
    return True


def _upgrade_job_task_resume_archives(connection: Connection) -> bool:
    required = {"users", "job_postings", "resumes", "screening_tasks"}
    if not required <= set(inspect(connection).get_table_names()):
        return False

    for definition in (
        "default_requested_count INTEGER",
        "critical_fields_json TEXT NOT NULL DEFAULT '[]'",
        "critical_fields_confirmed_at TIMESTAMP",
    ):
        _add_column(connection, "job_postings", definition)

    for definition in (
        "assignment_status VARCHAR(50) NOT NULL DEFAULT 'assigned'",
        "contact_event_id INTEGER REFERENCES outreach_events(id)",
    ):
        _add_column(connection, "resumes", definition)
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_resumes_contact_event_id "
            "ON resumes (contact_event_id)"
        )
    )

    _create_model_table(connection, "agent_runs")
    for definition in (
        "owner_user_id INTEGER REFERENCES users(id)",
        "availability VARCHAR(20) NOT NULL DEFAULT 'idle'",
        "current_task_id INTEGER REFERENCES screening_tasks(id)",
        "current_job_id INTEGER REFERENCES job_postings(id)",
        "boss_login_status VARCHAR(30) NOT NULL DEFAULT 'unknown'",
    ):
        _add_column(connection, "agent_runs", definition)
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_agent_runs_owner_user_id "
            "ON agent_runs (owner_user_id)"
        )
    )

    for definition in (
        "assigned_agent_run_id INTEGER REFERENCES agent_runs(id)",
        "active_job_guard INTEGER",
        "control_requested_at TIMESTAMP",
    ):
        _add_column(connection, "screening_tasks", definition)
    connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_screening_tasks_assigned_agent_run_id "
            "ON screening_tasks (assigned_agent_run_id)"
        )
    )
    connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_screening_tasks_active_job_guard "
            "ON screening_tasks (active_job_guard)"
        )
    )

    _create_model_table(connection, "screening_records")
    if connection.dialect.name == "sqlite":
        _rebuild_sqlite_outreach_events(connection)
    else:
        _add_column(
            connection,
            "outreach_events",
            "screening_record_id INTEGER REFERENCES screening_records(id)",
        )
        connection.execute(
            text("ALTER TABLE outreach_events ALTER COLUMN candidate_id DROP NOT NULL")
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_outreach_events_screening_record_id "
                "ON outreach_events (screening_record_id)"
            )
        )
    _create_model_table(connection, "resume_job_archives")
    return True


def _migrate_candidate_history(connection: Connection) -> bool:
    required = {
        "users",
        "job_postings",
        "candidates",
        "candidate_jobs",
        "screening_tasks",
        "screening_records",
        "outreach_events",
    }
    if not required <= set(inspect(connection).get_table_names()):
        return False

    owner_user_id = connection.execute(text("SELECT MIN(id) FROM users")).scalar_one_or_none()
    if owner_user_id is None:
        return True

    rows = connection.execute(
        text(
            """
            SELECT
                candidate_jobs.candidate_id,
                candidate_jobs.job_id,
                candidates.boss_id,
                candidates.fingerprint,
                candidates.name,
                candidates.age,
                candidates.years_of_experience,
                candidates.job_segments_json,
                candidate_jobs.status AS candidate_job_status,
                CASE WHEN EXISTS (
                    SELECT 1 FROM outreach_events successful
                    WHERE successful.candidate_id = candidate_jobs.candidate_id
                      AND successful.status = 'confirmed'
                      AND successful.greeted
                ) THEN 0 ELSE 1 END AS migration_review_required,
                (
                    SELECT MAX(score_events.id) FROM score_events
                    WHERE score_events.candidate_id = candidate_jobs.candidate_id
                      AND score_events.job_id = candidate_jobs.job_id
                ) AS latest_score_event_id,
                (
                    SELECT MAX(outreach_events.id) FROM outreach_events
                    WHERE outreach_events.candidate_id = candidate_jobs.candidate_id
                      AND outreach_events.job_id = candidate_jobs.job_id
                ) AS latest_outreach_event_id
            FROM candidate_jobs
            JOIN candidates ON candidates.id = candidate_jobs.candidate_id
            WHERE NOT EXISTS (
                SELECT 1 FROM outreach_events confirmed
                WHERE confirmed.candidate_id = candidate_jobs.candidate_id
                  AND confirmed.job_id = candidate_jobs.job_id
                  AND confirmed.status = 'confirmed'
                  AND confirmed.greeted
            )
            ORDER BY candidate_jobs.job_id, candidate_jobs.candidate_id
            """
        )
    ).mappings().all()

    grouped: dict[int, list[object]] = {}
    for row in rows:
        grouped.setdefault(int(row["job_id"]), []).append(row)

    for job_id, job_rows in grouped.items():
        task_id = connection.execute(
            text(
                "SELECT id FROM screening_tasks "
                "WHERE job_id = :job_id AND machine_id = 'history-migration' "
                "ORDER BY id LIMIT 1"
            ),
            {"job_id": job_id},
        ).scalar_one_or_none()
        if task_id is None:
            job = connection.execute(
                text(
                    "SELECT name, jd_text, score_threshold, greet_template, boss_entry_url "
                    "FROM job_postings WHERE id = :job_id"
                ),
                {"job_id": job_id},
            ).mappings().one()
            task_id = connection.execute(
                text(
                    """
                    INSERT INTO screening_tasks (
                        job_id, created_by_user_id, machine_id, requested_count,
                        critical_fields_json, critical_fields_source_json,
                        job_name_snapshot, jd_text_snapshot, score_threshold_snapshot,
                        greet_template_snapshot, boss_entry_url_snapshot, status, pause_reason,
                        processed_count, eligible_count, contacted_count, review_count,
                        skipped_count, failed_count, created_at, finished_at
                    ) VALUES (
                        :job_id, :owner_user_id, 'history-migration', :requested_count,
                        '[]', '{"confirmed": false, "source": "history_migration"}',
                        :job_name, :jd_text, :score_threshold, :greet_template,
                        :boss_entry_url, 'completed', '', :processed_count, 0, 0, :review_count,
                        0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id
                    """
                ),
                {
                    "job_id": job_id,
                    "owner_user_id": owner_user_id,
                    "requested_count": min(max(len(job_rows), 1), 50),
                    "job_name": job["name"] or "",
                    "jd_text": job["jd_text"] or "",
                    "score_threshold": job["score_threshold"] or 80,
                    "greet_template": job["greet_template"] or "",
                    "boss_entry_url": job["boss_entry_url"] or "",
                    "processed_count": len(job_rows),
                    "review_count": sum(
                        int(bool(row["migration_review_required"])) for row in job_rows
                    ),
                },
            ).scalar_one()

        for position_index, row in enumerate(job_rows, start=1):
            import json

            source_payload = {
                "migration_source": "legacy_candidate",
                "legacy_candidate_id": row["candidate_id"],
                "age": row["age"],
                "years_of_experience": row["years_of_experience"],
                "job_segments": json.loads(row["job_segments_json"] or "[]"),
                "candidate_job_status": row["candidate_job_status"],
                "latest_score_event_id": row["latest_score_event_id"],
            }
            connection.execute(
                text(
                    """
                    INSERT INTO screening_records (
                        task_id, job_id, boss_id, fingerprint, identity_key,
                        display_name, source_payload_json, status, score_snapshot_json,
                        candidate_id, outreach_event_id, position_index,
                        migration_review_required, created_at, updated_at
                    )
                    SELECT
                        :task_id, :job_id, :boss_id, :fingerprint, :identity_key,
                        :display_name, :source_payload_json, 'historical_screening', '{}',
                        :candidate_id, :outreach_event_id, :position_index,
                        :migration_review_required, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    WHERE NOT EXISTS (
                        SELECT 1 FROM screening_records
                        WHERE task_id = :task_id AND identity_key = :identity_key
                    )
                    """
                ),
                {
                    "task_id": task_id,
                    "job_id": job_id,
                    "boss_id": row["boss_id"],
                    "fingerprint": row["fingerprint"],
                    "identity_key": f"legacy-candidate:{row['candidate_id']}",
                    "display_name": row["name"] or "",
                    "source_payload_json": json.dumps(source_payload, ensure_ascii=False),
                    "candidate_id": row["candidate_id"],
                    "outreach_event_id": row["latest_outreach_event_id"],
                    "position_index": position_index,
                    "migration_review_required": bool(row["migration_review_required"]),
                },
            )
    return True


def _add_task_entry_url_snapshot(connection: Connection) -> bool:
    if "screening_tasks" not in inspect(connection).get_table_names():
        return False
    _add_column(
        connection,
        "screening_tasks",
        "boss_entry_url_snapshot VARCHAR(500) NOT NULL DEFAULT ''",
    )
    connection.execute(
        text(
            "UPDATE screening_tasks SET boss_entry_url_snapshot = COALESCE(("
            "SELECT boss_entry_url FROM job_postings "
            "WHERE job_postings.id = screening_tasks.job_id"
            "), '') WHERE boss_entry_url_snapshot = ''"
        )
    )
    return True


MIGRATIONS: tuple[Migration, ...] = (
    ("0001_add_must_change_password", _add_must_change_password),
    ("0002_talent_records", _upgrade_talent_records),
    ("0003_job_task_resume_archives", _upgrade_job_task_resume_archives),
    ("0004_candidate_history", _migrate_candidate_history),
    ("0005_task_entry_url_snapshot", _add_task_entry_url_snapshot),
)


def run_migrations(engine: Engine) -> None:
    """按版本升级已存在的数据库；新数据库由 ORM 创建完整结构。"""

    if "users" not in inspect(engine).get_table_names():
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(100) PRIMARY KEY, "
                "applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ")"
            )
        )
        applied = set(
            connection.execute(text("SELECT version FROM schema_migrations")).scalars()
        )
        for version, migrate in MIGRATIONS:
            if version in applied:
                continue
            if not migrate(connection):
                continue
            connection.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": version},
            )
