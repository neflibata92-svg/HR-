from __future__ import annotations

from sqlalchemy import create_engine, event, inspect, text

from resume_api.migrations.runner import run_migrations


def _enable_sqlite_foreign_keys(engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def test_upgrades_legacy_users_table_idempotently(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(200) NOT NULL,
                    role VARCHAR(20),
                    is_active BOOLEAN,
                    created_at DATETIME
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO users (username, password_hash, role, is_active)
                VALUES ('admin', 'old-hash', 'admin', TRUE)
                """
            )
        )

    run_migrations(engine)
    run_migrations(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "must_change_password" in columns
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT username, must_change_password FROM users WHERE username = 'admin'")
        ).one()
    assert row.username == "admin"
    assert row.must_change_password in (False, 0)


def test_existing_password_flag_does_not_skip_later_migrations(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'partially-upgraded.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(100) NOT NULL UNIQUE,
                    password_hash VARCHAR(200) NOT NULL,
                    role VARCHAR(20),
                    is_active BOOLEAN,
                    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at DATETIME
                )
                """
            )
        )

    run_migrations(engine)
    run_migrations(engine)

    inspector = inspect(engine)
    assert "schema_migrations" in inspector.get_table_names()
    migration_columns = {
        column["name"]: column for column in inspector.get_columns("schema_migrations")
    }
    assert "TIMESTAMP" in str(migration_columns["applied_at"]["type"]).upper()
    with engine.connect() as connection:
        versions = connection.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).scalars().all()
    assert versions == ["0001_add_must_change_password"]


def test_legacy_outreach_migration_preserves_rows_and_creates_quota_tables_once(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-outreach.db'}")
    with engine.begin() as connection:
        for ddl in (
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(100) NOT NULL UNIQUE, password_hash VARCHAR(200) NOT NULL, role VARCHAR(20), is_active BOOLEAN, created_at DATETIME)",
            "CREATE TABLE job_postings (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, jd_text TEXT NOT NULL, boss_entry_url VARCHAR(500))",
            "CREATE TABLE screening_tasks (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, created_by_user_id INTEGER NOT NULL, machine_id VARCHAR(100), requested_count INTEGER NOT NULL, status VARCHAR(30), FOREIGN KEY(job_id) REFERENCES job_postings(id), FOREIGN KEY(created_by_user_id) REFERENCES users(id))",
            "CREATE TABLE screening_task_items (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, FOREIGN KEY(task_id) REFERENCES screening_tasks(id))",
            "CREATE TABLE outreach_events (id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, task_id INTEGER, greeted BOOLEAN, created_at DATETIME, FOREIGN KEY(job_id) REFERENCES job_postings(id), FOREIGN KEY(task_id) REFERENCES screening_tasks(id))",
        ):
            connection.execute(text(ddl))
        connection.execute(
            text("INSERT INTO users VALUES (1, 'hr', 'hash', 'member', 1, '2026-01-01')")
        )
        connection.execute(text("INSERT INTO job_postings VALUES (1, '工程师', 'Python', '')"))
        connection.execute(text("INSERT INTO screening_tasks VALUES (10, 1, 1, 'legacy', 1, 'completed')"))
        connection.execute(text("INSERT INTO screening_task_items VALUES (20, 10)"))
        connection.execute(text("INSERT INTO outreach_events VALUES (30, 1, 10, 1, '2026-02-01')"))

    run_migrations(engine)
    run_migrations(engine)

    inspector = inspect(engine)
    assert "outreach_quota_ledgers" in inspector.get_table_names()
    assert "outreach_quota_reservations" in inspector.get_table_names()
    with engine.connect() as connection:
        quota_table_count = connection.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'outreach_quota_ledgers'")
        ).scalar_one()
        assert quota_table_count == 1
        assert connection.execute(text("SELECT id FROM users")).scalars().all() == [1]
        assert connection.execute(text("SELECT id FROM screening_tasks")).scalars().all() == [10]
        assert connection.execute(text("SELECT id FROM screening_task_items")).scalars().all() == [20]
        assert connection.execute(text("SELECT id FROM outreach_events")).scalars().all() == [30]
        assert connection.execute(
            text("SELECT quota_owner_user_id FROM outreach_events WHERE id = 30")
        ).scalar_one() == 1
        quota = connection.execute(
            text(
                "SELECT hard_limit, confirmed_count, reserved_count "
                "FROM outreach_quota_ledgers WHERE user_id = 1"
            )
        ).one()
        assert tuple(quota) == (200, 0, 0)
        assert connection.execute(
            text("SELECT COUNT(*) FROM outreach_quota_reservations")
        ).scalar_one() == 0
        assert connection.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE version = '0006_outreach_quota_ledger'")
        ).scalar_one() == 1


def test_migrates_legacy_talent_history_without_losing_records(tmp_path) -> None:
    old_resume = tmp_path / "old.pdf"
    old_resume.write_bytes(b"legacy resume")
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-talent.db'}")
    _enable_sqlite_foreign_keys(engine)
    with engine.begin() as connection:
        for ddl in (
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY, username VARCHAR(100) NOT NULL UNIQUE,
                password_hash VARCHAR(200) NOT NULL, role VARCHAR(20),
                is_active BOOLEAN, created_at DATETIME
            )
            """,
            """
            CREATE TABLE job_postings (
                id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL,
                jd_text TEXT NOT NULL, score_threshold INTEGER,
                greet_template TEXT, boss_entry_url VARCHAR(500),
                hourly_greet_limit INTEGER, min_action_delay_ms INTEGER,
                max_action_delay_ms INTEGER, enabled BOOLEAN, created_at DATETIME
            )
            """,
            """
            CREATE TABLE candidates (
                id INTEGER PRIMARY KEY, boss_id VARCHAR(100),
                fingerprint VARCHAR(64) NOT NULL, name VARCHAR(100), age INTEGER,
                years_of_experience FLOAT, job_segments_json TEXT,
                source VARCHAR(50), created_at DATETIME
            )
            """,
            """
            CREATE TABLE resumes (
                id INTEGER PRIMARY KEY, candidate_id INTEGER, version_number INTEGER,
                file_path VARCHAR(500) NOT NULL, parsed_text TEXT,
                source VARCHAR(50) NOT NULL, parse_status VARCHAR(50), created_at DATETIME,
                FOREIGN KEY(candidate_id) REFERENCES candidates(id)
            )
            """,
            """
            CREATE TABLE score_events (
                id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL, hard_filter_passed BOOLEAN,
                hard_filter_reasons TEXT, score INTEGER, reason TEXT,
                model VARCHAR(100), created_at DATETIME,
                FOREIGN KEY(candidate_id) REFERENCES candidates(id),
                FOREIGN KEY(job_id) REFERENCES job_postings(id)
            )
            """,
            """
            CREATE TABLE outreach_events (
                id INTEGER PRIMARY KEY, candidate_id INTEGER NOT NULL,
                job_id INTEGER NOT NULL, greeted BOOLEAN,
                attachment_received BOOLEAN, created_at DATETIME,
                CONSTRAINT uq_outreach_candidate_job UNIQUE(candidate_id, job_id),
                FOREIGN KEY(candidate_id) REFERENCES candidates(id),
                FOREIGN KEY(job_id) REFERENCES job_postings(id)
            )
            """,
        ):
            connection.execute(text(ddl))
        connection.execute(
            text("INSERT INTO users VALUES (1, 'admin', 'hash', 'admin', 1, '2026-01-01')")
        )
        connection.execute(
            text(
                "INSERT INTO job_postings VALUES "
                "(1, '工程师', 'Python', 80, '您好', '', 20, 1500, 4000, 1, '2026-01-01'),"
                "(2, '产品', '产品', 75, '您好', '', 20, 1500, 4000, 1, '2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO candidates VALUES "
                "(10, 'boss-10', 'fp-10', '甲', 30, 5, '[]', 'boss', '2026-01-01'),"
                "(20, NULL, 'fp-20', '乙', NULL, NULL, '[]', 'boss', '2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO resumes VALUES "
                "(100, 10, NULL, '/files/new.pdf', 'new', 'upload', 'ok', '2026-02-01'),"
                "(90, 10, 2, :old_path, 'old', 'upload', 'ok', '2026-01-01'),"
                "(110, NULL, NULL, '/files/unclaimed.pdf', '', 'watch', 'ok', '2026-01-15')"
            ),
            {"old_path": str(old_resume)},
        )
        connection.execute(
            text(
                "INSERT INTO score_events VALUES "
                "(1000, 10, 1, 1, '[]', 88, 'good', 'model-a', '2026-02-01'),"
                "(1001, 10, 1, 1, '[]', 90, 'better', 'model-b', '2026-02-02')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO outreach_events VALUES "
                "(2000, 10, 2, 1, 0, '2026-02-03'),"
                "(2001, 20, 1, 0, 0, '2026-02-04')"
            )
        )

    run_migrations(engine)
    run_migrations(engine)

    inspector = inspect(engine)
    expected_tables = {
        "candidate_jobs",
        "screening_tasks",
        "screening_task_items",
        "screening_records",
        "resume_job_archives",
        "candidate_merges",
        "candidate_merge_suggestions",
        "outreach_overrides",
        "audit_events",
    }
    assert expected_tables <= set(inspector.get_table_names())
    assert {
        "default_requested_count",
        "critical_fields_json",
        "critical_fields_confirmed_at",
    } <= {column["name"] for column in inspector.get_columns("job_postings")}
    assert {"contact_event_id", "assignment_status"} <= {
        column["name"] for column in inspector.get_columns("resumes")
    }
    assert {
        "assigned_agent_run_id",
        "control_requested_at",
        "active_job_guard",
        "boss_entry_url_snapshot",
    } <= {
        column["name"] for column in inspector.get_columns("screening_tasks")
    }
    assert {
        "owner_user_id",
        "current_task_id",
        "current_job_id",
        "availability",
        "boss_login_status",
    } <= {column["name"] for column in inspector.get_columns("agent_runs")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM candidates")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM resumes")).scalar_one() == 3
        assert connection.execute(text("SELECT COUNT(*) FROM score_events")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM outreach_events")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM candidate_jobs")).scalar_one() == 3
        assert connection.execute(
            text("SELECT id FROM resumes ORDER BY id")
        ).scalars().all() == [90, 100, 110]
        versions = connection.execute(
            text(
                "SELECT id, version_number FROM resumes "
                "WHERE candidate_id = 10 ORDER BY version_number"
            )
        ).all()
        assert versions == [(90, 1), (100, 2)]
        unclaimed = connection.execute(
            text("SELECT candidate_id, version_number FROM resumes WHERE id = 110")
        ).one()
        assert unclaimed == (None, None)
        hashes = connection.execute(
            text("SELECT id, file_hash FROM resumes ORDER BY id")
        ).all()
        assert hashes[0] == (
            90,
            "263e795e3b72f55cd086f3973d8c165f5ad1474d8432f8220a20843154c23696",
        )
        assert hashes[1].file_hash is None
        assert hashes[2].file_hash is None
        score_links = connection.execute(
            text("SELECT DISTINCT candidate_job_id FROM score_events")
        ).scalars().all()
        assert len(score_links) == 1
        candidate_jobs = connection.execute(
            text(
                "SELECT candidate_id, job_id, status, latest_score_event_id "
                "FROM candidate_jobs ORDER BY candidate_id, job_id"
            )
        ).all()
        assert candidate_jobs == [
            (10, 1, "scored", 1001),
            (10, 2, "contacted", None),
            (20, 1, "discovered", None),
        ]
        history = connection.execute(
            text(
                "SELECT candidate_id, job_id, status, migration_review_required "
                "FROM screening_records ORDER BY candidate_id, job_id"
            )
        ).all()
        assert history == [
            (10, 1, "historical_screening", 0),
            (20, 1, "historical_screening", 1),
        ]
        migration_tasks = connection.execute(
            text(
                "SELECT job_id, status FROM screening_tasks "
                "WHERE machine_id = 'history-migration' ORDER BY job_id"
            )
        ).all()
        assert migration_tasks == [(1, "completed")]
        outreach = connection.execute(
            text("SELECT id, status, confirmed_at FROM outreach_events ORDER BY id")
        ).all()
        assert outreach[0].id == 2000
        assert outreach[0].status == "confirmed"
        assert outreach[0].confirmed_at is not None
        assert outreach[1].id == 2001
        assert outreach[1].status == "failed"
        versions = connection.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).scalars().all()
        assert versions == [
            "0001_add_must_change_password",
            "0002_talent_records",
            "0003_job_task_resume_archives",
            "0004_candidate_history",
            "0005_task_entry_url_snapshot",
            "0006_outreach_quota_ledger",
        ]

    unique_sets = {
        tuple(constraint["column_names"])
        for constraint in inspect(engine).get_unique_constraints("outreach_events")
    }
    assert ("candidate_id", "job_id") not in unique_sets


def test_skips_database_without_users_table(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")

    run_migrations(engine)
    run_migrations(engine)

    assert "users" not in inspect(engine).get_table_names()
