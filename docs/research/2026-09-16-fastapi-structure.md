# Research: FastAPI + SQLAlchemy 项目结构（2026-09-16）

用于实现计划中的内网 API 布局选型。

## 结论

- 采用分层：`router`（HTTP）→ `service`（业务）→ `repository`/`models`（持久化）；Pydantic schemas 与 ORM 分离。
- SQLAlchemy 2.0 `Mapped` / `mapped_column`；MVP 用同步 Session + SQLite（`check_same_thread=False`）。
- 领域包按资源拆分（jobs、candidates、resumes、events），共享 `core`（settings、db、auth）。

## 参考

- https://github.com/zhanymkanov/fastapi-best-practices
- https://chaoticengineer.hashnode.dev/fastapi-sqlalchemy
