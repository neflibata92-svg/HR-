# LEION HR 可点击管理后台原型实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有单页工作台视觉稿扩展为可点击切换的五页面 LEION HR 管理后台原型。

**Architecture:** 继续使用一个独立 HTML 原型文件，在文件内按页面职责拆分五个视图模板，以少量原生 JavaScript 管理导航、筛选、详情抽屉和演示状态。所有数据使用本地演示对象，不连接 API，也不修改 `apps/web` 正式前端。

**Tech Stack:** HTML5、CSS3、原生 JavaScript、Google Fonts

**Spec:** `docs/superpowers/specs/2026-09-20-leion-hr-clickable-prototype-design.md`

## Global Constraints

- 品牌名称统一为 `LEION HR`。
- 每位 HR 每个自然日总计 200 次打招呼额度，所有岗位共享。
- 岗位管理中不得出现岗位独立招呼额度设置。
- 简历库必须先选择岗位，之后才能展示该岗位的简历。
- 保持深靛蓝 `#090E80`、蓝紫青渐变、大圆角、圆形轨道和衬线大标题的视觉语言。
- 原型只使用演示数据，不连接真实后端，不修改正式产品代码。
- 桌面与手机宽度均须可浏览。

## Review Focus

- 未选择岗位进入简历库时：只显示岗位选择引导，不混合展示全部简历。
- 切换简历库岗位时：人才列表和顶部统计必须同步更新。
- 同一候选人匹配多个岗位时：可以出现在多个岗位结果中，并显示其他匹配岗位提示。
- 窄屏查看时：五个页面仍有可操作的导航入口，详情抽屉不会超出屏幕。
- 重复点击导航、筛选和开关时：界面状态应稳定，不重复插入内容或产生脚本错误。

---

### Task 1: 建立五页面原型外壳与导航

**Files:**
- Modify: `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`
- Test: 浏览器手工检查同一原型文件

**Interfaces:**
- Consumes: 现有工作台 HTML、统一顶部栏和左侧导航。
- Produces: `showPage(pageId)` 页面切换函数，以及 `dashboard`、`jobs`、`candidates`、`resumes`、`settings` 五个页面容器。

- [ ] **Step 1: 记录导航验收检查**

在实施前确认以下失败状态：当前左侧五个导航项只是静态元素，点击“岗位管理”等入口不会切换页面。

- [ ] **Step 2: 为导航增加稳定标识**

为每个导航项增加 `data-page`，目标值固定为：

```html
<a data-page="dashboard">工作台</a>
<a data-page="jobs">岗位管理</a>
<a data-page="candidates">候选人</a>
<a data-page="resumes">简历库</a>
<a data-page="settings">系统设置</a>
```

- [ ] **Step 3: 建立页面容器和切换函数**

页面容器统一使用：

```html
<section class="page active" id="page-dashboard"></section>
<section class="page" id="page-jobs"></section>
<section class="page" id="page-candidates"></section>
<section class="page" id="page-resumes"></section>
<section class="page" id="page-settings"></section>
```

切换函数必须只激活一个页面及一个导航项：

```js
function showPage(pageId) {
  document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
  document.querySelectorAll('[data-page]').forEach(link => link.classList.remove('active'));
  document.getElementById(`page-${pageId}`).classList.add('active');
  document.querySelector(`[data-page="${pageId}"]`).classList.add('active');
}
```

- [ ] **Step 4: 增加页面切换和窄屏样式**

`.page` 默认隐藏，`.page.active` 显示并执行轻微淡入；小屏幕把侧栏改为可横向滚动的胶囊导航，而不是完全隐藏。

- [ ] **Step 5: 浏览器验证**

逐个点击五个导航，确认：标题和内容发生切换、只有当前导航高亮、重复点击无异常、手机宽度仍可切换。

- [ ] **Step 6: 保存阶段结果**

不执行 Git 提交；原型文件保留在现有视觉稿目录中，等待整体验收。

---

### Task 2: 完成岗位管理页面

**Files:**
- Modify: `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`
- Test: 浏览器手工检查岗位筛选与详情抽屉

**Interfaces:**
- Consumes: `showPage(pageId)` 和统一详情抽屉容器。
- Produces: `renderJobs(filter)`、`openJobDetail(jobId)`，供岗位搜索、状态筛选和卡片点击使用。

- [ ] **Step 1: 准备岗位演示数据**

建立至少三个岗位：高级产品经理、数据分析师、用户研究员。每项包含 `id`、`name`、`status`、`candidateCount`、`scoreThreshold`、`lastRun`、`jd`、`requirements`、`greeting`；不得包含岗位额度字段。

- [ ] **Step 2: 构建岗位页面头部与筛选区**

加入页面标题、岗位总数、运行中数量、搜索框、状态筛选胶囊和“新建岗位”按钮。

- [ ] **Step 3: 渲染岗位卡片**

每张卡片展示岗位名称、运行状态、候选人数、AI 阈值和最近运行时间。暂停岗位使用柔和灰紫状态，运行岗位使用青绿色状态。

- [ ] **Step 4: 实现筛选与演示反馈**

`renderJobs(filter)` 同时处理名称搜索和运行状态；无结果时显示“没有符合条件的岗位”。“新建岗位”按钮打开演示表单抽屉，并明确这是原型操作。

- [ ] **Step 5: 实现岗位详情抽屉**

`openJobDetail(jobId)` 展示 JD、硬性条件、AI 阈值、问候语和启停按钮。详情中不得出现岗位每日或每小时额度。

- [ ] **Step 6: 浏览器验证**

检查搜索、运行/暂停筛选、卡片详情、新建岗位入口和关闭抽屉；确认全文搜索不到“岗位额度”设置。

---

### Task 3: 完成候选人页面

**Files:**
- Modify: `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`
- Test: 浏览器手工检查候选人筛选与详情抽屉

**Interfaces:**
- Consumes: 岗位演示数据和统一详情抽屉。
- Produces: `renderCandidates()`、`openCandidateDetail(candidateId)`。

- [ ] **Step 1: 准备候选人演示数据**

至少提供五位候选人，每项包含 `id`、`name`、`jobId`、`score`、`summary`、`contactStatus`、`resumeStatus`、`experience`、`evidence`、`risk` 和 `timeline`。

- [ ] **Step 2: 构建候选人统计与筛选**

加入候选人总数、高分人数、已问候人数和已收简历人数；提供岗位、处理状态和最低 AI 分数筛选。

- [ ] **Step 3: 渲染候选人列表**

列表展示姓名、岗位、AI 分数环、判断摘要、问候状态和简历状态；高分使用蓝紫渐变强调，但不能只依赖颜色表达状态。

- [ ] **Step 4: 实现组合筛选**

`renderCandidates()` 同时应用岗位、处理状态和最低分数；无结果时显示可恢复的空状态，并保留清除筛选入口。

- [ ] **Step 5: 实现候选人详情抽屉**

展示经历摘要、匹配证据、风险提示和操作时间线；“查看简历”和“加入待沟通”按钮更新原型提示信息，不发起网络请求。

- [ ] **Step 6: 浏览器验证**

验证每种筛选及组合筛选、详情打开关闭、操作反馈、无结果状态和重复点击稳定性。

---

### Task 4: 完成按岗位筛选的简历库

**Files:**
- Modify: `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`
- Test: 浏览器手工检查岗位优先筛选、统计同步与多岗位提示

**Interfaces:**
- Consumes: 岗位和候选人演示数据、统一详情抽屉。
- Produces: `selectResumeJob(jobId)`、`renderResumes()`、`openResumeDetail(resumeId)`。

- [ ] **Step 1: 准备简历演示数据**

每份简历包含 `id`、`candidateId`、`jobIds`、`scoreByJob`、`tags`、`status`、`fileName`、`updatedAt`。至少一份简历的 `jobIds` 包含两个岗位，用于验证同一候选人的多岗位匹配。

- [ ] **Step 2: 建立岗位优先入口**

页面首屏首先显示岗位选择卡或选择器，并展示各岗位人才数量。初始 `selectedResumeJobId` 必须为 `null`，不得默认混合加载全部简历。

- [ ] **Step 3: 实现未选择岗位的引导状态**

当 `selectedResumeJobId === null` 时，仅显示“请先选择岗位查看简历”的引导和岗位入口，隐藏人才列表与岗位内二级筛选。

- [ ] **Step 4: 实现岗位结果与同步统计**

`selectResumeJob(jobId)` 更新当前岗位；`renderResumes()` 只保留 `jobIds.includes(selectedResumeJobId)` 的记录，并同步计算该岗位人才总数、已交换数和今日新增数。

- [ ] **Step 5: 增加岗位内二级筛选**

提供姓名搜索、最低 AI 分数、标签和简历状态筛选。AI 分数从 `scoreByJob[selectedResumeJobId]` 读取，确保同一候选人在不同岗位下可展示不同匹配分。

- [ ] **Step 6: 标示多岗位匹配**

当一份简历的 `jobIds.length > 1` 时显示“还匹配其他岗位”，详情抽屉列出岗位名称，但不复制文件或候选人身份。

- [ ] **Step 7: 浏览器验证**

确认首次进入无混合列表；依次选择三个岗位，核对列表和统计同步变化；验证二级筛选、多岗位提示和详情抽屉。

---

### Task 5: 完成系统设置与共享额度说明

**Files:**
- Modify: `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`
- Test: 浏览器手工检查设置分组、开关反馈和额度文案

**Interfaces:**
- Consumes: 统一页面外壳和原型反馈组件。
- Produces: `toggleDemoSetting(settingId)` 演示设置状态函数。

- [ ] **Step 1: 构建账号与连接设置**

展示当前 HR 账号、角色、BOSS 账号登录状态和 Agent 设备连接状态，并提供只做演示的“检查连接”反馈。

- [ ] **Step 2: 构建额度规则卡片**

固定显示：

```text
每位 HR 每天 200 次
所有岗位共享同一额度池
每日 00:00 自动刷新
额度耗尽后自动暂停新的打招呼
```

不得增加岗位额度输入框。

- [ ] **Step 3: 构建安全策略设置**

展示发送间隔、登录失效自动暂停、连续异常自动暂停和额度耗尽自动暂停。开关调用 `toggleDemoSetting(settingId)`，只更新视觉状态和反馈文案。

- [ ] **Step 4: 浏览器验证**

确认账号、设备、额度和安全策略分组完整；所有开关可重复操作；额度文案与工作台一致。

---

### Task 6: 统一视觉、交互与响应式验收

**Files:**
- Modify: `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`
- Test: 浏览器桌面与手机宽度手工验收

**Interfaces:**
- Consumes: 五个已完成页面及全部交互函数。
- Produces: 完整可点击原型。

- [ ] **Step 1: 统一视觉组件**

统一页面标题、数据卡、筛选胶囊、按钮、状态标签、空状态和详情抽屉的颜色、圆角、间距、字体及悬浮效果。

- [ ] **Step 2: 完善通用反馈与抽屉行为**

增加唯一的提示条和详情抽屉；重复操作只更新既有节点。点击关闭按钮或遮罩时关闭抽屉，按 `Escape` 也可关闭。

- [ ] **Step 3: 检查窄屏布局**

在约 390px 宽度下确认：导航可横向滚动、卡片改单列、表格转为信息卡、抽屉占满可用宽度、所有按钮可点击。

- [ ] **Step 4: 检查内容一致性**

全文检查 `TALENT FLOW`、`20 次`、`岗位额度`、`每小时额度` 等旧文案，确保品牌和额度规则没有冲突；允许“岗位消耗明细”，但不得表达为岗位可用额度。

- [ ] **Step 5: 完整走查五个页面**

按工作台 → 岗位管理 → 候选人 → 简历库 → 系统设置的顺序操作所有导航、筛选、详情和开关。重点验证 Review Focus 中五类情况。

- [ ] **Step 6: 确认预览地址**

使用现有原型服务器打开 `.superpowers/brainstorm/47853-1789903760/content/beyondx-style-dashboard.html`，向用户提供可点击预览地址和本轮完成项摘要。
