# LEION HR 原版设计还原实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以原始 HTML 为唯一视觉基准，将 LEION HR 原版界面完整迁回 Vue 前端，同时保留现有真实业务能力。

**Architecture:** 继续由 `App.vue` 管认证、`AppShell.vue` 管五页切换，各页面调用现有 `api.ts`。先恢复共享视觉与外壳，再逐页恢复原版模块；无接口内容保留版式并显示 `—` 或“暂未接入”。

**Tech Stack:** Vue 3.5、TypeScript 5.7、Vite 6、Vitest 2、Vue Test Utils、原生 CSS

**Spec:** `docs/superpowers/specs/2026-09-21-leion-hr-original-design-restoration.md`

## Global Constraints

- 唯一视觉基准：`/Users/yueguanshengren/Desktop/Resume_Screening/.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`。
- 主色 `#090E80`，辅色 `#7C65EB`、`#83E4EC`；字体必须有本地回退。
- 桌面端 208px 侧栏；窄屏横向导航且页面不得横向溢出。
- 动效遵守 `prefers-reduced-motion`，所有交互保留键盘焦点和无障碍名称。
- 保留真实 API、401 清理、失败重试、重复提交锁和权限隔离。
- 禁止展示原型数字 `326`、`148`、`126`、`37` 及示例人物、岗位、设备。
- 不新增后端接口、路由、状态库或大型 UI 库。
- 不自动提交或合并分支。

## Review Focus

- 请求失败必须显示错误与重试，不能伪装成空数据。
- 缺接口的统计、筛选和操作必须保留位置并禁用，不能产生假成功。
- API 返回空数组时原版模块仍存在，页面结构不得塌陷。
- 普通 HR 不渲染管理组件，也不调用管理员接口。
- 390px 宽度下导航、抽屉、表单、表格可用且 body 不横向溢出。

---

### Task 1: 共享视觉、登录与应用外壳

**Files:**
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/src/App.vue`
- Modify: `apps/web/src/layouts/AppShell.vue`
- Modify: `apps/web/src/pages/LoginPage.vue`
- Modify: `apps/web/src/components/{FirstPasswordChange,AppDrawer,EmptyState,StatusBadge}.vue`
- Test: `apps/web/src/{__tests__/App.spec.ts,layouts/__tests__/AppShell.spec.ts,pages/__tests__/LoginPage.spec.ts,components/__tests__/FirstPasswordChange.spec.ts}`

**Interfaces:** 保持现有认证事件；`EmptyState` 增加可选 `kind: "empty" | "unavailable" | "error"`；其他组件公开接口不变。

- [ ] **Step 1: 写失败测试**

```ts
expect(wrapper.text()).toContain("FIND.");
expect(wrapper.text()).toContain("SECURE WORKSPACE");
expect(wrapper.text()).not.toContain("输入任意账号即可进入");
await wrapper.get('[aria-label="显示密码"]').trigger("click");
expect(wrapper.get('[aria-label="密码"]').attributes("type")).toBe("text");
expect(wrapper.text()).toContain("RECRUITING AUTOMATION");
expect(wrapper.text()).toContain("CURRENT DEVICE");
expect(wrapper.text()).toContain("BOSS ACCOUNT");
expect(wrapper.text()).toContain("BEYOND THE RESUME");
```

另测“记住账号”只写 `localStorage["leion-hr:remembered-username"]`，不写密码或令牌；忘记密码提示联系管理员。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd apps/web && npm test -- --run src/pages/__tests__/LoginPage.spec.ts src/layouts/__tests__/AppShell.spec.ts src/components/__tests__/FirstPasswordChange.spec.ts src/__tests__/App.spec.ts`

Expected: FAIL，缺少原版结构和交互。

- [ ] **Step 3: 实现共享视觉与结构**

在 `styles.css` 建立 `--ink:#090e80`、`--violet:#7c65eb`、`--cyan:#83e4ec`、32px 玻璃外壳、80px 顶栏、208px 浅色侧栏、胶囊导航、虚线圆环、底部文字流及响应式规则。

`LoginPage.vue` 增加密码显隐、记住用户名和管理员找回提示；保留真实 `login()` 与提交锁。`FirstPasswordChange.vue` 仅换原版玻璃样式。`AppShell.vue` 恢复编号 01–05、用户简写头像、退出入口、设备/BOSS 信息位和文字流；Agent 状态必须来自真实请求，失败显示“状态未知”。`AppDrawer.vue` 保留 dialog、Esc、遮罩、焦点恢复，恢复圆形 `×` 按钮和滑入样式。

- [ ] **Step 4: 运行测试确认通过**

Run 同 Step 2。Expected: PASS。

---

### Task 2: 原版工作台

**Files:**
- Modify: `apps/web/src/pages/DashboardPage.vue`
- Modify: `apps/web/src/pages/__tests__/DashboardPage.spec.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:** 继续使用 `listAgentRuns()`；不新增任务或统计 API。

- [ ] **Step 1: 写失败测试**

```ts
for (const text of ["FIND.", "SCORE.", "CONNECT.", "Active Mission", "今日发现", "评分达标", "问候成功", "收到简历", "实时任务流", "200 次 / 天"]) {
  expect(wrapper.text()).toContain(text);
}
expect(wrapper.findAll(".metric-value").every(n => n.text() === "—")).toBe(true);
expect(wrapper.get('[aria-label="暂停任务"]').attributes("disabled")).toBeDefined();
expect(wrapper.text()).not.toMatch(/326|148|126|37|王女士|李先生/);
```

保留 Agent 成功、空列表、失败重试、状态映射测试。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd apps/web && npm test -- --run src/pages/__tests__/DashboardPage.spec.ts`

- [ ] **Step 3: 实现页面**

按原版顺序恢复主视觉、Active Mission 渐变卡、四指标、实时任务流、共享额度卡和真实 Agent 面板。任务按钮禁用并写“任务控制暂未接入”；四指标为 `—`；额度仅显示真实规则 `200 次 / 天`，已用/剩余/百分比/岗位消耗均为 `—`。

- [ ] **Step 4: 运行测试确认通过**

Run 同 Step 2。Expected: PASS。

---

### Task 3: 原版岗位管理

**Files:**
- Modify: `apps/web/src/pages/JobsPage.vue`
- Modify: `apps/web/src/pages/__tests__/JobsPage.spec.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:** 保持 `listJobs()`、`createJob(JobWrite)`、`updateJob(id,payload)`。

- [ ] **Step 1: 写失败测试**

```ts
expect(wrapper.text()).toContain("JOB MISSIONS.");
expect(wrapper.get('[data-testid="jobs-total"]').text()).toContain("2");
expect(wrapper.get('[data-testid="jobs-running"]').text()).toContain("1");
expect(wrapper.get('[data-testid="jobs-candidates"]').text()).toContain("—");
await wrapper.get('[aria-label="查看高级前端工程师详情"]').trigger("click");
for (const text of ["JOB DESCRIPTION", "HARD REQUIREMENTS", "AI SCORE THRESHOLD", "GREETING", "TASK STATUS"]) expect(wrapper.get('[role="dialog"]').text()).toContain(text);
expect(wrapper.get('[role="dialog"]').text()).toContain("硬性条件暂未接入");
```

保留现有筛选、创建、编辑、启停、失败保留表单和重复保存锁测试。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd apps/web && npm test -- --run src/pages/__tests__/JobsPage.spec.ts`

- [ ] **Step 3: 实现页面**

恢复英文标题、三项统计、胶囊筛选、三列岗位卡和原版抽屉。总数/运行数从真实岗位计算；候选人数与最近运行显示 `—`。卡片展示真实名称、状态、JD 摘要、阈值。详情按五区排列；硬性条件明确未接入。CRUD payload 不增加字段，岗位页不显示独立额度。

- [ ] **Step 4: 运行测试确认通过**

Run 同 Step 2。Expected: PASS。

---

### Task 4: 原版候选人

**Files:**
- Modify: `apps/web/src/pages/CandidatesPage.vue`
- Modify: `apps/web/src/pages/__tests__/CandidatesPage.spec.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:** 保持 `listCandidates(q)`、`markExchange(candidateId,operator)` 和 `user: UserMe`。

- [ ] **Step 1: 写失败测试**

```ts
expect(wrapper.text()).toContain("HUMAN POTENTIAL.");
expect(wrapper.get('[data-testid="candidate-total"]').text()).toContain("1");
for (const id of ["candidate-high-score", "candidate-contacted", "candidate-resume"]) expect(wrapper.get(`[data-testid="${id}"]`).text()).toContain("—");
for (const label of ["筛选候选人岗位", "筛选处理状态", "筛选 AI 分数"]) expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeDefined();
```

详情抽屉测试四区 `EXPERIENCE`、`MATCH EVIDENCE`、`RISK NOTE`、`ACTIVITY` 均存在；“查看简历”禁用；交换标记仍调用真实 API。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd apps/web && npm test -- --run src/pages/__tests__/CandidatesPage.spec.ts`

- [ ] **Step 3: 实现页面**

恢复标题、四指标、工具栏、候选人行和详情抽屉。总数取真实数组长度，其他指标为 `—`；仅姓名/BOSS ID 搜索可用，岗位/状态/分数筛选禁用并标明暂未接入。展示真实基础字段；AI 分数、摘要、问候和简历状态为 `—`。详情缺失区逐区说明，不能删除整个抽屉。

- [ ] **Step 4: 运行测试确认通过**

Run 同 Step 2。Expected: PASS。

---

### Task 5: 原版简历库

**Files:**
- Modify: `apps/web/src/pages/ResumesPage.vue`
- Modify: `apps/web/src/pages/__tests__/ResumesPage.spec.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:** 保持 `listJobs()`、`uploadResume(file)`；不伪造岗位关联。

- [ ] **Step 1: 写失败测试**

```ts
expect(wrapper.text()).toContain("RESUME LIBRARY.");
expect(wrapper.text()).toContain("STEP 01 / 选择一个岗位");
await wrapper.get('[aria-label="选择岗位高级前端工程师"]').trigger("click");
expect(wrapper.findAll("[data-testid^='resume-stat-']")).toHaveLength(3);
expect(wrapper.findAll("[data-testid^='resume-stat-']").every(n => n.text().includes("—"))).toBe(true);
for (const label of ["按姓名筛选简历", "按分数筛选简历", "按标签筛选简历", "按状态筛选简历"]) expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeDefined();
```

上传成功同时断言真实文件名和 `parse_status`；切换岗位清理上次反馈。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd apps/web && npm test -- --run src/pages/__tests__/ResumesPage.spec.ts`

- [ ] **Step 3: 实现页面**

把启用岗位渲染成三列按钮卡，以 `aria-pressed` 表示选中；未选显示 `CHOOSE A POSITION.`。选中后保留三项统计和四项禁用筛选，列表区写“简历列表及岗位关联暂未接入”。上传放入独立原版面板，成功显示所选文件名与真实解析状态，失败可重试，换岗位清空反馈。

- [ ] **Step 4: 运行测试确认通过**

Run 同 Step 2。Expected: PASS。

---

### Task 6: 原版系统设置与账号管理

**Files:**
- Modify: `apps/web/src/pages/SettingsPage.vue`
- Modify: `apps/web/src/components/HrAccountManagement.vue`
- Modify: `apps/web/src/pages/__tests__/SettingsPage.spec.ts`
- Modify: `apps/web/src/components/__tests__/HrAccountManagement.spec.ts`
- Modify: `apps/web/src/styles.css`

**Interfaces:** 保持 Agent Key 与 HR 管理 API；普通 HR 不挂载管理组件。

- [ ] **Step 1: 写失败测试**

```ts
for (const text of ["SYSTEM SETTINGS.", "ACCOUNT & CONNECTION", "DAILY SHARED QUOTA", "200 次 / 天", "SAFETY AUTOMATION"]) expect(wrapper.text()).toContain(text);
expect(wrapper.text()).toContain("BOSS 账号状态暂未接入");
for (const label of ["随机发送间隔", "登录失效自动暂停", "连续异常自动暂停", "额度耗尽自动暂停"]) expect(wrapper.get(`[aria-label="${label}"]`).attributes("disabled")).toBeDefined();
expect(wrapper.text()).not.toMatch(/今日已用 126|剩余 74/);
expect(api.listUsers).not.toHaveBeenCalled();
```

保留 Key 创建一次性明文、吊销、错误不丢列表，以及管理员新建/停用/启用/重置测试；补充各操作 pending 期间不可重复请求。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd apps/web && npm test -- --run src/pages/__tests__/SettingsPage.spec.ts src/components/__tests__/HrAccountManagement.spec.ts`

- [ ] **Step 3: 实现页面与管理抽屉**

恢复双列布局：账号与连接、共享额度、安全自动化、能力说明。账号/角色用真实 `UserMe`；BOSS 显示暂未接入；额度卡仅真实显示 200 次规则，其余 `—`；四个策略开关禁用并写“服务端策略，前端暂不可修改”。Agent Key 和管理员 HR 功能保留真实 API，弹层统一使用原版抽屉视觉；请求失败不关闭、不清输入、不改列表，pending 时锁住对应按钮。

- [ ] **Step 4: 运行测试确认通过**

Run 同 Step 2。Expected: PASS。

---

### Task 7: 全量回归与视觉验收

**Files:**
- Modify only if verification exposes a defect: Tasks 1–6 listed files.

**Interfaces:** 产出可构建、桌面与手机均符合规格的前端。

- [ ] **Step 1: 增加跨页面禁用演示数据断言**

```ts
const forbidden = ["326", "148", "126", "37", "王女士", "李先生"];
for (const value of forbidden) expect(wrapper.text()).not.toContain(value);
```

在 `AppShell.spec.ts` 逐页切换并确认五个标志标题、单一活动页面、普通 HR 权限隔离。

- [ ] **Step 2: 运行全部测试**

Run: `cd apps/web && npm test -- --run`

Expected: 全部 PASS，0 failed。

- [ ] **Step 3: 执行生产构建**

Run: `cd apps/web && npm run build`

Expected: exit code 0，`vue-tsc`/Vite 无错误。

- [ ] **Step 4: 桌面视觉验收**

在约 1280px 逐项对照原始 HTML：双栏登录、玻璃外壳、浅色侧栏、五个英文标题、工作台控制卡/指标/任务流/额度、岗位卡、候选人行、岗位选择卡、设置双列、紫青渐变、虚线圆环、抽屉、底部文字流。

- [ ] **Step 5: 手机与无障碍验收**

在约 390px 检查登录、首次改密、五页导航、抽屉、表单、空/错状态；确认无页面级横向滚动，Tab 焦点可见，Esc 和遮罩关闭抽屉；启用 reduced motion 后无非必要动画。

- [ ] **Step 6: 汇报而不提交**

列出测试数量、构建结果、视觉验收结果和仍受后端限制的模块；不执行 `git commit`、合并或覆盖主分支。
