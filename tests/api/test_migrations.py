from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from resume_api.migrations.runner import run_migrations


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


def test_skips_database_without_users_table(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")

    run_migrations(engine)
    run_migrations(engine)

    assert "users" not in inspect(engine).get_table_names()
