# 岗位任务控制、候选人边界与简历归档 Implementation Plan

> **执行要求：** 使用 `executing-plans` 按批次实施；每项先写失败测试，再做最小实现。未经用户明确要求，不提交或推送 Git。

**Goal:** 将系统改为岗位视角的真实任务控制，区分筛选记录与正式候选人，并支持 Agent 附件收取及 HR 按岗位批量归档 PDF。

**Architecture:** FastAPI 和数据库是任务、候选人与简历归档的唯一事实来源；常驻 Agent 只处理明确分配给本机的岗位任务，并独立监视当前 HR 的待收简历；Vue 工作台按岗位聚合真实状态，岗位详情维护默认配置，简历库负责按岗位查看与批量导入。

**Spec:** `docs/superpowers/specs/2026-09-23-job-task-resume-archive-design.md`

## 全局约束

- 当前开发在独立 worktree 中进行，不影响主工作区。
- API、Agent 与 Web 分阶段兼容升级；迁移必须幂等，历史数据不得删除。
- 不绕过 BOSS 验证码、风控或登录限制。
- 只有页面明确验证发送成功后才能创建正式候选人。
- 暂停和终止必须在发送前由服务端再次阻断新联系。
- 手工 PDF 不解析、不评分、不创建候选人、不触发联系。
- 不提交或推送 Git，除非用户另行明确要求。

---

### Task 1: 可持续迁移与核心数据模型

**Files**
- Modify: `apps/api/src/resume_api/models.py`
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/migrations/runner.py`
- Modify: `tests/api/test_migrations.py`
- Create: `tests/api/test_job_task_archive_models.py`

- [ ] 写失败测试：新增筛选记录、简历岗位归档、岗位默认配置、任务控制字段和 Agent 状态字段；迁移重复执行不丢数据。
- [ ] 写失败测试：`Resume.candidate_id` 可空；`(resume_id, job_id)` 唯一；同岗位文件哈希去重；活动任务具备并发防重条件。
- [ ] Run: `python -m pytest tests/api/test_migrations.py tests/api/test_job_task_archive_models.py -v`，确认先失败。
- [ ] 增加 `ScreeningRecord`、`ResumeJobArchive`，扩展 `JobPosting`、`Resume`、`ScreeningTask`、`AgentRun`；保留旧 `ScreeningTaskItem` 兼容读取。
- [ ] 实施逐步骤、幂等迁移；SQLite 与 PostgreSQL 使用兼容的索引和约束策略。
- [ ] 重跑测试，预期通过。

---

### Task 2: 筛选记录与正式候选人提升

**Files**
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/services/screening_tasks.py`
- Modify: `apps/api/src/resume_api/services/candidates.py`
- Modify: `apps/api/src/resume_api/services/outreach.py`
- Modify: `apps/api/src/resume_api/routers/screening_tasks.py`
- Modify: `apps/api/src/resume_api/routers/candidates.py`
- Modify: `tests/api/test_screening_task_items.py`
- Create: `tests/api/test_screening_records.py`
- Create: `tests/api/test_candidate_promotion.py`

- [ ] 写失败测试：浏览、低分、跳过、待复核、发送失败和结果未知均只建立筛选记录，不创建 Candidate。
- [ ] 写失败测试：确认联系成功后幂等创建/复用 Candidate、CandidateJob，并设为 `waiting_resume`；重试不得重复。
- [ ] 写失败测试：候选人列表默认只返回有成功联系证据的人。
- [ ] Run: `python -m pytest tests/api/test_screening_records.py tests/api/test_candidate_promotion.py tests/api/test_screening_task_items.py -v`。
- [ ] 将任务项输入从 `candidate_id` 改为 BOSS 身份和页面摘要，评分快照归入筛选记录；保留旧任务兼容查询。
- [ ] 联系确认事务中完成候选人提升和反向关联。
- [ ] 重跑测试，预期通过。

---

### Task 3: 历史候选人兼容迁移

**Files**
- Modify: `apps/api/src/resume_api/migrations/runner.py`
- Modify: `apps/api/src/resume_api/services/candidates.py`
- Modify: `tests/api/test_migrations.py`
- Create: `tests/api/test_candidate_history_migration.py`

- [ ] 用旧库写失败测试：明确成功联系者保留；无成功证据者生成历史筛选记录；无法判断者标记人工核对；所有旧外键仍可追溯。
- [ ] 写失败测试：迁移执行两次结果相同；候选人 API 服务端过滤未确认历史行。
- [ ] Run: `python -m pytest tests/api/test_candidate_history_migration.py tests/api/test_migrations.py -v`。
- [ ] 实施兼容回填，不物理删除历史 Candidate；记录迁移来源和人工核对状态。
- [ ] 重跑测试，预期通过。

---

### Task 4: 简历直接岗位归档与批量导入 API

**Files**
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/services/ingest.py`
- Modify: `apps/api/src/resume_api/routers/resumes.py`
- Modify: `tests/api/test_resume_upload.py`
- Modify: `tests/api/test_resume_versions.py`
- Create: `tests/api/test_resume_job_archives.py`
- Create: `tests/api/test_resume_batch_import.py`

- [ ] 写失败测试：指定岗位批量上传多个 PDF，逐文件返回 `imported|duplicate|failed`。
- [ ] 写失败测试：手工 PDF 不解析、不创建候选人，保留原文件名；非 PDF、超限和空文件被拒绝。
- [ ] 写失败测试：同岗位同哈希跳过，跨岗位允许归档；按岗位查询使用直接归档关系。
- [ ] Run: `python -m pytest tests/api/test_resume_job_archives.py tests/api/test_resume_batch_import.py tests/api/test_resume_upload.py tests/api/test_resume_versions.py -v`。
- [ ] 增加归档服务和批量端点；每文件独立事务与结果；保留旧单候选人上传端点。
- [ ] 重跑测试，预期通过。

---

### Task 5: Agent 附件上传、待收名单与多岗位确认

**Files**
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/routers/resumes.py`
- Modify: `apps/api/src/resume_api/routers/candidates.py`
- Modify: `apps/api/src/resume_api/services/ingest.py`
- Create: `apps/api/src/resume_api/services/resume_inbox.py`
- Create: `tests/api/test_resume_inbox.py`
- Create: `tests/api/test_resume_job_assignment.py`

- [ ] 写失败测试：当前 HR 可查询跨任务全部 `waiting_resume` 人员，其他 HR 不可见。
- [ ] 写失败测试：单一等待岗位自动归档并更新为 `resume_received`；多个等待岗位进入 `pending_job_assignment`。
- [ ] 写失败测试：HR 选择一个岗位后完成归档；重传响应丢失时按哈希和联系事件幂等。
- [ ] Run: `python -m pytest tests/api/test_resume_inbox.py tests/api/test_resume_job_assignment.py -v`。
- [ ] 实现待收名单、Agent 附件上传和待确认分岗 API。
- [ ] 重跑测试，预期通过。

---

### Task 6: 岗位默认配置与启动校验

**Files**
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/services/jobs.py`
- Modify: `apps/api/src/resume_api/routers/jobs.py`
- Modify: `tests/api/test_jobs.py`
- Create: `tests/api/test_job_readiness.py`

- [ ] 写失败测试：保存默认筛选人数、关键资料确认、阈值、模板、BOSS 地址和限速；返回配置缺失项。
- [ ] 写失败测试：停用或配置不完整岗位禁止启动；任务保存完整配置快照。
- [ ] Run: `python -m pytest tests/api/test_jobs.py tests/api/test_job_readiness.py -v`。
- [ ] 扩展岗位读写和 readiness 聚合；创建任务不再要求 Web 临时提交关键资料。
- [ ] 重跑测试，预期通过。

---

### Task 7: 每岗位唯一任务、指定 Agent 与安全状态机

**Files**
- Modify: `apps/api/src/resume_api/schemas.py`
- Modify: `apps/api/src/resume_api/models.py`
- Modify: `apps/api/src/resume_api/services/screening_tasks.py`
- Modify: `apps/api/src/resume_api/services/outreach.py`
- Modify: `apps/api/src/resume_api/routers/screening_tasks.py`
- Modify: `tests/api/test_screening_tasks.py`
- Modify: `tests/api/test_screening_task_state_machine.py`
- Modify: `tests/api/test_global_outreach_dedup.py`
- Create: `tests/api/test_job_task_assignment.py`

- [ ] 写失败测试：同岗位只能存在一个 `ready|running|pausing|paused|cancelling` 任务；终态后可重启。
- [ ] 写失败测试：只能选择当前 HR 在线空闲 Agent，且只有被指定机器可领取。
- [ ] 写失败测试：暂停为 `running→pausing→paused`，终止为活动态→`cancelling→cancelled`；继续只允许 paused。
- [ ] 写失败测试：暂停/终止请求后，服务端拒绝新的评分、联系预留和下一筛选记录。
- [ ] Run: `python -m pytest tests/api/test_screening_tasks.py tests/api/test_screening_task_state_machine.py tests/api/test_job_task_assignment.py tests/api/test_global_outreach_dedup.py -v`。
- [ ] 实施事务锁、指定 Agent、控制请求与 Agent 收口确认端点。
- [ ] 重跑测试，预期通过。

---

### Task 8: Agent 心跳、常驻领取与安全控制

**Files**
- Modify: `apps/agent/src/resume_agent/api_client.py`
- Modify: `apps/agent/src/resume_agent/config.py`
- Modify: `apps/agent/src/resume_agent/runner.py`
- Modify: `apps/agent/src/resume_agent/live_runner.py`
- Modify: `apps/agent/src/resume_agent/cli.py`
- Modify: `tests/agent/test_task_api_client.py`
- Modify: `tests/agent/test_task_runner.py`
- Modify: `tests/agent/test_live_runner.py`
- Create: `tests/agent/test_resident_agent.py`

- [ ] 写失败测试：常驻循环上报在线、空闲、任务和岗位；只领取分配给自己的任务；重启恢复未终态任务。
- [ ] 写失败测试：按岗位 `boss_entry_url` 导航并校验；失效、掉线、岗位不符、验证码或风控触发安全暂停。
- [ ] 写失败测试：开始候选人、评分、联系预留、真实发送和翻页前均检查控制状态；安全收口后确认暂停/终止。
- [ ] Run: `python -m pytest tests/agent/test_task_api_client.py tests/agent/test_task_runner.py tests/agent/test_live_runner.py tests/agent/test_resident_agent.py -v`。
- [ ] 将 Agent 改为常驻任务循环，移除任意领取和默认 `jobs[0]` 路径。
- [ ] 重跑测试，预期通过。

---

### Task 9: Agent 跨任务附件监视

**Files**
- Modify: `apps/agent/src/resume_agent/api_client.py`
- Modify: `apps/agent/src/resume_agent/boss_live.py`
- Modify: `apps/agent/src/resume_agent/live_runner.py`
- Create: `apps/agent/src/resume_agent/resume_monitor.py`
- Modify: `tests/agent/test_boss_live.py`
- Create: `tests/agent/test_resume_monitor.py`

- [ ] 写失败测试：筛选任务运行、暂停、完成和终止时均继续轮询当前 HR 待收名单。
- [ ] 写失败测试：收到 PDF 后安全下载、计算哈希、上传并删除临时副本；失败保留等待状态并可重试。
- [ ] 写失败测试：多个岗位冲突不自动复制，由 API 标记待确认。
- [ ] Run: `python -m pytest tests/agent/test_resume_monitor.py tests/agent/test_boss_live.py -v`。
- [ ] 接入现有附件定位与下载方法，形成独立后台监视职责。
- [ ] 重跑测试，预期通过。

---

### Task 10: Web 岗位工作台与岗位详情

**Files**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/pages/DashboardPage.vue`
- Modify: `apps/web/src/pages/JobsPage.vue`
- Modify: `apps/web/src/pages/__tests__/DashboardPage.spec.ts`
- Modify: `apps/web/src/pages/__tests__/JobsPage.spec.ts`

- [ ] 写失败测试：工作台首屏按岗位展示卡片；每张卡只使用真实 `Job`、`ScreeningTask`、`AgentRun`、候选人与简历接口数据，显示配置完整度、活动任务状态、`processed_count / requested_count`、执行 Agent、候选人数和归档简历数。
- [ ] 写失败测试：岗位没有任务或统计为 0 时显示正常空值；任一聚合请求失败时保留已成功数据、显示明确错误和重试入口，不回退到静态数字或演示活动。
- [ ] 写失败测试：只有 `enabled && readiness.ready` 且没有活动任务的岗位允许打开启动表单；表单只列出当前在线、心跳新鲜、BOSS 已登录且 `availability === "idle"` 的 Agent，并使用岗位 `default_requested_count` 和已确认关键资料。
- [ ] 写失败测试：运行中任务只显示“暂停/终止”，暂停中和终止中锁定重复操作，暂停后只显示“继续/终止”；控制请求期间按钮禁用，服务端响应后才更新；轮询和整页刷新均恢复全部活动任务。
- [ ] 写失败测试：岗位卡可进入对应岗位详情；配置不完整或停用时禁止启动，并列出 `readiness.missing` 对应的可理解提示和“完善岗位配置”入口。
- [ ] 写失败测试：岗位详情可新建、编辑、启停并保存岗位名称、JD、评分阈值、招呼模板、BOSS 地址、限速、默认筛选人数和已人工确认的关键资料；展示该岗位当前活动任务和历史任务，不把 AI 建议自动当成确认结果。
- [ ] Run: `cd apps/web && npm test -- DashboardPage.spec.ts JobsPage.spec.ts`，确认新增断言先失败且失败原因对应缺失交互。
- [ ] 在 `api.ts` 复用并收紧岗位、任务、Agent、候选人和简历类型；由页面基于真实列表按 `job_id` 聚合，避免新增第二套状态来源。
- [ ] 实现工作台岗位卡、启动/控制状态机、5 秒轮询和卸载清理；轮询请求防止旧响应覆盖新选择或新状态。
- [ ] 实现岗位详情完整配置、readiness 提示、按岗位任务历史和真实候选人/简历统计；保存或启停失败时保留当前页面和未保存输入，防止重复提交。
- [ ] 重跑目标测试，再运行 `cd apps/web && npm run typecheck`，预期全部通过。

---

### Task 11: Web 简历库、候选人库与生产占位清理

**Files**
- Modify: `apps/web/src/api.ts`
- Modify: `apps/web/src/layouts/AppShell.vue`
- Modify: `apps/web/src/pages/DashboardPage.vue`
- Modify: `apps/web/src/pages/JobsPage.vue`
- Modify: `apps/web/src/pages/ResumesPage.vue`
- Modify: `apps/web/src/pages/CandidatesPage.vue`
- Modify: `apps/web/src/pages/SettingsPage.vue`
- Modify: `apps/web/src/pages/__tests__/DashboardPage.spec.ts`
- Modify: `apps/web/src/pages/__tests__/JobsPage.spec.ts`
- Modify: `apps/web/src/pages/__tests__/ResumesPage.spec.ts`
- Modify: `apps/web/src/pages/__tests__/CandidatesPage.spec.ts`
- Modify: `apps/web/src/pages/__tests__/SettingsPage.spec.ts`

- [ ] 写失败测试：简历库加载真实岗位和简历归档，支持“全部岗位/指定岗位”切换；每行显示原文件名、`manual_upload|boss_attachment` 的中文来源、导入时间、候选人（可空）、解析状态和分岗状态。
- [ ] 写失败测试：选择启用岗位后可一次上传多个 PDF；提交期间防止重复导入，完成后逐文件保留并展示 `imported|duplicate|failed`，局部失败不抹掉成功结果，随后只刷新受影响的岗位列表。
- [ ] 写失败测试：文件选择阶段拒绝非 PDF；服务端返回的空文件、超限和批次数量错误显示原始文件名与可行动原因，不把整批统一显示为成功或失败。
- [ ] 写失败测试：`pending_job_assignment` 简历显示候选人的待选岗位；HR 选定一个岗位后调用 `assignResumeJob(resumeId, jobId)`，成功后更新为已归档，失败时保留待确认项和当前选择并允许重试。
- [ ] 写失败测试：手工导入简历显示原文件名和“无候选人”，不会出现在候选人库；同岗位重复文件显示“已跳过重复”，跨岗位导入仍可成功。
- [ ] 写失败测试：候选人库只展示服务端认定的联系成功者；按候选人的 `CandidateJob.status` 展示“等待简历 / 已收到简历 / 待确认分岗”，同一候选人多个岗位分别展示，不用本地猜测联系是否成功。
- [ ] 写失败测试：简历库和候选人库的首次加载失败、空列表、筛选无结果、操作失败分别显示错误、正常空状态、清空筛选或重试入口；已加载数据在局部操作失败时继续可见。
- [ ] 写失败测试：`AppShell`、工作台、岗位管理、简历库、候选人库和设置页不再常驻显示“暂未接入”“不会伪造”“模拟”“占位”等开发说明；没有后端数据来源的卡片或区块应删除或替换为真实状态/下一步操作，不能保留破折号统计冒充功能。
- [ ] Run: `cd apps/web && npm test -- ResumesPage.spec.ts CandidatesPage.spec.ts DashboardPage.spec.ts JobsPage.spec.ts SettingsPage.spec.ts`，确认新增断言先失败。
- [ ] 在 `api.ts` 对齐现有 `listResumes({ jobId })`、`batchImportResumes(jobId, files)`、`assignResumeJob(resumeId, jobId)`、`listCandidates` 和 `listCandidateJobs` 契约；保留服务端逐文件结果和状态，不在 Web 重新推断。
- [ ] 实现简历库岗位筛选、批量导入结果、待确认分岗、并发锁和可重试错误；实现候选人多岗位状态展示，选择变化或异步响应过期时不得串数据。
- [ ] 删除所有生产页面常驻开发占位文案：可由真实接口支持的改接真实数据；本轮无数据来源且不影响主流程的装饰区块直接移除；空数据统一给出正常说明和下一步操作。
- [ ] 重跑目标测试，再运行 `cd apps/web && npm run typecheck && npm run build`，预期全部通过。

---

### Task 12: 模拟全链路回归、权限边界与交付收口

**Files**
- Modify: `tests/api/test_task_permissions.py`
- Modify: `tests/api/test_resume_inbox.py`
- Modify: `tests/api/test_resume_job_assignment.py`
- Modify: `tests/api/test_resume_batch_import.py`
- Modify: `tests/agent/test_resident_agent.py`
- Modify: `tests/agent/test_resume_monitor.py`
- Modify: `README.md`

- [ ] 写或补失败测试：普通 HR 只能控制自己创建且分配给自己 Agent 的任务，只能读取自己的待收简历名单并处理其附件；其他 HR 的任务、联系事件和待确认分岗不可越权读取或修改，admin 保留既有管理能力。
- [ ] 写或补失败测试：用确定性测试替身跑通“岗位完整配置 → 指定在线 Agent 启动 → 筛选记录 → 发送确认后提升候选人 → `waiting_resume` → Agent 上传 PDF → 单岗位自动归档 / 多岗位人工确认”。
- [ ] 写或补失败测试：手工批量导入保持“不解析、不评分、不创建候选人、不触发联系”；同岗位哈希重复跳过、跨岗位允许归档；逐文件局部失败不回滚其他成功文件。
- [ ] 写或补失败测试：暂停/终止请求后服务端禁止新筛选和联系预留，Agent 安全收口后确认终态；任务终态不停止附件监视，重启后恢复未终态任务和待收监视。
- [ ] Run: `python -m pytest tests/api/test_task_permissions.py tests/api/test_resume_inbox.py tests/api/test_resume_job_assignment.py tests/api/test_resume_batch_import.py tests/agent/test_resident_agent.py tests/agent/test_resume_monitor.py -v`，确认新增断言先失败。
- [ ] 仅修复回归发现的契约、权限或幂等缺口，不在收口任务中新增规格外功能。
- [ ] 更新 `README.md`：说明岗位配置与启动、指定 Agent、暂停/继续/终止、候选人形成边界、Agent 后台收件、简历批量归档与多岗位确认；明确模拟测试不访问 BOSS 真站、不需要真实 LLM 密钥。
- [ ] 重跑目标集成测试，预期通过。

---

## 最终验证

- [ ] Run: `python -m pytest -q`，记录通过数量；任何失败均不得以“与本轮无关”直接忽略，需确认根因和影响。
- [ ] Run: `cd apps/web && npm test -- --run`，确认工作台、岗位管理、简历库和候选人库四个页面目标交互均有测试且全部通过。
- [ ] Run: `cd apps/web && npm run typecheck && npm run build`。
- [ ] Run: `git diff --check`；检查仓库中没有测试密钥、生产模拟数据、PDF 临时文件、BOSS Profile、截图或下载目录。
- [ ] 在新 SQLite 和旧 SQLite 副本上各连续执行两次迁移，核对候选人、筛选记录、任务、简历、岗位归档、联系记录和审计数量以及外键完整性。
- [ ] PostgreSQL 只有在真实测试库完成 DDL、回填、唯一约束、并发活动任务和事务回滚验证后才标记通过；若环境未提供，明确记录为“待 PostgreSQL 环境验证”，不得用 SQLite 结果代替。
- [ ] 按规格 14.2 逐项人工验收；涉及 BOSS 真站时必须由 HR 人工值守、小批量执行，不绕过验证码、风控、登录限制或平台规则。
- [ ] 最终报告分别列出：自动测试证据、四页面验收结果、迁移验证范围、尚未进行的真站/真实 LLM 联调和剩余风险，不把未验证事项描述为已完成。
