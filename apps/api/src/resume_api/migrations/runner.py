"""轻量、可重复执行的数据库迁移。"""

from __future__ import annotations

from sqlalchemy import Engine, inspect, text


def run_migrations(engine: Engine) -> None:
    """升级已存在的数据库；新数据库由 ORM 直接创建完整结构。"""

    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("users")}
    if "must_change_password" in columns:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE users ADD COLUMN "
                "must_change_password BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
