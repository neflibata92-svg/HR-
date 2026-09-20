# BOSS Resume Screening MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付本机 Playwright Agent + 内网 FastAPI 简历库 MVP：硬筛、LLM 打分、达阈值打招呼入库、团队交换冷却、上传与文件夹监视。

**Architecture:** 共享领域逻辑在 `packages/domain`；内网服务 `apps/api`（FastAPI + SQLite + 文件存储 + 文件夹监视）；本机 `apps/agent`（Playwright persistent profile + API 客户端）；简易 `apps/web`（Vue 3）连内网 API。CI/单测不依赖真实 BOSS 站，Agent 用 HTML fixture。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy 2.0、SQLite、Playwright、httpx、pydantic-settings、pytest、Vue 3（Vite）、Makefile。

**Spec:** `docs/superpowers/specs/2026-09-16-boss-resume-screening-design.md`  
**Research:** `docs/research/2026-09-16-local-agent-llm-scoring.md`、`docs/research/2026-09-16-fastapi-structure.md`

## Global Constraints

- 注释使用中文；TypeScript/前端与 Python 均避免随意 `any`（Python 用明确类型）。
- 硬筛固定：年龄 ≤38；工作年限 ∈[3,5]；平均每份工作 >1；近 30 天无 ExchangeEvent；字段不确定则跳过。
- LLM 细打分，默认阈值 80；达阈值才打招呼。
- Agent 本机 headed + persistent profile；简历主数据只存内网服务。
- 不绕过验证码；风控页停机；限速可配。
- 提交前 `make test` 必须通过。
- Git commit 格式：`type(scope): description`。

---

## File Structure

```
Resume_Screening/
├── Makefile
├── pyproject.toml                 # workspace: domain, api, agent
├── README.md
├── .env.example
├── packages/
│   └── domain/
│       ├── pyproject.toml
│       └── src/resume_domain/
│           ├── __init__.py
│           ├── hard_filter.py
│           ├── fingerprint.py
│           ├── llm_schema.py
│           └── decision.py
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   └── src/resume_api/
│   │       ├── main.py
│   │       ├── core/{config.py,db.py,auth.py}
│   │       ├── models.py
│   │       ├── schemas.py
│   │       ├── services/{jobs.py,candidates.py,resumes.py,events.py,ingest.py}
│   │       ├── routers/{jobs.py,candidates.py,resumes.py,events.py,agent.py}
│   │       └── parsing.py
│   ├── agent/
│   │   ├── pyproject.toml
│   │   └── src/resume_agent/
│   │       ├── __init__.py
│   │       ├── config.py
│   │       ├── api_client.py
│   │       ├── llm.py
│   │       ├── rate_limit.py
│   │       ├── browser.py
│   │       ├── parse_page.py
│   │       ├── pipeline.py
│   │       └── cli.py
│   └── web/
│       ├── package.json
│       ├── vite.config.ts
│       ├── index.html
│       └── src/{main.ts,App.vue,api.ts,views/*.vue}
└── tests/
    ├── domain/
    ├── api/
    ├── agent/
    └── fixtures/boss_list.html
```

---

### Task 1: Domain — 硬筛与指纹

**Files:**
- Create: `packages/domain/pyproject.toml`
- Create: `packages/domain/src/resume_domain/hard_filter.py`
- Create: `packages/domain/src/resume_domain/fingerprint.py`
- Create: `packages/domain/src/resume_domain/__init__.py`
- Create: `pyproject.toml`（根，pytest 配置）
- Create: `Makefile`
- Test: `tests/domain/test_hard_filter.py`
- Test: `tests/domain/test_fingerprint.py`

**Interfaces:**
- Produces:
  - `dataclass CandidateSnapshot(age: int | None, years_of_experience: float | None, job_segment_count: int | None, total_work_years: float | None)`
  - `dataclass HardFilterResult(passed: bool, reasons: list[str])`
  - `def apply_hard_filter(snap: CandidateSnapshot, *, exchanged_within_30_days: bool) -> HardFilterResult`
  - `def candidate_fingerprint(name: str, recent_org: str) -> str`

- [ ] **Step 1: 写失败测试**

```python
# tests/domain/test_hard_filter.py
from resume_domain.hard_filter import CandidateSnapshot, apply_hard_filter

def test_passes_when_all_rules_ok() -> None:
    snap = CandidateSnapshot(age=30, years_of_experience=4, job_segment_count=3, total_work_years=4.0)
    r = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert r.passed is True
    assert r.reasons == []

def test_rejects_age_over_38() -> None:
    snap = CandidateSnapshot(age=39, years_of_experience=4, job_segment_count=2, total_work_years=4.0)
    r = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert r.passed is False
    assert "age" in r.reasons

def test_rejects_years_outside_3_to_5() -> None:
    snap = CandidateSnapshot(age=30, years_of_experience=2, job_segment_count=1, total_work_years=2.0)
    assert apply_hard_filter(snap, exchanged_within_30_days=False).passed is False

def test_rejects_avg_tenure_not_gt_1() -> None:
    # 4 years / 4 segments = 1.0，不满足 > 1
    snap = CandidateSnapshot(age=30, years_of_experience=4, job_segment_count=4, total_work_years=4.0)
    r = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert r.passed is False
    assert "avg_tenure" in r.reasons

def test_skips_when_segments_unknown() -> None:
    snap = CandidateSnapshot(age=30, years_of_experience=4, job_segment_count=None, total_work_years=4.0)
    r = apply_hard_filter(snap, exchanged_within_30_days=False)
    assert r.passed is False
    assert "avg_tenure_unknown" in r.reasons

def test_rejects_recent_exchange() -> None:
    snap = CandidateSnapshot(age=30, years_of_experience=4, job_segment_count=2, total_work_years=4.0)
    r = apply_hard_filter(snap, exchanged_within_30_days=True)
    assert r.passed is False
    assert "exchange_cooldown" in r.reasons
```

```python
# tests/domain/test_fingerprint.py
from resume_domain.fingerprint import candidate_fingerprint

def test_fingerprint_stable_after_normalize() -> None:
    a = candidate_fingerprint(" 张三 ", "阿里巴巴")
    b = candidate_fingerprint("张三", "阿里巴巴")
    assert a == b
    assert len(a) == 64
```

- [ ] **Step 2: 跑测确认失败**

Run: `python -m pytest tests/domain -v`  
Expected: FAIL（模块未安装/未定义）

- [ ] **Step 3: 实现**

```python
# packages/domain/src/resume_domain/hard_filter.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CandidateSnapshot:
    age: int | None
    years_of_experience: float | None
    job_segment_count: int | None
    total_work_years: float | None

@dataclass(frozen=True)
class HardFilterResult:
    passed: bool
    reasons: list[str]

def apply_hard_filter(
    snap: CandidateSnapshot,
    *,
    exchanged_within_30_days: bool,
) -> HardFilterResult:
    reasons: list[str] = []
    if snap.age is None:
        reasons.append("age_unknown")
    elif snap.age > 38:
        reasons.append("age")
    if snap.years_of_experience is None:
        reasons.append("years_unknown")
    elif not (3 <= snap.years_of_experience <= 5):
        reasons.append("years")
    if snap.job_segment_count is None or snap.total_work_years is None:
        reasons.append("avg_tenure_unknown")
    elif snap.job_segment_count <= 0:
        reasons.append("avg_tenure_unknown")
    else:
        avg = snap.total_work_years / snap.job_segment_count
        if not (avg > 1.0):
            reasons.append("avg_tenure")
    if exchanged_within_30_days:
        reasons.append("exchange_cooldown")
    return HardFilterResult(passed=len(reasons) == 0, reasons=reasons)
```

```python
# packages/domain/src/resume_domain/fingerprint.py
from __future__ import annotations
import hashlib
import re

def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())

def candidate_fingerprint(name: str, recent_org: str) -> str:
    raw = f"{_norm(name)}|{_norm(recent_org)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

根 `pyproject.toml` 用 hatchling/setuptools 声明 packages；`Makefile`：

```makefile
test:
	python -m pytest -q

.PHONY: test
```

- [ ] **Step 4: 跑测通过** — `python -m pytest tests/domain -v` Expected: PASS

- [ ] **Step 5: Commit** — `git commit -m "feat(domain): hard filter and fingerprint"`

---

### Task 2: Domain — LLM schema 与阈值决策

**Files:**
- Create: `packages/domain/src/resume_domain/llm_schema.py`
- Create: `packages/domain/src/resume_domain/decision.py`
- Test: `tests/domain/test_llm_schema.py`
- Test: `tests/domain/test_decision.py`

**Interfaces:**
- Produces:
  - `class LlmScoreResult(BaseModel): score: int; reason: str; evidence: list[str]`
  - `def parse_llm_score_payload(raw: str) -> LlmScoreResult`（非法则抛 `ValueError`）
  - `def should_greet(score: int, threshold: int) -> bool`

- [ ] **Step 1: 测试**

```python
from resume_domain.llm_schema import parse_llm_score_payload
from resume_domain.decision import should_greet

def test_parse_valid_json() -> None:
    r = parse_llm_score_payload('{"score": 85, "reason": "匹配", "evidence": ["Python"]}')
    assert r.score == 85

def test_parse_rejects_out_of_range() -> None:
    try:
        parse_llm_score_payload('{"score": 120, "reason": "x", "evidence": []}')
        assert False
    except ValueError:
        pass

def test_should_greet_threshold() -> None:
    assert should_greet(80, 80) is True
    assert should_greet(79, 80) is False
```

- [ ] **Step 2: 实现** — Pydantic v2 model，`score` ge=0 le=100；`should_greet` 为 `score >= threshold`

- [ ] **Step 3: pytest PASS → commit** `feat(domain): llm score schema and greet decision`

---

### Task 3: API 骨架、模型、鉴权、Job CRUD

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/resume_api/main.py`
- Create: `apps/api/src/resume_api/core/config.py`
- Create: `apps/api/src/resume_api/core/db.py`
- Create: `apps/api/src/resume.api` → `resume_api/core/auth.py`
- Create: `apps/api/src/resume_api/models.py`
- Create: `apps/api/src/resume_api/schemas.py`
- Create: `apps/api/src/resume_api/routers/jobs.py`
- Create: `apps/api/src/resume_api/services/jobs.py`
- Create: `.env.example`
- Test: `tests/api/conftest.py`
- Test: `tests/api/test_jobs.py`

**Interfaces:**
- `GET/POST /api/jobs`，`PATCH /api/jobs/{id}`
- Header: `X-Api-Token` 必须等于 `settings.api_token`
- Job 字段：`name`, `jd_text`, `score_threshold` default 80, `greet_template`, `boss_entry_url`, `hourly_greet_limit` default 20, `min_action_delay_ms` default 1500, `max_action_delay_ms` default 4000, `enabled`

- [ ] **Step 1: conftest 用临时 SQLite + TestClient；无 token 401；创建 job 200**

- [ ] **Step 2: 实现 models（SQLAlchemy 2）含 JobPosting / Candidate / Resume / ScoreEvent / OutreachEvent / ExchangeEvent / AgentRun**（本 Task 路由只接 Job；其它表 create_all 一并建好）

- [ ] **Step 3: pytest tests/api/test_jobs.py PASS → commit** `feat(api): job crud and token auth`

---

### Task 4: 候选人、交换冷却、打分/招呼幂等 API

**Files:**
- Create: `apps/api/src/resume_api/routers/candidates.py`
- Create: `apps/api/src/resume_api/routers/events.py`
- Create: `apps/api/src/resume_api/services/candidates.py`
- Create: `apps/api/src/resume_api/services/events.py`
- Test: `tests/api/test_exchange_cooldown.py`
- Test: `tests/api/test_outreach_idempotent.py`

**Interfaces:**
- `POST /api/candidates` upsert by boss_id or fingerprint
- `POST /api/candidates/{id}/exchanges` body `{operator, type}` type ∈ exchange|forward
- `GET /api/candidates/{id}/exchange-blocked?days=30` → `{blocked: bool}`
- `POST /api/events/scores`
- `POST /api/events/outreach` — 若同 job+candidate 已存在则返回已有记录（幂等）
- `GET /api/jobs/enabled` — Agent 拉任务

冷却边界：29 天内 blocked=true；恰好 30*24h 之外 blocked=false（用 `created_at <= now - timedelta(days=30)` 为未阻塞临界：`now - created_at >= 30 days` → 不阻塞）。规格：近 30 天有事件则阻塞。测试冻结时间。

- [ ] 实现 + 测试 PASS → commit `feat(api): candidates exchange scores outreach`

---

### Task 5: 简历上传、解析、文件夹监视

**Files:**
- Create: `apps/api/src/resume_api/parsing.py`
- Create: `apps/api/src/resume_api/services/ingest.py`
- Create: `apps/api/src/resume_api/routers/resumes.py`
- Create: `apps/api/src/resume_api/services/folder_watch.py`
- Test: `tests/api/test_resume_upload.py`
- Test: `tests/api/test_folder_watch.py`

**Interfaces:**
- `POST /api/resumes/upload` multipart: file + optional candidate_id + source
- PDF/DOCX 抽文本；图片 → `parse_status=skipped_image`；失败 → `failed` 仍存原件
- `start_folder_watcher(path, poll_seconds=2)` 后台线程：size 连续两次相同再入库 `source=folder_watch`

- [ ] 测试用临时目录写 `.txt`（解析器对 txt 直接读）与假 pdf 失败路径  
- [ ] commit `feat(api): resume upload parse and folder watch`

---

### Task 6: Agent — LLM adapter、API client、限速、pipeline（fixture）

**Files:**
- Create: `apps/agent/...` 全套
- Create: `tests/fixtures/boss_list.html`
- Test: `tests/agent/test_llm.py`
- Test: `tests/agent/test_parse_page.py`
- Test: `tests/agent/test_pipeline.py`

**Interfaces:**
- `async def score_candidate(jd: str, summary: str) -> LlmScoreResult` — httpx 调 OpenAI 兼容 chat.completions，要求 JSON；最多 2 次重试
- `parse_list_html(html: str) -> list[RawCandidate]` 从 fixture 解析 data 属性
- `async def process_candidate(...)`：查冷却 → 硬筛 → LLM → 达阈值则 outreach（pipeline 对 browser 动作用 protocol/mock）
- `detect_risk_page(html: str) -> bool` 含「验证码」「异常」等关键词则 True

Fixture HTML：3 个候选人卡片，带 `data-age` `data-years` `data-segments` `data-total-years` `data-name` `data-org` `data-boss-id`。

真站选择器集中在 `parse_page.py` 常量；MVP 真站路径用同一解析逻辑的「页面 HTML 快照」模式，CLI 提供 `--fixture` 跑通。

- [ ] commit `feat(agent): llm client pipeline and fixture parsing`

---

### Task 7: Agent CLI + API AgentRun 心跳

**Files:**
- Create: `apps/agent/src/resume_agent/cli.py`
- Create: `apps/api/src/resume_api/routers/agent.py`
- Test: `tests/api/test_agent_run.py`
- Modify: `apps/api/src/resume_api/main.py` 注册路由

**Interfaces:**
- `POST /api/agent/runs` `{machine_id, status}` upsert
- `PATCH /api/agent/runs/{machine_id}` 心跳/错误
- CLI: `python -m resume_agent.cli run --fixture tests/fixtures/boss_list.html`

- [ ] commit `feat(agent): cli and run heartbeat`

---

### Task 8: Vue 3 最小管理台

**Files:**
- Create: `apps/web/*`
- 页面：登录 Token 存 localStorage；Job 列表/创建；候选人搜索；上传简历；标记交换；Agent 状态只读

- [ ] `npm install && npm run build` 成功
- [ ] commit `feat(web): minimal admin console`

---

### Task 9: README、.env.example、make test 一键、规格状态

**Files:**
- Create: `README.md`
- Modify: `.env.example`
- Modify: `Makefile`（test 含 pytest；可选 web build）
- Modify: spec 状态 → 已批准并实现中

- [ ] `make test` PASS
- [ ] commit `docs: readme and env example for mvp`

---

## Self-Review

1. **Spec coverage:** 硬筛/LLM/阈值招呼/共享库/交换冷却/上传+监视/Agent/审计限速风控/Web — 均有对应 Task；真站 DOM 以 fixture+可配选择器交付，人工验收写在 README。
2. **Placeholders:** 无 TBD；图片 OCR 明确不在 MVP。
3. **Types:** `CandidateSnapshot` / `LlmScoreResult` / Job 字段名与 API schemas 保持一致。

## Execution

用户已要求「写完计划直接写代码」→ 采用 **Inline Execution（executing-plans）**，在分支 `feat/mvp-resume-screening` 上按 Task 1→9 推进。
