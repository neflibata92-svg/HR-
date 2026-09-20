# HR 账号管理与首次改密 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 同步完善 LEION HR 原型与真实系统，使 HR 总负责人可安全创建、停用、启用和重置普通 HR 账号，并强制临时密码用户首次改密。

**Architecture:** 沿用 `admin/member`，在 `User` 增加首次改密状态；FastAPI 服务层集中执行账号规则，鉴权依赖统一约束 JWT、Refresh Token 和 API Key。所有 HR 共用一套后端 API，但每位 HR 使用独立 JWT 和个人 Agent API Key；大模型等第三方 API Key 只由后端集中保管，Agent 经后端评分接口调用第三方服务。Vue 将账号管理与首次改密拆为独立组件，`App.vue` 只编排登录、强制改密和工作台状态。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy 2、Pydantic 2、Pytest、Vue 3、TypeScript、Vite、Vitest、Vue Test Utils、Playwright

**Spec:** `docs/superpowers/specs/2026-09-20-hr-account-management-design.md`

## Global Constraints

- `admin/member` 分别显示“HR 总负责人”和“HR”；管理接口只能创建和操作 `member`。
- “删除”是 `is_active=false` 的软停用；不物理删除用户或历史数据。
- 新建和重置 HR 密码后设置 `must_change_password=true`。
- 未完成首次改密的用户只能访问 `/auth/me` 和 `/auth/change-password`；后端必须拦截业务接口。
- 停用后 JWT、Refresh Token、API Key 立即失效。
- 用户名长度 2–100；密码长度 8–128，且新密码不能等于当前密码。
- 不新增角色、不引入 RBAC、不开放普通 HR 自助注册。
- 每位 HR 使用独立 JWT 与个人 Agent API Key，不允许多人共用同一系统凭据。
- 第三方 `LLM_API_KEY` 只存在于 API 服务端环境或 Secret 管理系统，不进入 Web bundle、本机 Agent 配置、用户数据或 API 响应。
- Agent 的评分请求统一发送到后端；后端缺少第三方密钥时必须明确失败，不得返回固定占位分。
- 未经用户明确要求不得提交或推送 Git。

## Review Focus

- 创建请求携带 `role=admin` 等额外字段时必须返回 `422`。
- 用户名首尾空格、全空格和大小写碰撞必须规范化后判重。
- 并发创建同名用户触发唯一约束时必须回滚并返回可读 `400`。
- 管理员重置密码后，目标用户的旧 JWT 访问业务 API 必须返回 `403`。
- 停用再启用后，当前无 token-version 机制，未过期旧凭据会恢复可用；测试不得声称永久吊销。

---

### Task 1: 静态原型账号管理与首次改密

**Files:**
- Modify: `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`
- Modify: `tests/prototype/test_login_prototype.py`

**Interfaces:**
- Consumes: 现有 `showPage()`、`notify()` 和登录表单。
- Produces: `#accountManagement`、`#passwordChangeScreen`；原型内存账号的新增、停用、启用和首次改密交互。

- [ ] **Step 1: 写失败的原型测试**

在 `test_login_prototype.py` 增加：管理员登录后进入系统设置，点击“新增 HR”，提交 `lisi/tempPass8` 后列表出现 `lisi`；点击 `aria-label="停用 lisi"` 并二次确认后状态为“已停用”；点击 `aria-label="重新启用 lisi"` 后状态为“正常”。再增加 `new.hr` 登录后只显示 `#passwordChangeScreen`，填写当前密码、新密码和确认密码后进入 `.shell` 的测试。

- [ ] **Step 2: 验证测试先失败**

Run: `python -m pytest tests/prototype/test_login_prototype.py -v`

Expected: 找不到账号管理区或首次改密页而失败。

- [ ] **Step 3: 实现原型内存数据和交互**

使用：

```js
const demoHrAccounts = [
  { username: "wang.hr", active: true, mustChangePassword: false },
  { username: "new.hr", active: true, mustChangePassword: true }
];
```

在系统设置增加账号表格、新建弹窗、停用确认和“不保存数据”提示。新建时执行 `trim()`、用户名至少 2 位、密码至少 8 位、两次密码一致；所有操作仅更新数组并重新渲染。管理员行无操作按钮。

- [ ] **Step 4: 实现首次改密演示**

约定 `new.hr` 为临时密码账号；登录后隐藏 `.shell`，显示改密页。表单验证成功后进入工作台；其他非空账号保持原有演示登录。

- [ ] **Step 5: 验证原型**

Run: `python -m pytest tests/prototype/test_login_prototype.py -v`

Expected: 全部通过。

---

### Task 2: 首次改密字段与幂等迁移

**Files:**
- Modify: `apps/api/src/resume_api/models.py`
- Modify: `apps/api/src/resume_api/core/db.py`
- Create: `apps/api/src/resume_api/migrations/__init__.py`
- Create: `apps/api/src/resume_api/migrations/runner.py`
- Create: `tests/api/test_migrations.py`

**Interfaces:**
- Produces: `User.must_change_password: bool`；`run_migrations(engine: Engine) -> None`。

- [ ] **Step 1: 写旧数据库升级失败测试**

测试先用 SQL 建立不含新字段的 `users` 表并插入管理员，再连续调用两次 `run_migrations(engine)`；断言字段存在、旧管理员仍存在且值为 `false`。另测没有 `users` 表时迁移器安全返回。

- [ ] **Step 2: 验证测试先失败**

Run: `python -m pytest tests/api/test_migrations.py -v`

Expected: 迁移模块不存在。

- [ ] **Step 3: 增加模型字段和迁移器**

```python
must_change_password: Mapped[bool] = mapped_column(
    Boolean, nullable=False, default=False, server_default=false()
)
```

`run_migrations()` 用 `inspect(engine)` 判断表和字段；旧表执行：

```sql
ALTER TABLE users ADD COLUMN must_change_password BOOLEAN NOT NULL DEFAULT FALSE
```

`init_db()` 先 `Base.metadata.create_all()`，再 `run_migrations(engine)`；SQLite 与 PostgreSQL 共用该迁移。

- [ ] **Step 4: 验证迁移与认证回归**

Run: `python -m pytest tests/api/test_migrations.py tests/api/test_auth.py -v`

Expected: 全部通过。

---

### Task 3: 管理员账号管理 API

**Files:**
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/services/auth_service.py`
- Modify: `apps/api/src/resume_api/routers/auth.py`
- Create: `tests/api/test_hr_account_management.py`

**Interfaces:**
- Produces: `GET/POST /auth/users`、`PATCH /auth/users/{id}/status`、`POST /auth/users/{id}/reset-password`；`list_users()`、`set_member_status()`、`reset_member_password()`。

- [ ] **Step 1: 写失败的 API 测试**

覆盖：管理员列表并创建固定 `member`；创建返回 `201`、`must_change_password=true`；`role=admin` 额外字段返回 `422`；member 调四类管理接口均 `403`；用户名空白/规范化重复；并发唯一约束转 `400`；状态切换幂等；不存在 `404`；任何 admin 目标的状态切换和重置均 `403`；重置后强制改密。

- [ ] **Step 2: 验证测试先失败**

Run: `python -m pytest tests/api/test_hr_account_management.py -v`

Expected: 缺端点、字段或 schema。

- [ ] **Step 3: 增加严格 schema**

```python
class AdminCreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=2, max_length=100)
    temporary_password: str = Field(min_length=8, max_length=128)

class UserStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool

class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temporary_password: str = Field(min_length=8, max_length=128)
```

`username` validator 返回 `value.strip().lower()` 并拒绝规范化后不足 2 位。`UserOut` 增加 `must_change_password` 和 `created_at`。

- [ ] **Step 4: 实现服务规则**

`admin_create_user()` 写死 `role="member"`、`is_active=True`、`must_change_password=True`。私有 `_get_managed_member()` 对不存在用户抛 `LookupError`，对非 member 抛 `PermissionError`。`IntegrityError` 必须回滚并转换为 `ValueError("username taken")`。

- [ ] **Step 5: 接入四个路由**

所有路由使用 `require_admin`。映射 `LookupError→404`、`PermissionError→403`、`ValueError→400`。创建使用 `status_code=201`；状态相同时返回当前用户。

- [ ] **Step 6: 验证 API**

Run: `python -m pytest tests/api/test_hr_account_management.py tests/api/test_auth.py -v`

Expected: 全部通过。

---

### Task 4: 首次改密与凭据限制

**Files:**
- Modify: `apps/api/src/resume_api/core/auth.py`
- Modify: `apps/api/src/resume_api/services/auth_service.py`
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/routers/auth.py`
- Modify: `apps/api/src/resume_api/routers/{jobs,candidates,events,resumes,agent}.py`
- Create: `tests/api/test_first_password_change.py`

**Interfaces:**
- Produces: `CurrentUser.must_change_password`、`require_password_change_complete()`、`POST /auth/change-password -> TokenResponse`。

- [ ] **Step 1: 写失败的改密与停用测试**

覆盖：临时密码可登录和访问 `/auth/me`，但 `/api/jobs` 返回 `403`；正确当前密码改密后返回新 token 且业务访问成功；错误当前密码失败；新旧密码相同失败；API Key 改密为 `403`；管理员重置后旧 JWT 业务请求为 `403`；停用后旧 access token、refresh token、API Key 均 `401`；重新启用后未过期旧凭据按现设计恢复可用。

- [ ] **Step 2: 验证测试先失败**

Run: `python -m pytest tests/api/test_first_password_change.py -v`

Expected: 缺少改密端点和业务限制。

- [ ] **Step 3: 扩展当前用户和依赖**

```python
@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: str
    auth_via: str
    must_change_password: bool


def require_password_change_complete(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="password change required")
    return user
```

JWT、API Key、开发 token 三条路径都填充该字段。

- [ ] **Step 4: 实现改密端点**

`ChangePasswordRequest` 含 `current_password` 和 8–128 位 `new_password`，禁止额外字段。服务验证当前密码，拒绝相同密码，更新哈希并置 `must_change_password=False`。路由只接受 `auth_via="jwt"`，成功后签发新 tokens。

- [ ] **Step 5: 后端拦截所有受保护功能**

五个业务 router 的依赖改为 `require_password_change_complete`；`candidates.py` 中需要当前用户的端点也改用该依赖。`require_admin` 改为依赖 `require_password_change_complete`，三个 API Key 端点同样改用 `require_password_change_complete`。仅 `/auth/me` 和 `/auth/change-password` 保持基础 `get_current_user`；登录与改密所需的公开登录流程不变。

- [ ] **Step 6: 验证完整 API**

Run: `python -m pytest tests/api -v`

Expected: 全部通过。

---

### Task 5: Web API 与独立组件

**Files:**
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Modify: `apps/web/vite.config.ts`
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/styles.css`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/src/components/HrAccountManagement.vue`
- Create: `apps/web/src/components/FirstPasswordChange.vue`
- Create: `apps/web/src/components/__tests__/{HrAccountManagement,FirstPasswordChange}.spec.ts`

**Interfaces:**
- Produces: `UserMe`、`UserRow`、`TokenResponse`；账号管理 API 函数；两个可独立测试的 Vue 组件。

- [ ] **Step 1: 配置 Web 测试**

Run: `cd apps/web && npm install -D vitest@^2.1.8 @vue/test-utils@^2.4.6 jsdom@^25.0.1`

增加脚本 `"test": "vitest run"`；`vitest.config.ts` 使用 Vue 插件、`environment: "jsdom"`、`clearMocks: true`。

- [ ] **Step 2: 写失败的组件测试**

账号组件覆盖：角色文案、admin 行无操作、新建字段、确认密码不一致、取消停用、停用失败不改本地状态、启用成功、重置密码确认。改密组件覆盖：三个字段、确认不一致、当前密码错误、提交防重复、成功 emit 新 tokens。

- [ ] **Step 3: 验证测试先失败**

Run: `cd apps/web && npm run test -- src/components/__tests__/HrAccountManagement.spec.ts src/components/__tests__/FirstPasswordChange.spec.ts`

Expected: 组件/API 不存在。

- [ ] **Step 4: 扩展 API 客户端**

`UserMe` 增加联合角色与 `must_change_password`；`UserRow` 增加 `created_at`；统一 `TokenResponse`。增加 `listUsers()`、`createHr()`、`setUserStatus()`、`resetUserPassword()`、`changePassword()`；JSON 字段严格匹配设计。Vite 代理增加 `/auth`。

- [ ] **Step 5: 实现组件**

`HrAccountManagement` 自行加载列表，只在 API 成功后替换行；member 操作按钮的 `aria-label` 含用户名，admin 行无操作。`FirstPasswordChange` 不展示业务内容，成功后 emit `changed(accessToken, refreshToken)`，并提供 `logout`。

- [ ] **Step 6: 验证组件和构建**

Run: `cd apps/web && npm run test && npm run build`

Expected: 测试与构建全部通过。

---

### Task 6: 第三方 LLM 调用集中到后端

**Files:**
- Modify: `apps/api/src/resume_api/core/config.py`
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/main.py`
- Modify: `apps/api/pyproject.toml`
- Create: `apps/api/src/resume_api/services/llm.py`
- Create: `apps/api/src/resume_api/routers/scoring.py`
- Modify: `apps/agent/src/resume_agent/config.py`
- Modify: `apps/agent/src/resume_agent/api_client.py`
- Modify: `apps/agent/src/resume_agent/cli.py`
- Modify: `apps/agent/src/resume_agent/pipeline.py`
- Modify: `apps/agent/src/resume_agent/runner.py`
- Modify: `apps/agent/src/resume_agent/live_runner.py`
- Delete or replace: `apps/agent/src/resume_agent/llm.py`
- Modify: `packages/domain/src/resume_domain/llm_schema.py`
- Modify: `.env.example`
- Modify: `deploy/docker-compose.yml`
- Modify: `deploy/Dockerfile.api`
- Create: `tests/api/test_llm_service.py`
- Create: `tests/api/test_scoring.py`
- Create: `tests/agent/test_api_scoring.py`
- Modify: `tests/agent/test_pipeline.py`
- Modify or replace: `tests/agent/test_llm.py`
- Modify: `tests/domain/test_llm_schema.py`

**Interfaces:**
- Produces: `POST /api/scoring/evaluate`；API 端 `score_candidate()`；Agent 端通过个人 `X-Api-Key` 使用统一后端评分。
- Security boundary: `LLM_API_KEY` 仅 API 服务端持有；Agent 只持有绑定具体 HR 的系统 API Key。

- [ ] **Step 1: 写失败的 API 端 LLM 服务测试**

覆盖：使用后端配置的供应商地址、模型和密钥；合法 JSON 正确解析；无效分数或非 JSON 被拒绝；上游 HTTP 失败最多尝试三次；未配置密钥立即报服务不可用；返回和异常中不包含供应商密钥；绝不产生固定 80 分占位结果。测试 mock `httpx`，不访问真实供应商。

- [ ] **Step 2: 实现 API 端供应商适配器**

将 `SCORE_PROMPT`、`/chat/completions` 请求、重试和 `parse_llm_score_payload()` 从 Agent 迁入 `apps/api/src/resume_api/services/llm.py`。`Settings` 增加 `llm_base_url`、`llm_api_key`、`llm_model`、超时和重试配置；日志与错误不得输出密钥或完整认证头。

- [ ] **Step 3: 写失败的评分路由测试**

覆盖：无凭据 `401`；个人系统 API Key 可调用；被停用 HR 或已吊销 Key 返回 `401`；临时密码未修改的账号返回 `403`；空 JD/摘要返回 `422`；上游错误转 `502`；后端未配置供应商 Key 转 `503`；响应只有 `score/reason/evidence/model`，不包含第三方密钥。

- [ ] **Step 4: 实现并注册统一评分接口**

增加严格的 `ScoreEvaluateRequest` 与 `ScoreEvaluateOut`，实现 `POST /api/scoring/evaluate`，鉴权使用 `require_password_change_complete`。在 `main.py` 注册路由，并在 API 包与 Docker 镜像中补齐 `httpx`。生产配置通过服务器环境或 Secret 注入 `LLM_API_KEY`，不得硬编码进仓库。

- [ ] **Step 5: 写失败的 Agent 远程评分测试**

覆盖：Agent 请求 `/api/scoring/evaluate`；请求头只带个人系统 `X-Api-Key`；请求体只含 JD 与候选人摘要；保留服务端返回的 `model`；后端 `401/502` 或超时进入现有 `score_error`；硬筛失败时不调用评分接口。

- [ ] **Step 6: 将 Agent 改为只调用统一后端**

在 `ApiClient` 增加 `score_candidate()` 并满足 `Scorer` 协议；CLI 不再创建直连供应商的 `LlmScorer`。从 `AgentSettings` 删除 `llm_base_url/llm_api_key/llm_model`，删除或改写旧 `llm.py`，移除“无密钥固定 80 分”。评分响应的 `model` 经 `ProcessResult` 传给 score event，runner 不再读取本地模型配置。

- [ ] **Step 7: 更新环境边界并验证**

`.env.example` 明确区分“API 服务器专用第三方密钥”和“Agent 个人系统 API Key”；Compose 只向 API 容器注入第三方配置。运行：

```bash
python -m pytest tests/api/test_llm_service.py tests/api/test_scoring.py -v
python -m pytest tests/agent/test_api_scoring.py tests/agent/test_pipeline.py -v
python -m pytest tests/domain/test_llm_schema.py -v
```

再搜索 `apps/agent` 生产代码，确认不再包含 `LLM_API_KEY`、`llm_api_key` 或 `/chat/completions`。

---

### Task 7: 根应用编排与全量回归

**Files:**
- Modify: `apps/web/src/App.vue`
- Modify: `apps/web/src/styles.css`
- Modify: `Makefile`
- Modify: `README.md`
- Create: `apps/web/src/__tests__/App.spec.ts`

**Interfaces:**
- Consumes: Task 5 的组件与 API。
- Produces: 登录 → 首次改密 → 工作台状态流；仅 admin 可见账号管理；`make test-all`。

- [ ] **Step 1: 写失败的根应用测试**

覆盖：无 token 只显示登录；member 工作台无账号管理；admin 有账号管理；`must_change_password=true` 时只显示改密组件，且 `listJobs/listCandidates/listAgentRuns/listApiKeys` 均未调用；改密成功替换 token 后加载工作台；`/auth/me` 返回 `401` 清 token。

- [ ] **Step 2: 验证测试先失败**

Run: `cd apps/web && npm run test -- src/__tests__/App.spec.ts`

Expected: 根组件尚无三态编排。

- [ ] **Step 3: 重构加载顺序并接入组件**

拆出 `loadCurrentUser()` 与 `loadWorkspace()`。登录后先 `setTokens()`，再请求 `me()`；需要改密时不调用任何工作台 API。改密组件 emit 新 token 后重新请求 `me()`，确认状态解除再加载工作台。正常工作台中仅 `user.role === "admin"` 渲染 `HrAccountManagement`。

- [ ] **Step 4: 增加统一验证入口与运行说明**

`Makefile` 增加：

```make
test-web:
	cd apps/web && npm run test

build-web:
	cd apps/web && npm run build

test-all: test test-web build-web
```

更新 `README.md`：管理员账号管理、临时密码首次改密、软停用语义、统一后端 API、每位 HR 独立账号与个人 Agent API Key、第三方 API Key 仅后端保管，以及 `make test-all`；不写真实密码或密钥。

- [ ] **Step 5: 运行全量验证**

Run:

```bash
python -m pytest tests/api -v
python -m pytest tests/prototype -v
make test-all
git diff --check
```

Expected: Python、原型、Web 测试和 Web 构建全部通过，`git diff --check` 无输出。

- [ ] **Step 6: 对照规格验收**

逐项核对：管理员只能管理 member；临时密码强制改密；业务后端限制；三类凭据停用失效；多位 HR 使用独立账号和个人系统 API Key；Agent 不持有第三方 API Key；原型演示完整；普通 HR 无入口；无物理删除。

- [ ] **Step 7: 准备最终存档（仅在用户授权后执行）**

建议存档名：`新增-HR账号管理和首次改密功能`
