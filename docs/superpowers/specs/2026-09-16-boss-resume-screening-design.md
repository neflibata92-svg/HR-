# BOSS 直聘本机全自动筛选 + 共享简历库 — 设计规格

- 日期：2026-09-16
- 状态：已批准；部署与鉴权以改版规格为准
- 改版规格（优先）：[2026-09-16-cloud-auth-design.md](./2026-09-16-cloud-auth-design.md)
- 相关调研：
  - [docs/research/2026-09-16-boss-zhipin-integration.md](../../research/2026-09-16-boss-zhipin-integration.md)
  - [docs/research/2026-09-16-local-agent-llm-scoring.md](../../research/2026-09-16-local-agent-llm-scoring.md)
  - [docs/research/2026-09-16-cloud-auth-architecture.md](../../research/2026-09-16-cloud-auth-architecture.md)

## 1. 目标

为招聘小团队提供本机自动化助手：在 BOSS 直聘招聘端按岗位 JD 筛选候选人，硬性条件过滤后由大模型打分，达到阈值则自动打招呼索取附件简历，并将附件与存量简历写入**云端共享简历库**；全员共享「近 30 天交换/转发」冷却，避免重复交换。

### 1.1 成功标准（MVP）

- 本机 Agent 能在已登录的 BOSS 会话中跑完「列表 → 硬筛 → 打分 →（可选）打招呼 → 收附件 → 入库」主路径。
- 硬筛四条全部生效，且交换冷却以共享库为准、团队可见。
- 管理台可配置 JD、分数阈值、招呼话术；可批量上传与监视文件夹入库。
- 关键步骤有审计日志与失败可观测（截图/状态），风控页能停机。

### 1.2 非目标（MVP 不做）

- 官方 BOSS Open API 对接（若后续有商务授权可替换 Agent 采集层）。
- 多账号并行、云端无头集群、自动电话/短信。
- 完整 ATS / 飞书深度对接。
- 对抗平台检测或绕过验证码。

## 2. 约束与假设

- 交互模式：**尽量全自动**；运行位置：**招聘同学本机常驻**；登录态为操作者本人 BOSS 账号。
- 共享简历库部署在 **云服务器（Docker Compose）**；详见改版规格。
- 细打分：**大模型**输出 0–100 分 + 简短理由；达可配置阈值（默认 80）则自动打招呼。
- 自动化可能违反平台用户协议并有封号风险；产品行为必须限速、可熔断、可人工接管。
- 首次联网检索未发现可用的公开招聘端候选人 API；采集层以浏览器自动化实现（见调研文档）。

## 3. 架构

系统分为本机 Agent 与内网服务两块：

```
[本机 Agent]                      [内网 NAS/小主机]
 Playwright (headed,             api + db + files
  persistent profile)              ├─ JD / 阈值 / 话术
  → 硬筛 / 调 LLM / 打招呼         ├─ Resume / Candidate
  → 下附件 → 上报 API              ├─ ExchangeEvent (30d)
                                   ├─ Score / Outreach 审计
                                   ├─ ingestor (上传 + 文件夹监视)
                                   └─ web 管理台
         │                              │
         └──── HTTPS/Token ─────────────┘
         LLM API（用户自备）
```

边界：

- Agent **不作为简历主存储**；简历、交换、JD 以内存服务为准。
- 同事通过 Web 管理台共享同一冷却与简历库。

推荐技术选型（可在实现计划中微调，但边界不变）：

| 层 | 建议 |
|----|------|
| Agent | Python 3.11+ / Playwright，持久化 browser profile |
| API | Python FastAPI |
| DB | SQLite（MVP）→ 可迁 PostgreSQL |
| 文件 | NAS 目录（原件）+ DB 元数据/解析文本 |
| Web | Vue 3 简易管理台（内网） |
| LLM | 可配置 OpenAI 兼容 API（强制 JSON schema） |

依据调研：长期登录用 persistent context；API 与浏览器任务逻辑分离；硬约束在模型打分之前执行。

## 4. 核心流程

### 4.1 岗位任务主循环

1. Agent 从 API 拉取启用中的 `JobPosting`（JD、阈值、话术、BOSS 入口配置、限速）。
2. 打开对应推荐/搜索列表，逐个读取候选人可见字段。
3. **硬筛**（本地，不调用 LLM），失败则写 `ScoreEvent.hardFilter=fail` 并跳过。
4. 通过后调用 LLM，校验 JSON：`{ score, reason, evidence[] }`。
5. `score >= threshold` → 发送招呼话术（索取附件）；写 `OutreachEvent`。
6. 等待/轮询附件；下载成功后上传 API（`source=boss_attachment`），关联 Candidate/Resume。
7. 未达阈值：仅保留打分记录，不打招呼。
8. 同一 `jobId + candidateKey` 已打过招呼则跳过（幂等）。

### 4.2 硬性筛选（固定规则）

| 规则 | 判定 |
|------|------|
| 年龄 | ≤ 38 |
| 工作年限 | ∈ [3, 5] 年 |
| 平均每份工作 | 总工作年限 ÷ 完整工作段数 > 1；段数无法解析 → 标不确定并 **跳过**（不打招呼） |
| 交换冷却 | 共享库中该候选人近 **30 天** 无 `ExchangeEvent` |

说明：年龄/年限优先取 BOSS 卡片或详情中的结构化字段；工作段来自在线简历经历列表。字段缺失按「不确定 → 跳过」处理，避免误招呼。

### 4.3 候选人标识

1. 优先 BOSS 稳定 ID（页面可得时）。
2. 否则弱指纹：`hash(规范化姓名 + 最近公司或学校)`。
3. 管理台支持人工合并重复 Candidate。

### 4.4 「交换过简历」

以下任一写入 `ExchangeEvent` 即触发冷却：

- 同事在管理台标记「已交换 / 已转发」。
- 后续若接入可观测的分享动作，同样入库（MVP 以人工标记为主）。

## 5. 组件职责

| 组件 | 职责 |
|------|------|
| `agent` | Playwright 驱动、硬筛、LLM 调用编排、打招呼、附件下载、审计上报、限速与熔断 |
| `api` | REST：JD、候选人/简历、交换事件、打分/招呼日志、Agent 运行心跳、鉴权 |
| `ingestor` | 批量上传解析；监视共享文件夹自动入库 |
| `web` | 简历检索、JD/阈值/话术配置、交换标记、任务状态与审计查看 |
| `llm-adapter` | 统一模型调用、JSON schema 校验、有限重试 |

### 5.1 存量简历入库

- **批量上传**：PDF / Word / 图片。PDF/Word 提取文本；图片 MVP 只存原件（`parse_status=skipped_image`），OCR 不在 MVP。
- 任意格式解析失败仍保留原件并标记 `parse_status=failed`。
- **文件夹监视**：配置共享目录，新文件写入稳定（短时 size 不变）后再入库，避免读到半截文件。

## 6. 数据模型

- **JobPosting**：名称、JD 原文、`score_threshold`（默认 80）、招呼话术、BOSS 入口配置、限速参数、启用标志。
- **Candidate**：`id`、`boss_id` 可空、`fingerprint`、年龄、年限、工作段摘要 JSON、来源。
- **Resume**：`candidate_id`、文件路径、解析文本、`source` ∈ {`boss_attachment`,`upload`,`folder_watch`}、入库时间、`parse_status`。
- **ScoreEvent**：`candidate_id`、`job_id`、硬筛结果、score、reason、model、时间。
- **OutreachEvent**：`candidate_id`、`job_id`、已打招呼、已收附件、时间。
- **ExchangeEvent**：`candidate_id`、操作人、类型、时间。
- **AgentRun**：机器标识、状态、最后心跳、最近错误。

文件原件只存 NAS；数据库存元数据与解析文本。

鉴权：内网账号或 Token；Agent 使用服务 Token。

## 7. 异常处理与风控

- 选择器/DOM 失败：截图，任务暂停，Web 标红；禁止盲目连点。
- LLM 失败：最多重试 2 次；仍失败则跳过该人并记 `score_error`。
- 附件超时（默认 24h，可配）：留在「已招呼待附件」；支持人工补传。
- API 不可达：停止新的打招呼；恢复后同步。
- 验证码/风控页：立即停机并通知操作者。
- 限速：操作随机间隔 + 每小时招呼上限（Job 级可配）。
- 不绕过验证码、不进行未授权访问。

## 8. 测试策略

- 硬筛单测：年龄、年限、平均在职、冷却 29/30/31 天边界。
- `llm-adapter`：合法/非法 JSON、重试与降级。
- API：入库去重、交换过滤、幂等招呼。
- Agent：本地 HTML fixture 测主流程（CI 不依赖真站）。
- 真站：人工验收清单（登录、列表、招呼、附件、入库）。
- 文件夹监视：PDF/Word 入库与解析失败保留原件。

提交前遵循仓库约定：有 `make test` 时必须通过。

## 9. MVP 范围切片

1. 内网 API + SQLite + 文件存储 + 最小 Web（JD、上传、交换标记、列表）。
2. 硬筛与交换冷却查询。
3. LLM adapter + 分数阈值决策。
4. 本机 Agent：登录 Profile、列表读取、硬筛、打分、打招呼、附件上传。
5. 文件夹监视入库。
6. 审计、限速、风控停机。

## 10. 风险

| 风险 | 缓解 |
|------|------|
| 平台协议与封号 | 限速、熔断、人工接管；产品说明风险 |
| DOM 变更 | 选择器集中配置；fixture + 人工验收 |
| LLM 幻觉/不稳定 | 硬筛前置；JSON schema；低置信可后续加人工队列（非 MVP） |
| 弱指纹误合并 | 人工合并工具；优先 boss_id |
| 内网单点 | MVP 接受；备份 DB 与文件目录 |

## 11. 已确认产品决策摘要

- 尽量全自动；本机常驻；本人 BOSS 登录态。
- 小团队共享库 + 30 天交换冷却。
- 库部署：内网服务/NAS。
- 打分：硬筛 + LLM 细打分；≥ 固定阈值自动打招呼。
- 存量：批量上传 + 文件夹扫描。
- 架构选型：本机 Playwright Agent + 内网简历服务（方案 1）。
