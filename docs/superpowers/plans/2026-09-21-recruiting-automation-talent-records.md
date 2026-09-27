# LEION HR 招聘自动化与人才档案升级 Implementation Plan

> **执行要求：** 使用 `subagent-driven-development`（推荐）或 `executing-plans` 逐任务实施。每项先写失败测试，再做最小实现。未经用户明确要求，不提交或推送 Git。

**Goal:** 在现有 Vue 3、FastAPI 和本机 Playwright Agent 上实现候选人多岗位、简历版本、可逆合并、人工复核、`1–50` 人筛选任务及跨岗位联系去重。

**Architecture:** FastAPI/数据库是任务事实来源；Agent 只领取任务并操作 HR 当前打开的 BOSS 候选人结果页；Vue 管理台负责配置、控制、复核和档案管理。浏览器 DOM 操作集中在 `BossLiveSession`，不扩散到业务层。

**Spec:** `docs/superpowers/specs/2026-09-21-recruiting-automation-talent-records-design.md`

## 全局约束

- 开发前创建独立 worktree，不影响当前可运行工作区。
- 不自动设置 BOSS 筛选条件；不绕过验证码、风控或登录限制。
- 单次任务严格限制为 `1–50` 人，不无限运行。
- 自动发送必须同时满足：分数达标、关键资料完整、全局未联系、身份复核、模板渲染成功。
- 点击发送不算成功；页面确认消息出现后才记录 `confirmed`。
- 未知资料与明确不符合必须分开；普通缺失项按对应正向评分项零贡献并记录，关键资料缺失进入人工复核。
- 历史候选人、简历、评分、联系、任务和合并记录不物理删除。
- `admin/lead` 可合并、撤销和授权重发；只有 `admin` 可管理用户。
- 日志不得包含完整电话、邮箱、简历正文、JWT、API Key 或浏览器会话信息。
- API 和 Agent 需同批升级；迁移必须幂等。

## 重点风险

1. `migrations/runner.py` 当前检测到旧字段后会整体返回，必须改为逐步骤迁移。
2. SQLite 无法直接删除旧联系唯一约束，需要重建表并保留 ID。
3. 当前 `process_candidate()` 忽略 `greeter.greet()` 返回值，可能把失败发送记为成功。
4. `live-{index}` 不是稳定 BOSS ID，禁止用于持久去重和恢复。
5. 任务恢复必须读取服务端 `ScreeningTaskItem`，不能依赖本地循环下标。
6. 简历版本并发、合并和撤销均必须由数据库事务和约束兜底。

---

### Task 1: 角色权限与可持续迁移框架

**Files**
- Modify: `apps/api/src/resume_api/{models.py,schemas.py}`
- Modify: `apps/api/src/resume_api/core/auth.py`
- Modify: `apps/api/src/resume_api/services/auth_service.py`
- Modify: `apps/api/src/resume_api/routers/auth.py`
- Modify: `apps/api/src/resume_api/migrations/runner.py`
- Modify: `tests/api/{test_migrations.py,test_hr_account_management.py,test_auth.py}`

- [ ] 写失败测试：管理员可创建 `member/lead` 但不能创建 `admin`；`lead` 无账号管理权；`require_lead_or_admin()` 允许 `admin/lead`、拒绝 `member`。
- [ ] 写失败测试：旧库已有 `must_change_password` 时仍执行后续迁移；迁移连续运行两次不重复加列、表或数据。
- [ ] Run: `python -m pytest tests/api/test_migrations.py tests/api/test_hr_account_management.py tests/api/test_auth.py -v`，确认先失败。
- [ ] 将迁移器改为逐步骤探测并执行，不再因单字段存在而整体返回；兼容 SQLite/PostgreSQL 方言。
- [ ] `AdminCreateUserRequest` 增加严格角色枚举；新增 `require_lead_or_admin()`，继续保留 `require_admin()` 的账号管理边界。
- [ ] 重跑上述测试，预期全部通过。

---

### Task 2: 核心模型、约束与历史回填

**Files**
- Modify: `apps/api/src/resume_api/{models.py,schemas.py}`
- Modify: `apps/api/src/resume_api/migrations/runner.py`
- Modify: `tests/api/test_migrations.py`
- Create: `tests/api/test_talent_models.py`

**Models:** `CandidateJob`、扩展 `Candidate/Resume/ScoreEvent/OutreachEvent`、`ScreeningTask`、`ScreeningTaskItem`、`CandidateMerge`、`CandidateMergeSuggestion`、`OutreachOverride`、`AuditEvent`。

- [ ] 用 legacy SQLite 表写失败测试：原 ID/文件/事件数量保留；历史 `candidate_id+job_id` 回填唯一 `CandidateJob`；简历按候选人和时间回填版本；无候选人简历保持待认领。
- [ ] 测试唯一约束：`CandidateJob(candidate_id,job_id)`、`Resume(candidate_id,version_number)`、候选人内文件哈希、`ScreeningTaskItem(task_id,candidate_id)`。
- [ ] Run: `python -m pytest tests/api/test_talent_models.py tests/api/test_migrations.py -v`，确认先失败。
- [ ] 增加模型和索引；JSON 暂用 `Text` 统一序列化，保持 SQLite/PostgreSQL 兼容。
- [ ] 按“建表→补列→回填关联→回填版本→重建 SQLite 联系表→补约束”实施事务迁移；旧成功联系映射为 `confirmed`。
- [ ] Run: `python -m pytest tests/api/test_talent_models.py tests/api/test_migrations.py tests/api/test_outreach_idempotent.py tests/api/test_resume_upload.py -v`。

---

### Task 3: 候选人身份、多岗位与简历版本

**Files**
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/services/{candidates.py,ingest.py,folder_watch.py}`
- Modify: `apps/api/src/resume_api/routers/{candidates.py,resumes.py}`
- Create: `apps/api/src/resume_api/services/audit.py`
- Create: `tests/api/{test_candidate_identity.py,test_candidate_jobs.py,test_resume_versions.py}`
- Modify: `tests/api/{test_resume_upload.py,test_folder_watch.py,test_exchange_cooldown.py}`

- [ ] 写失败测试：电话标准化、邮箱 trim/lowercase；相同电话或邮箱只产生疑似重复，不静默合并；空 `boss_id` 不生成伪稳定 ID。
- [ ] 写失败测试：同一候选人关联多个岗位，状态和 `active_resume_id` 相互隔离；候选人列表可按岗位、状态、最低分、待复核过滤，默认排除已合并来源。
- [ ] 写失败测试：同候选人不同文件生成递增版本；同候选人同哈希幂等；新版不自动切换岗位版本或触发重评；文件夹监听可创建待认领版本。
- [ ] Run: `python -m pytest tests/api/test_candidate_identity.py tests/api/test_candidate_jobs.py tests/api/test_resume_versions.py -v`，确认先失败。
- [ ] 扩展候选人详情和 `/api/candidates/{id}/jobs`；保留旧 upsert 兼容，但已合并来源解析到目标主体。
- [ ] 上传时计算 SHA-256，使用临时文件+事务+最终移动；Web 上传要求候选人，监听器允许待认领。
- [ ] 增加 `GET /api/resumes?candidate_id=&job_id=` 和 `PATCH /api/candidates/{id}/jobs/{job_id}/active-resume`；切换只写审计，不自动评分。
- [ ] Run: `python -m pytest tests/api/test_candidate_identity.py tests/api/test_candidate_jobs.py tests/api/test_resume_versions.py tests/api/test_resume_upload.py tests/api/test_folder_watch.py -v`。

---

### Task 4: 字段级合并与事务性撤销

**Files**
- Modify: `apps/api/src/resume_api/schemas.py`
- Create: `apps/api/src/resume_api/services/candidate_merges.py`
- Create: `apps/api/src/resume_api/routers/candidate_merges.py`
- Modify: `apps/api/src/resume_api/{main.py}`
- Create: `tests/api/{test_candidate_merge.py,test_candidate_merge_revert.py,test_candidate_merge_permissions.py}`

- [ ] 写失败测试：member 只能建议；admin/lead 可预览、执行、撤销；相同主体、合并环和已合并来源被拒绝。
- [ ] 写失败测试：逐字段选择后，简历、岗位、评分、任务、联系和交换历史均保留；来源仅软标记。
- [ ] 写失败测试：无冲突撤销完整恢复；合并后新增且归属不明的数据返回冲突清单并整笔回滚；重复撤销幂等。
- [ ] Run: `python -m pytest tests/api/test_candidate_merge.py tests/api/test_candidate_merge_revert.py tests/api/test_candidate_merge_permissions.py -v`，确认先失败。
- [ ] 在单事务中锁定主体和关联数据；先写完整 JSON 快照，再迁移外键、处理同岗位状态和简历重编号。
- [ ] 撤销先做只读冲突预检；无冲突才按快照原子恢复。审计只记录 ID、动作和结果。
- [ ] 注册 `/api/candidate-merges`、预览和 `/{id}/revert`，使用 `require_lead_or_admin()`。
- [ ] 重跑三组测试，预期全部通过。

---

### Task 5: 评分扩展、关键资料与人工复核

**Files**
- Modify: `packages/domain/src/resume_domain/{hard_filter.py,llm_schema.py}`
- Modify: `apps/api/src/resume_api/{schemas.py,main.py}`
- Modify: `apps/api/src/resume_api/services/llm.py`
- Create: `apps/api/src/resume_api/services/reviews.py`
- Modify/Create: `apps/api/src/resume_api/routers/{jobs.py,scoring.py,reviews.py}`
- Modify: `tests/domain/{test_hard_filter.py,test_llm_schema.py}`
- Modify: `tests/api/{test_llm_service.py,test_scoring.py}`
- Create: `tests/api/{test_critical_fields.py,test_reviews.py}`

- [ ] 写失败测试：硬筛拆为明确拒绝原因和未知字段；未知年龄/年限/任职信息不直接拒绝，明确超限仍拒绝。
- [ ] 写失败测试：关键资料建议返回稳定键、中文名和理由；失败时不伪造建议；岗位阈值 `0–100`，模板只允许 `{{candidate_name}}`、`{{job_name}}`。
- [ ] 写失败测试：评分包含 evidence、missing、estimated、critical、confidence、decision；高分但关键缺失为 `needs_review`。
- [ ] 写失败测试：复核可按岗位查询；补资料、关联版本、归档和手动重评均写审计；重评新增历史且不自动联系。
- [ ] Run: `python -m pytest tests/domain tests/api/test_critical_fields.py tests/api/test_scoring.py tests/api/test_reviews.py -v`，确认先失败。
- [ ] 扩展严格 LLM Schema 和 prompt；未知普通字段不得被猜测为满足，按正向项零贡献并记录 estimated。
- [ ] 增加 `/api/jobs/{id}/critical-fields/suggest`、`GET/PATCH /api/reviews`、`POST /api/candidates/{id}/jobs/{job_id}/re-evaluate`。
- [ ] Run: `python -m pytest tests/domain tests/api/test_llm_service.py tests/api/test_scoring.py tests/api/test_critical_fields.py tests/api/test_reviews.py -v`。

---

### Task 6: 任务状态机与全局联系去重

**Files**
- Modify: `apps/api/src/resume_api/{schemas.py,main.py}`
- Modify: `apps/api/src/resume_api/routers/events.py`
- Create: `apps/api/src/resume_api/services/{screening_tasks.py,outreach.py}`
- Create: `apps/api/src/resume_api/routers/{screening_tasks.py,outreach.py}`
- Create: `tests/api/{test_screening_tasks.py,test_screening_task_items.py,test_screening_task_state_machine.py,test_global_outreach_dedup.py}`
- Modify: `tests/api/{test_outreach_idempotent.py,test_outreach_lookup.py}`

- [ ] 写失败测试：人数 `0/1/50/51`；任务要求启用岗位和已确认关键资料；启动后岗位、人数、JD、阈值、模板和关键资料快照锁定。
- [ ] 写失败测试：合法状态转换和非法转换 `409`；Agent 原子 claim；第二台机器不能重复领取；任务项幂等；汇总数字由数据库重算。
- [ ] 写失败测试：任一岗位已有成功联系即阻止其他岗位自动发送；`sending` 超时进入人工核验；发送采用 `sending→confirmed/failed` 两阶段。
- [ ] 写失败测试：admin/lead 可创建指定候选人+岗位的一次性重发授权，member 被拒绝，授权消费后不可复用。
- [ ] Run: `python -m pytest tests/api/test_screening_tasks.py tests/api/test_screening_task_items.py tests/api/test_screening_task_state_machine.py tests/api/test_global_outreach_dedup.py -v`，确认先失败。
- [ ] 实现任务 CRUD、`start/pause/resume/cancel`、Agent `claim/items/complete/fail`；服务端校验归属、状态和幂等。
- [ ] 实现联系预留、确认、失败和 override；旧事件端点短期委托新服务，统一执行全局规则。
- [ ] Run: `python -m pytest tests/api/test_screening_tasks.py tests/api/test_screening_task_items.py tests/api/test_screening_task_state_machine.py tests/api/test_global_outreach_dedup.py tests/api/test_outreach_idempotent.py tests/api/test_outreach_lookup.py -v`。

---

### Task 7: 将 Agent 改为服务端任务驱动

**Files**
- Modify: `apps/agent/src/resume_agent/{api_client.py,cli.py,config.py,pipeline.py,runner.py,live_runner.py,boss_live.py,selectors.py}`
- Modify: `apps/agent/boss_selectors.json`
- Modify: `tests/agent/{test_pipeline.py,test_api_scoring.py}`
- Create: `tests/agent/{test_task_api_client.py,test_task_runner.py,test_live_runner.py,test_boss_live.py}`
- Modify/Create: `tests/fixtures/boss_*.html`

- [ ] 写失败测试：高分且关键资料完整才发送；关键缺失转复核；普通缺失记录估算；`greet()` 返回 false 时不得标记成功。
- [ ] 写失败测试：claim、任务项幂等、暂停和完成请求；处理数量严格为 1/50/页面不足；恢复跳过已终态项。
- [ ] 写失败测试：不导航到岗位入口、不操作筛选器；当前页错误、登录失效、验证码、风控和 API 不可达立即停止；连续三次同类 DOM 错误暂停。
- [ ] 写失败测试：发送前复核候选人身份，发送后验证消息；`live-{index}` 不作为 boss_id。
- [ ] Run: `python -m pytest tests/agent -v`，确认新测试先失败。
- [ ] 扩展 `ApiClient` 的 claim/item/outreach/task 方法；CLI 提供任务运行入口，不再默认取 `jobs[0]`。
- [ ] 重构 pipeline 输出完整决策和字段信息；只有 Greeter 返回并验证成功才为 contacted。
- [ ] `run_live_round()` 改为使用当前已打开结果页，最多处理任务请求数，以服务端任务项判断恢复位置。
- [ ] 扩展选择器和页面分类；旧 JSON 新字段可缺省，避免配置加载失败。
- [ ] Run: `python -m pytest tests/agent -v`，预期全部通过。

---

### Task 8: Web API、任务控制与真实业务页面

**Files**
- Modify: `apps/web/src/{api.ts,types.ts,styles.css,App.vue}`
- Modify: `apps/web/src/layouts/AppShell.vue`
- Modify: `apps/web/src/pages/{DashboardPage.vue,JobsPage.vue,CandidatesPage.vue,ResumesPage.vue,SettingsPage.vue}`
- Create: `apps/web/src/pages/ReviewsPage.vue`
- Create: `apps/web/src/components/{ScreeningTaskForm.vue,CandidateMergeDrawer.vue,CandidateTimeline.vue,ScoreEvidence.vue}`
- Modify: `apps/web/src/components/HrAccountManagement.vue`
- Modify/Create: 对应 `apps/web/src/**/__tests__/*.spec.ts`

- [ ] 先扩展 `api.ts` 类型和函数：`lead`、CandidateJob、版本、评分、任务、复核、合并、审计；查询错误支持解析结构化冲突详情，并保留现有 401 事件。
- [ ] 写失败测试：Dashboard 创建任务时建议可增删、人数仅 `1–50`、启动后锁定、按钮服从状态机、真实计数显示。
- [ ] 写失败测试：Jobs 模板白名单和关键资料建议；继续不展示岗位独立额度。
- [ ] 写失败测试：Candidates 多岗位/分数/状态筛选、证据时间线、角色权限、字段级合并、撤销冲突和重发理由。
- [ ] 写失败测试：Resumes 强制先选岗位和候选人、版本时间线、新版不自动切换、选择版本后手动重评。
- [ ] 写失败测试：Reviews 展示关键缺失、普通估算、置信度、证据、模型和任务来源；补资料后不自动恢复旧任务发送。
- [ ] 写失败测试：Settings 显示 lead；账号管理仅 admin 可见并可创建 member/lead；BOSS 登录状态无真实接口时不得推断为已登录。
- [ ] Run: `cd apps/web && npm run test`，确认新测试先失败。
- [ ] 依次实现 API 类型、共享组件、Dashboard、Jobs、Candidates、Resumes、Reviews 和 Settings；沿用现有 LEION HR 视觉，不加入演示数据。
- [ ] 在 `types.ts`/`AppShell.vue` 注册 `reviews` 页面并更新导航测试；`App.vue` 保证 lead 正常进入工作台但无管理员能力。
- [ ] Run: `cd apps/web && npm run test && npm run build`。

---

### Task 9: 回归、迁移与人工验收

**Files**
- Modify: `Makefile`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `deploy/docker-compose.yml`（仅新增已实现的安全配置）
- Optionally Modify: `pyproject.toml`、`apps/api/pyproject.toml`（仅在加入 PostgreSQL 测试驱动时）

- [ ] 在 `Makefile` 增加 `test-domain`、`test-api`、`test-agent`、`typecheck-web`，保留 `test-all`。
- [ ] 更新环境说明：第三方 LLM Key 仅 API 持有；Agent 只持个人系统 API Key；Profile、截图和下载目录不得同步到服务器。
- [ ] 搜索生产代码，确认没有固定评分、演示候选人、真实密钥、验证码绕过、自动设置筛选器或敏感日志。
- [ ] Run:

```bash
python -m pytest -q tests/domain
python -m pytest -q tests/api
python -m pytest -q tests/agent
cd apps/web && npm run test
cd apps/web && npx vue-tsc --noEmit
cd apps/web && npm run build
make test-all
git diff --check
```

- [ ] 在临时复制的 legacy SQLite 数据库上执行两次迁移，核对候选人、简历、评分、联系记录数量及外键完整性。
- [ ] 若配置了 PostgreSQL 测试库，运行 DDL、回填、唯一约束、合并撤销事务测试；未运行前不得宣称生产 PostgreSQL 迁移已验证。
- [ ] 使用本地 fixture 完成端到端验收：1 人、50 人、页面不足、关键资料缺失、全局重复联系、发送确认失败、断点恢复、风控暂停。
- [ ] 真站只做人工验收：HR 登录并手动设置筛选条件，运行极小批次；验证码/风控出现后确认立即暂停。不得在 CI 访问 BOSS。
- [ ] 对照规格逐条核验成功标准；记录仍需人工确认的平台合规项。

## 完成定义

- 全部自动测试、TypeScript 类型检查、Web 构建和 `git diff --check` 通过。
- legacy SQLite 迁移可重复且历史记录不丢失。
- Agent 不修改筛选条件、不重复发送、未确认发送不记成功。
- 关键资料缺失进入人工复核，普通缺失有清晰估算标记。
- 候选人多岗位、简历版本、合并及无冲突撤销均有 API 和 UI 验证。
- PostgreSQL 只有在真实集成测试通过后才标记为已验证。
- 未经用户授权不创建提交、不推送、不合并分支。
