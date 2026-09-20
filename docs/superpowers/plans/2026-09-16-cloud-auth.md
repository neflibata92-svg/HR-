# Cloud Auth + Docker Compose Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline; user requested plan then code).

**Goal:** 将 API/Web 改为云端可部署形态：账号密码 JWT、个人 API Key（Agent）、Docker Compose（Nginx+API+Postgres）。

**Architecture:** FastAPI 统一 `get_current_user`（Bearer JWT 或 `X-Api-Key`）；开发环境保留 `DEV_API_TOKEN` 旁路；生产 Compose 使用 PostgreSQL。

**Tech Stack:** PyJWT、passlib[bcrypt]、python-multipart、Docker Compose、Nginx、Vue 登录页。

**Spec:** `docs/superpowers/specs/2026-09-16-cloud-auth-design.md`

## Global Constraints

- Agent 本机；`X-Api-Key` 固定头。
- 生产禁用全局 `API_TOKEN`；`ENV=development` 才允许 `DEV_API_TOKEN`。
- 首个注册用户为 admin；`ALLOW_REGISTER` 可关。
- 注释中文；`make test` 必须通过。
- Commit：`type(scope): description`

---

### Task 1: Auth 模型与 JWT/API Key 核心

**Files:** `apps/api/src/resume_api/models.py`, `core/config.py`, `core/security.py`, `core/auth.py`, `schemas.py`, tests

- User / ApiKey ORM
- Settings: jwt_secret, allow_register, env, dev_api_token, cors
- hash_password / verify; create_access/refresh; hash_api_key
- `get_current_user` dependency

### Task 2: Auth 路由 + 替换业务鉴权

**Files:** `routers/auth.py`, 各业务 router 依赖改为 `get_current_user`, `main.py`

### Task 3: 测试夹具与 auth 测试

**Files:** `tests/api/conftest.py`, `test_auth.py`, 更新现有测试 headers

### Task 4: Agent 改 X-Api-Key

**Files:** `resume_agent/config.py`, `api_client.py`, `.env.example`

### Task 5: Web 登录 + Bearer + API Key 管理

**Files:** `apps/web/src/*`

### Task 6: Docker Compose + Nginx + README

**Files:** `deploy/docker-compose.yml`, `deploy/nginx.conf`, Dockerfiles, README

### Task 7: make test + commit

用户已要求写完计划直接改代码 → Inline Execution。
