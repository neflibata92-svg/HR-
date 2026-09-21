# LEION HR 正式前端迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧单页管理台迁移为已确认的 LEION HR 五页正式前端，只显示真实 API 数据，缺失能力使用明确空状态。

**Architecture:** `App.vue` 仅处理登录、用户确认和首次改密门禁；`AppShell.vue` 管理五页导航，各页面独立请求数据。复用抽屉、状态标签和空状态组件；不增加状态库，不扩后端，不用演示数据冒充生产数据。

**Tech Stack:** Vue 3.5、TypeScript 5.7、Vite 6、Vitest 2、Vue Test Utils、原生 CSS

**Spec:** `docs/superpowers/specs/2026-09-20-leion-hr-clickable-prototype-design.md`

## Global Constraints

- 品牌统一为 `LEION HR`，视觉采用深靛蓝 `#090E80`、紫青渐变、玻璃面板和大圆角。
- 每位 HR 每自然日 200 次招呼额度由所有岗位共享；无统计接口时只说明规则，不虚构使用量。
- 岗位不得设置独立额度。
- 简历库必须先选择岗位；因当前无查询和岗位关联接口，选择后明确展示能力缺失。
- 普通用户无自助注册；账号由管理员创建。
- 管理员功能对 `member` 隐藏，且不得触发管理员接口。
- 大模型 Key 不进入前端；这里只管理各 Agent 的独立 API Key。
- 桌面显示侧栏，窄屏显示横向导航。
- 不实现后端尚不支持的统计、活动流、任务控制、简历查询或设置持久化。

## Review Focus

- access token 无效：清除两类 token 并回到登录页，不加载业务数据。
- 账号要求首次改密：只显示改密页，成功后重新确认用户再进入应用。
- 页面 API 失败：显示错误和重试，不伪装成正常空数据。
- 普通 HR：不显示或请求 HR 账号管理。
- 键盘与窄屏：导航、表单和抽屉具备明确标签及 dialog 语义。

---

## 文件结构

**修改：** `apps/web/src/App.vue`、`api.ts`、`styles.css`、`components/FirstPasswordChange.vue`、`components/HrAccountManagement.vue`、`__tests__/App.spec.ts`、`index.html`。

**创建：**

```text
apps/web/src/types.ts
apps/web/src/layouts/AppShell.vue
apps/web/src/pages/LoginPage.vue
apps/web/src/pages/DashboardPage.vue
apps/web/src/pages/JobsPage.vue
apps/web/src/pages/CandidatesPage.vue
apps/web/src/pages/ResumesPage.vue
apps/web/src/pages/SettingsPage.vue
apps/web/src/components/AppDrawer.vue
apps/web/src/components/EmptyState.vue
apps/web/src/components/StatusBadge.vue
apps/web/src/layouts/__tests__/AppShell.spec.ts
apps/web/src/pages/__tests__/{LoginPage,DashboardPage,JobsPage,CandidatesPage,ResumesPage,SettingsPage}.spec.ts
```

### Task 1: 登录与认证门禁

**Files:**
- Create: `apps/web/src/pages/LoginPage.vue`
- Modify: `apps/web/src/App.vue`
- Modify: `apps/web/src/components/FirstPasswordChange.vue`
- Modify: `apps/web/src/__tests__/App.spec.ts`
- Test: `apps/web/src/pages/__tests__/LoginPage.spec.ts`

**Interfaces:**
- Consumes: `login()`、`me()`、`setTokens()`、`clearTokens()`。
- Produces: `LoginPage` 事件 `authenticated(accessToken, refreshToken)`；`App.vue` 只向业务壳传入已确认的 `UserMe`。

- [ ] 写失败测试：提交时去除用户名两端空格、调用 `login()`、成功发出 token、重复提交被阻止、失败显示错误，并断言页面无“注册”。
- [ ] 运行 `cd apps/web && npm test -- --run src/pages/__tests__/LoginPage.spec.ts`，确认因组件不存在而 FAIL。
- [ ] 实现双栏 `LEION HR` 登录页；使用 `submitting` 锁和页面内错误，不保留 `register()` UI。
- [ ] 重构 `App.vue` 为未登录、首次改密、已登录三态；401 清 token，改密成功后重新调用 `me()`。
- [ ] 更新 `App.spec.ts`：覆盖无 token、401、首次改密、改密成功和角色加载。
- [ ] 运行 `npm test -- --run src/pages/__tests__/LoginPage.spec.ts src/__tests__/App.spec.ts src/components/__tests__/FirstPasswordChange.spec.ts`，预期 PASS。

### Task 2: 五页应用壳与共享组件

**Files:**
- Create: `apps/web/src/types.ts`
- Create: `apps/web/src/layouts/AppShell.vue`
- Create: `apps/web/src/components/AppDrawer.vue`
- Create: `apps/web/src/components/EmptyState.vue`
- Create: `apps/web/src/components/StatusBadge.vue`
- Test: `apps/web/src/layouts/__tests__/AppShell.spec.ts`
- Modify: `apps/web/src/App.vue`

**Interfaces:**
- Produces: `PageId = "dashboard" | "jobs" | "candidates" | "resumes" | "settings"`；`AppDrawer` props `open/title` 和事件 `close`；`AppShell` 事件 `logout`。

- [ ] 写失败测试：五个导航按钮分别只挂载对应 `data-testid` 页面；品牌、用户名持续显示；退出发出一次事件。
- [ ] 运行 `npm test -- --run src/layouts/__tests__/AppShell.spec.ts`，确认 FAIL。
- [ ] 实现顶栏、侧栏、移动导航和当前页切换，不引入路由依赖。
- [ ] 实现共享组件；抽屉使用 `role="dialog"`、`aria-modal="true"`、标题关联、关闭按钮和遮罩关闭。
- [ ] 测试抽屉关闭、状态文本和空状态说明，运行该测试文件并确认 PASS。

### Task 3: 工作台真实状态

**Files:**
- Create: `apps/web/src/pages/DashboardPage.vue`
- Test: `apps/web/src/pages/__tests__/DashboardPage.spec.ts`
- Modify: `apps/web/src/api.ts`

**Interfaces:**
- Consumes: `listAgentRuns()`。
- Produces: `AgentRun { id, machine_id, status, last_error, last_heartbeat }`。

- [ ] 写失败测试：真实机器状态出现；额度规则出现；统计、动态和控制显示“接口暂未提供”；不出现原型示例数字。
- [ ] 增加请求失败测试：显示错误与重试按钮，而非“暂无设备”。
- [ ] 运行测试，确认 FAIL。
- [ ] 补全 `AgentRun` 类型，实现设备状态、共享额度规则和三类明确空状态。
- [ ] 运行 `npm test -- --run src/pages/__tests__/DashboardPage.spec.ts`，预期 PASS。

### Task 4: 岗位管理真实流程

**Files:**
- Create: `apps/web/src/pages/JobsPage.vue`
- Test: `apps/web/src/pages/__tests__/JobsPage.spec.ts`
- Modify: `apps/web/src/api.ts`

**Interfaces:**
- Consumes: `listJobs()`、`createJob()`。
- Produces: 完整 `Job` 类型、`JobWrite`、`updateJob(id, payload): Promise<Job>`。

- [ ] 写失败测试：加载真实岗位、名称搜索、状态过滤、空列表、失败重试、点击卡片打开详情。
- [ ] 写表单测试：创建岗位提交 `name/jd_text/score_threshold/greet_template`；编辑和启停调用 `PATCH /api/jobs/{id}`；表单中无岗位额度字段。
- [ ] 运行测试，确认 FAIL。
- [ ] 在 `api.ts` 补齐 `boss_entry_url`、限速字段、`created_at` 和 `updateJob()`。
- [ ] 实现岗位卡片、新建抽屉、编辑抽屉和保存中锁；成功后用响应对象替换本地项，失败保留表单。
- [ ] 运行 `npm test -- --run src/pages/__tests__/JobsPage.spec.ts`，预期 PASS。

### Task 5: 候选人基础查询与交换标记

**Files:**
- Create: `apps/web/src/pages/CandidatesPage.vue`
- Test: `apps/web/src/pages/__tests__/CandidatesPage.spec.ts`
- Modify: `apps/web/src/api.ts`

**Interfaces:**
- Consumes: `listCandidates(q)`、`markExchange(candidateId, operator)`。
- Produces: 完整 `Candidate` 基础类型；只展示 API 已返回字段。

- [ ] 写失败测试：首次加载、姓名/BOSS ID 搜索、无结果、失败重试和点击候选人打开基础详情。
- [ ] 写交换测试：操作人使用当前用户名；成功显示反馈且不伪造沟通阶段；失败保持原状态。
- [ ] 运行测试，确认 FAIL。
- [ ] 补全 `job_segments_json/source/created_at` 类型，实现真实列表、基础详情抽屉和交换按钮。
- [ ] 对 AI 分数、匹配证据、风险和时间线显示“详情接口暂未提供”，不从 JSON 猜测。
- [ ] 运行 `npm test -- --run src/pages/__tests__/CandidatesPage.spec.ts`，预期 PASS。

### Task 6: 简历库上传与能力边界

**Files:**
- Create: `apps/web/src/pages/ResumesPage.vue`
- Test: `apps/web/src/pages/__tests__/ResumesPage.spec.ts`
- Modify: `apps/web/src/api.ts`

**Interfaces:**
- Consumes: `listJobs()`、`uploadResume(file, candidateId?)`。
- Produces: `Resume` 类型；岗位前置选择和真实上传结果反馈。

- [ ] 写失败测试：未选岗位时阻止进入结果区并提示先选择；岗位列表来自 API；切换岗位清除上次反馈。
- [ ] 写上传测试：无文件不请求；上传真实文件后显示响应中的解析状态；错误可重试。
- [ ] 写边界测试：选岗后明确说明后端尚不支持简历列表及岗位关联，不渲染示例简历。
- [ ] 运行测试，确认 FAIL。
- [ ] 将 `uploadResume()` 返回值改为 `Promise<Resume>`，可选传 `candidate_id`；实现岗位选择、上传和空状态。
- [ ] 运行 `npm test -- --run src/pages/__tests__/ResumesPage.spec.ts`，预期 PASS。

### Task 7: 系统设置、HR 与 Agent Key

**Files:**
- Create: `apps/web/src/pages/SettingsPage.vue`
- Test: `apps/web/src/pages/__tests__/SettingsPage.spec.ts`
- Modify: `apps/web/src/components/HrAccountManagement.vue`

**Interfaces:**
- Consumes: `UserMe`、`listApiKeys()`、`createApiKey(name)`、`revokeApiKey(id)`；管理员复用 `HrAccountManagement`。
- Produces: 当前账号卡、共享额度说明、真实 Agent Key 管理；管理员 HR 管理区。

- [ ] 写 member 测试：显示账号和 Key，绝不挂载 HR 管理，也不调用 `listUsers()`。
- [ ] 写 admin 测试：挂载 HR 管理；创建 Key 只显示一次明文；吊销成功更新状态；错误不清空列表。
- [ ] 运行测试，确认 FAIL。
- [ ] 实现设置页；Key 名称由用户输入且必填；明确提示“大模型 Key 仅在服务端配置”。
- [ ] 保留 HR 新建、停用、启用、重置密码的现有真实流程，统一为新卡片和弹层样式。
- [ ] 运行 `npm test -- --run src/pages/__tests__/SettingsPage.spec.ts src/components/__tests__/HrAccountManagement.spec.ts`，预期 PASS。

### Task 8: 统一视觉、响应式与最终验收

**Files:**
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/index.html`
- Modify: 所有新增页面与布局（仅补语义 class/aria，不改业务行为）

**Interfaces:**
- Consumes: 前七项稳定 DOM 与状态。
- Produces: 与原型一致的正式视觉和桌面/窄屏布局。

- [ ] 在 `styles.css` 建立颜色、间距、圆角、阴影、字体、动效变量；实现顶栏、208px 侧栏、页面卡片、胶囊按钮、抽屉和模态框。
- [ ] 添加 `prefers-reduced-motion`，在窄屏将侧栏变为横向滚动导航，表格/卡片不造成页面横向溢出。
- [ ] 将 `index.html` 标题改为 `LEION HR · 招聘工作台`；字体使用系统回退，避免网络字体失败导致不可用。
- [ ] 逐页核对 loading、error、empty、disabled、focus-visible 和 dialog 标签。
- [ ] 运行 `cd apps/web && npm test -- --run`，预期全部 PASS。
- [ ] 运行 `cd apps/web && npm run build`，预期 TypeScript 与 Vite 构建成功。
- [ ] 运行 `cd /Users/yueguanshengren/Desktop/Resume_Screening && .venv/bin/python -m pytest -q`，预期后端回归全部 PASS。
- [ ] 在 `1280px` 与 `390px` 视口人工核对登录、改密、五页切换、抽屉、管理员权限和空状态。

## 自检结果

- 规格覆盖：五页、品牌、共享额度规则、岗位无独立额度、简历先选岗位、详情抽屉和响应式均有对应任务。
- 真实数据约束：所有缺失接口均由测试固定为空状态，没有演示数据入口。
- 类型一致：页面只依赖 `api.ts` 导出的 `UserMe/Job/Candidate/Resume/AgentRun/ApiKeyRow`。
- 范围控制：不引入 Router、Pinia、图标库，不修改后端，不实现伪任务控制。
- 工作区保护：当前 `apps/web` 无未提交改动；现有未跟踪项仅为 `.DS_Store` 与 `.superpowers` 运行状态文件，不纳入提交。
