<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import {
  cancelScreeningTask,
  createScreeningTask,
  getScreeningTask,
  listAgentRuns,
  listCandidates,
  listJobs,
  listResumes,
  listReviews,
  listScreeningTasks,
  pauseScreeningTask,
  resumeScreeningTask,
  type AgentRun,
  type Job,
  type ScreeningTask,
} from "../api";
import EmptyState from "../components/EmptyState.vue";
import StatusBadge from "../components/StatusBadge.vue";

const emit = defineEmits<{ "open-job": [jobId: number, edit: boolean] }>();

const runs = ref<AgentRun[]>([]);
const jobs = ref<Job[]>([]);
const candidateCounts = ref<Record<number, number>>({});
const resumeCounts = ref<Record<number, number>>({});
const waitingResumeCounts = ref<Record<number, number>>({});
const resumeReceivedCounts = ref<Record<number, number>>({});
const reviewCounts = ref<Record<number, number>>({});
const jobStatsErrors = ref<Record<number, string[]>>({});
const loading = ref(true);
const error = ref("");
const jobsError = ref("");
const agentDataFresh = ref(false);
const taskError = ref("");
const taskBusy = ref(false);
const taskFormOpen = ref(false);
const currentTask = ref<ScreeningTask | null>(null);
const tasks = ref<ScreeningTask[]>([]);
const selectedJobId = ref("");
const selectedAgentRunId = ref("");
const requestedCount = ref(20);
let taskPollTimer: ReturnType<typeof setInterval> | null = null;
let taskPollBusy = false;
let taskListRequestId = 0;
let taskStateVersion = 0;
const taskRefreshRequestIds = new Map<number, number>();
const jobStatsRequestIds = new Map<number, number>();

const ACTIVE_TASK_STATUSES = ["ready", "running", "pausing", "paused", "cancelling"];
const AGENT_HEARTBEAT_MAX_AGE_MS = 45_000;
const enabledJobs = computed(() => jobs.value.filter((job) => job.enabled));
const selectedJob = computed(() => jobs.value.find((job) => job.id === Number(selectedJobId.value)) ?? null);
const activeTasks = computed(() => tasks.value.filter((task) => ACTIVE_TASK_STATUSES.includes(task.status)));
const readyRuns = computed(() => agentDataFresh.value ? runs.value.filter((run) => {
  const heartbeatAt = run.last_heartbeat ? new Date(run.last_heartbeat).getTime() : Number.NaN;
  const heartbeatFresh = Number.isFinite(heartbeatAt)
    && Date.now() - heartbeatAt <= AGENT_HEARTBEAT_MAX_AGE_MS;
  return ["online", "idle"].includes(run.status.toLowerCase())
    && run.availability === "idle"
    && run.current_task_id == null
    && run.boss_login_status === "logged_in"
    && heartbeatFresh;
}) : []);
const selectedReadyRun = computed(() => readyRuns.value.find((run) => run.id === Number(selectedAgentRunId.value)) ?? null);
const assignedRun = computed(() => runs.value.find((run) => run.id === currentTask.value?.assigned_agent_run_id) ?? null);
const taskCanPause = computed(() => currentTask.value?.status === "running");
const taskCanResume = computed(() => currentTask.value?.status === "paused");
const taskCanCancel = computed(() => ["ready", "running", "paused"].includes(currentTask.value?.status || ""));

function jobActiveTask(jobId: number): ScreeningTask | undefined {
  return activeTasks.value.find((task) => task.job_id === jobId);
}

function jobAgent(task?: ScreeningTask): AgentRun | undefined {
  if (!task) return undefined;
  return runs.value.find((run) => run.id === task.assigned_agent_run_id)
    ?? runs.value.find((run) => run.machine_id === task.machine_id);
}

function jobTasks(jobId: number): ScreeningTask[] {
  return tasks.value.filter((task) => task.job_id === jobId);
}

function jobTaskTotal(jobId: number, field: "contacted_count" | "failed_count"): number {
  return jobTasks(jobId).reduce((sum, task) => sum + task[field], 0);
}

function jobAgentStatus(task?: ScreeningTask): string {
  const run = jobAgent(task);
  return run ? statusLabel(run.status) : "未连接";
}

function openTaskForJob(job: Job): void {
  if (!job.enabled || job.readiness?.ready !== true || jobActiveTask(job.id) || !agentDataFresh.value || readyRuns.value.length === 0) return;
  taskFormOpen.value = true;
  selectedJobId.value = String(job.id);
}

function readinessMissingLabels(job: Job): string[] {
  const labels: Record<string, string> = {
    jd_text: "岗位 JD",
    boss_entry_url: "BOSS 岗位入口",
    default_requested_count: "默认筛选人数",
  };
  return (job.readiness?.missing ?? []).map((item) => labels[item] ?? item);
}

async function loadJobStats(job: Job): Promise<void> {
  const requestId = (jobStatsRequestIds.get(job.id) ?? 0) + 1;
  jobStatsRequestIds.set(job.id, requestId);
  const [candidateResult, resumeResult, waitingResult, receivedResult, reviewResult] = await Promise.allSettled([
    listCandidates("", { jobId: job.id }),
    listResumes({ jobId: job.id }),
    listCandidates("", { jobId: job.id, status: "waiting_resume" }),
    listCandidates("", { jobId: job.id, status: "resume_received" }),
    listReviews(job.id),
  ]);
  if (jobStatsRequestIds.get(job.id) !== requestId) return;
  const errors: string[] = [];
  if (candidateResult.status === "fulfilled") {
    candidateCounts.value = { ...candidateCounts.value, [job.id]: candidateResult.value.length };
  } else {
    errors.push("候选人统计加载失败");
  }
  if (resumeResult.status === "fulfilled") {
    resumeCounts.value = { ...resumeCounts.value, [job.id]: resumeResult.value.length };
  } else {
    errors.push("简历统计加载失败");
  }
  if (waitingResult.status === "fulfilled") {
    waitingResumeCounts.value = { ...waitingResumeCounts.value, [job.id]: waitingResult.value.length };
  } else {
    errors.push("等待简历统计加载失败");
  }
  if (receivedResult.status === "fulfilled") {
    resumeReceivedCounts.value = { ...resumeReceivedCounts.value, [job.id]: receivedResult.value.length };
  } else {
    errors.push("收到简历统计加载失败");
  }
  if (reviewResult.status === "fulfilled") {
    reviewCounts.value = { ...reviewCounts.value, [job.id]: reviewResult.value.length };
  } else {
    errors.push("待复核统计加载失败");
  }
  jobStatsErrors.value = { ...jobStatsErrors.value, [job.id]: errors };
}

async function loadJobStatsFor(jobRows: Job[]): Promise<void> {
  await Promise.all(jobRows.map((job) => loadJobStats(job)));
}

async function refreshTask(task: ScreeningTask): Promise<void> {
  const requestId = (taskRefreshRequestIds.get(task.id) ?? 0) + 1;
  taskRefreshRequestIds.set(task.id, requestId);
  const versionAtStart = taskStateVersion;
  try {
    const updated = await getScreeningTask(task.id);
    if (taskRefreshRequestIds.get(task.id) !== requestId || versionAtStart !== taskStateVersion) return;
    const index = tasks.value.findIndex((item) => item.id === updated.id);
    if (index >= 0) tasks.value[index] = updated;
    currentTask.value = activeTasks.value[0] ?? null;
    taskError.value = "";
  } catch (err) {
    if (taskRefreshRequestIds.get(task.id) !== requestId || versionAtStart !== taskStateVersion) return;
    taskError.value = `同步任务状态失败：${err instanceof Error ? err.message : String(err)}`;
  }
}

async function refreshCurrentTask(): Promise<void> {
  await Promise.all(activeTasks.value.map((task) => refreshTask(task)));
}

function stopTaskPolling(): void {
  if (taskPollTimer !== null) clearInterval(taskPollTimer);
  taskPollTimer = null;
}

function syncTaskPolling(): void {
  stopTaskPolling();
  taskPollTimer = setInterval(() => {
    if (taskPollBusy) return;
    taskPollBusy = true;
    void Promise.all([loadRuns(), loadTasks()]).finally(() => {
      taskPollBusy = false;
    });
  }, 5000);
}

function taskStatusLabel(status: string): string {
  return ({ ready: "等待领取", running: "执行中", paused: "已暂停", completed: "已完成", cancelled: "已取消", failed: "失败" } as Record<string, string>)[status] || status;
}

async function createTask(): Promise<void> {
  if (!selectedJobId.value || selectedJob.value?.readiness?.ready !== true || jobActiveTask(Number(selectedJobId.value)) || !selectedReadyRun.value || requestedCount.value < 1 || requestedCount.value > 50) return;
  taskBusy.value = true;
  taskError.value = "";
  try {
    const createdTask = await createScreeningTask({
      job_id: Number(selectedJobId.value),
      assigned_agent_run_id: Number(selectedAgentRunId.value),
      requested_count: requestedCount.value,
    });
    applyControlledTask(createdTask);
    taskFormOpen.value = false;
    syncTaskPolling();
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : "任务创建失败";
  } finally {
    taskBusy.value = false;
  }
}

function applyControlledTask(updated: ScreeningTask): void {
  taskStateVersion += 1;
  const index = tasks.value.findIndex((item) => item.id === updated.id);
  if (index >= 0) {
    tasks.value[index] = updated;
  } else {
    tasks.value.unshift(updated);
  }
  currentTask.value = activeTasks.value[0] ?? null;
}

async function pauseTask(task = currentTask.value): Promise<void> {
  if (!task || task.status !== "running") return;
  taskBusy.value = true;
  try {
    const updated = await pauseScreeningTask(task.id, "人工检查");
    applyControlledTask(updated);
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : "暂停失败";
  } finally {
    taskBusy.value = false;
  }
}

async function resumeTask(task = currentTask.value): Promise<void> {
  if (!task || task.status !== "paused") return;
  taskBusy.value = true;
  try {
    const updated = await resumeScreeningTask(task.id);
    applyControlledTask(updated);
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : "继续失败";
  } finally {
    taskBusy.value = false;
  }
}

async function cancelTask(task = currentTask.value): Promise<void> {
  if (!task || !["ready", "running", "paused"].includes(task.status)) return;
  taskBusy.value = true;
  try {
    const updated = await cancelScreeningTask(task.id);
    applyControlledTask(updated);
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : "停止失败";
  } finally {
    taskBusy.value = false;
  }
}


function statusLabel(status: string): string {
  const normalized = status.toLowerCase();
  if (["online", "running", "active"].includes(normalized)) return "在线";
  if (["idle", "waiting"].includes(normalized)) return "空闲";
  if (["paused"].includes(normalized)) return "已暂停";
  if (["offline", "stopped"].includes(normalized)) return "离线";
  if (["error", "failed"].includes(normalized)) return "异常";
  return status;
}

function statusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  const normalized = status.toLowerCase();
  if (["online", "running", "active"].includes(normalized)) return "success";
  if (["idle", "waiting", "paused"].includes(normalized)) return "warning";
  if (["error", "failed"].includes(normalized)) return "danger";
  return "neutral";
}

function formatHeartbeat(value: string | null): string {
  if (!value) return "暂无心跳";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : `${date.toLocaleString("zh-CN")}（本地时间）`;
}

async function loadRuns(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    runs.value = await listAgentRuns();
    agentDataFresh.value = true;
  } catch (err) {
    agentDataFresh.value = false;
    const message = err instanceof Error ? err.message : String(err);
    error.value = `加载 Agent 状态失败：${message}`;
  } finally {
    loading.value = false;
  }
}

async function loadTasks(): Promise<void> {
  const requestId = ++taskListRequestId;
  const versionAtStart = taskStateVersion;
  try {
    const taskRows = await listScreeningTasks();
    if (requestId !== taskListRequestId || versionAtStart !== taskStateVersion) return;
    tasks.value = taskRows;
    currentTask.value = tasks.value.find((task) => ACTIVE_TASK_STATUSES.includes(task.status)) ?? null;
    taskError.value = "";
  } catch (err) {
    if (requestId !== taskListRequestId || versionAtStart !== taskStateVersion) return;
    taskError.value = `任务列表加载失败：${err instanceof Error ? err.message : String(err)}`;
  }
}

async function loadJobs(): Promise<void> {
  jobsError.value = "";
  try {
    const jobRows = await listJobs();
    jobs.value = jobRows;
    await loadJobStatsFor(jobRows);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    jobsError.value = `岗位列表加载失败：${message}`;
  }
}

watch(selectedJobId, () => {
  requestedCount.value = selectedJob.value?.default_requested_count ?? 20;
});
watch(readyRuns, () => {
  if (selectedAgentRunId.value && !selectedReadyRun.value) selectedAgentRunId.value = "";
});
watch(() => currentTask.value?.status, () => syncTaskPolling());

onMounted(() => {
  syncTaskPolling();
  taskPollBusy = true;
  void Promise.all([loadRuns(), loadJobs(), loadTasks()]).finally(() => {
    taskPollBusy = false;
  });
});

onUnmounted(() => stopTaskPolling());
</script>

<template>
  <section class="dashboard-page page" data-testid="dashboard-page" data-page-panel>
    <div class="page-kicker">WORKSPACE / LIVE CONTROL</div>

    <section class="dashboard-hero">
      <div class="dashboard-hero-copy">
        <p class="eyebrow">RECRUITING INTELLIGENCE</p>
        <h1>FIND.<br /><em>SCORE.</em><br />CONNECT.</h1>
        <p>让人才发现、智能判断与真实沟通自然流动。</p>
      </div>
      <article class="mission-control">
        <div>
          <p class="eyebrow">Active Mission</p>
          <h2>{{ currentTask ? `任务 #${currentTask.id} · ${currentTask.job_name_snapshot}` : "招聘任务控制台" }}</h2>
          <p v-if="currentTask">
            {{ taskStatusLabel(currentTask.status) }} · 已处理 {{ currentTask.processed_count }} / {{ currentTask.requested_count }} 人
          </p>
          <p v-if="currentTask && assignedRun">执行设备：{{ assignedRun.machine_id }}</p>
          <p v-else-if="!currentTask">当前没有活动任务，可选择已就绪岗位和空闲 Agent 启动。</p>
        </div>
        <div class="mission-actions">
          <button v-if="currentTask" type="button" class="btn btn-secondary" aria-label="刷新当前任务" :disabled="taskBusy" @click="refreshCurrentTask">刷新任务</button>
          <button type="button" aria-label="新建筛选任务" @click="taskFormOpen = !taskFormOpen">新建任务</button>
          <button v-if="taskCanPause" type="button" aria-label="暂停任务" :disabled="taskBusy" @click="pauseTask()">暂停任务</button>
          <button v-if="taskCanResume" type="button" aria-label="继续任务" :disabled="taskBusy" @click="resumeTask()">继续任务</button>
          <button v-if="currentTask" type="button" aria-label="停止任务" :disabled="taskBusy || !taskCanCancel" @click="cancelTask()">停止任务</button>
          <template v-if="!currentTask">
            <button type="button" aria-label="暂停任务" disabled>暂停任务</button>
            <button type="button" aria-label="停止任务" disabled>停止任务</button>
          </template>
        </div>
      </article>
    </section>

    <section v-if="jobsError" class="panel error" data-testid="jobs-load-error" role="alert">
      <p>{{ jobsError }}</p>
      <button type="button" class="secondary" aria-label="重试岗位列表" @click="loadJobs">重试岗位列表</button>
    </section>

    <section v-if="jobs.length" class="job-grid job-card-grid" aria-label="岗位工作台">
      <article v-for="job in jobs" :key="job.id" class="panel job-card" :data-testid="`dashboard-job-card-${job.id}`">
        <div class="job-card-top">
          <StatusBadge
            :label="job.readiness?.ready === true ? '配置完整' : job.enabled ? '配置未完成' : '已停用'"
            :tone="job.readiness?.ready === true && job.enabled ? 'success' : 'warning'"
          />
          <span :data-testid="`job-readiness-${job.id}`">{{ job.readiness?.ready === true ? "配置完整" : "配置未完成" }}</span>
        </div>
        <h2>{{ job.name }}</h2>
        <p>岗位状态：{{ job.enabled ? "招聘中" : "已停用" }}</p>
        <p :data-testid="`job-agent-${job.id}`">
          执行 Agent：{{ jobAgent(jobActiveTask(job.id))?.machine_id ?? "未分配" }} · Agent 状态：{{ jobAgentStatus(jobActiveTask(job.id)) }}
        </p>
        <p v-if="job.readiness?.ready !== true" class="error">
          {{ readinessMissingLabels(job).length ? `缺少 ${readinessMissingLabels(job).join("、")}` : "岗位配置尚未完成" }}
        </p>
        <p :data-testid="`job-task-progress-${job.id}`">
          <template v-if="jobActiveTask(job.id)">
            {{ taskStatusLabel(jobActiveTask(job.id)!.status) }} · {{ jobActiveTask(job.id)!.processed_count }} / {{ jobActiveTask(job.id)!.requested_count }}
          </template>
          <template v-else>暂无活动任务</template>
        </p>
        <dl class="job-card-facts job-operation-facts">
          <div><dt>已联系</dt><dd :data-testid="`job-contacted-count-${job.id}`">{{ jobTaskTotal(job.id, "contacted_count") }}</dd></div>
          <div><dt>等待简历</dt><dd :data-testid="`job-waiting-resume-count-${job.id}`">{{ waitingResumeCounts[job.id] ?? "—" }}</dd></div>
          <div><dt>已收到简历</dt><dd :data-testid="`job-resume-received-count-${job.id}`">{{ resumeReceivedCounts[job.id] ?? "—" }}</dd></div>
          <div><dt>待复核</dt><dd :data-testid="`job-review-count-${job.id}`">{{ reviewCounts[job.id] ?? "—" }}</dd></div>
          <div><dt>失败</dt><dd :data-testid="`job-failed-count-${job.id}`">{{ jobTaskTotal(job.id, "failed_count") }}</dd></div>
        </dl>
        <div v-if="jobStatsErrors[job.id]?.length" class="error" role="alert">
          <p>{{ jobStatsErrors[job.id].join("；") }}</p>
          <button type="button" :aria-label="`重试${job.name}统计`" @click="loadJobStats(job)">重试统计</button>
        </div>
        <div class="mission-actions job-card-actions">
          <button
            v-if="!jobActiveTask(job.id)"
            type="button"
            :aria-label="`启动${job.name}任务`"
            :disabled="!job.enabled || job.readiness?.ready !== true || !agentDataFresh || readyRuns.length === 0"
            :title="!agentDataFresh ? 'Agent 状态未知' : readyRuns.length === 0 ? '暂无可用 Agent' : ''"
            @click="openTaskForJob(job)"
          >启动任务</button>
          <button
            v-if="jobActiveTask(job.id)"
            type="button"
            class="btn btn-secondary"
            :aria-label="`刷新${job.name}任务`"
            :disabled="taskBusy"
            @click="refreshTask(jobActiveTask(job.id)!)"
          >刷新</button>
          <button
            v-if="jobActiveTask(job.id)?.status === 'running'"
            type="button"
            :aria-label="`暂停${job.name}任务`"
            :disabled="taskBusy"
            @click="pauseTask(jobActiveTask(job.id)!)"
          >暂停</button>
          <button
            v-if="jobActiveTask(job.id)?.status === 'paused'"
            type="button"
            :aria-label="`继续${job.name}任务`"
            :disabled="taskBusy"
            @click="resumeTask(jobActiveTask(job.id)!)"
          >继续</button>
          <button
            v-if="jobActiveTask(job.id)"
            type="button"
            :aria-label="`终止${job.name}任务`"
            :disabled="taskBusy"
            @click="cancelTask(jobActiveTask(job.id)!)"
          >终止</button>
          <button
            type="button"
            class="secondary"
            :aria-label="job.readiness?.ready === true && job.enabled ? `查看${job.name}详情` : `完善${job.name}配置`"
            @click="emit('open-job', job.id, job.readiness?.ready !== true || !job.enabled)"
          >{{ job.readiness?.ready === true && job.enabled ? "查看详情" : "完善岗位配置" }}</button>
        </div>
      </article>
    </section>

    <section v-else-if="!jobsError" class="panel empty-job-workspace">
      <h2>暂无招聘岗位</h2>
      <p>先创建岗位并完成招聘要求配置，才能启动筛选任务。</p>
      <button type="button" aria-label="创建第一个岗位" @click="emit('open-job', 0, true)">创建第一个岗位</button>
    </section>

    <section v-if="activeTasks.length" class="job-grid" aria-label="全部活动任务">
      <article v-for="task in activeTasks" :key="task.id" class="panel" data-testid="active-task-card">
        <div class="section-heading">
          <div>
            <p class="eyebrow">ACTIVE TASK</p>
            <h2>任务 #{{ task.id }} · {{ task.job_name_snapshot }}</h2>
          </div>
          <StatusBadge :label="taskStatusLabel(task.status)" :tone="task.status === 'failed' ? 'danger' : task.status === 'paused' ? 'warning' : 'success'" />
        </div>
        <p>已处理 {{ task.processed_count }} / {{ task.requested_count }} 人；达标 {{ task.eligible_count }}；已联系 {{ task.contacted_count }}；待复核 {{ task.review_count }}。</p>
        <p v-if="task.machine_id">执行设备：{{ task.machine_id }}</p>
        <div class="mission-actions">
          <button type="button" class="btn btn-secondary" :aria-label="activeTasks.length === 1 ? '刷新当前任务' : `刷新任务 #${task.id}`" :disabled="taskBusy" @click="refreshTask(task)">刷新任务</button>
          <button v-if="task.status === 'running'" type="button" :aria-label="activeTasks.length === 1 ? '暂停任务' : `暂停任务 #${task.id}`" :disabled="taskBusy" @click="pauseTask(task)">暂停任务</button>
          <button v-if="task.status === 'paused'" type="button" :aria-label="activeTasks.length === 1 ? '继续任务' : `继续任务 #${task.id}`" :disabled="taskBusy" @click="resumeTask(task)">继续任务</button>
          <button type="button" :aria-label="activeTasks.length === 1 ? '停止任务' : `停止任务 #${task.id}`" :disabled="taskBusy || !['ready', 'running', 'paused'].includes(task.status)" @click="cancelTask(task)">停止任务</button>
        </div>
      </article>
    </section>

    <form v-if="taskFormOpen" class="panel form-grid task-form" aria-label="筛选任务表单" @submit.prevent="createTask">
      <div class="form-field span-2">
        <label for="task-job">启用岗位</label>
        <select id="task-job" v-model="selectedJobId" aria-label="任务岗位" required>
          <option value="">请选择岗位</option>
          <option v-for="job in enabledJobs" :key="job.id" :value="String(job.id)" :disabled="job.readiness?.ready !== true || Boolean(jobActiveTask(job.id))">{{ job.name }}{{ job.readiness?.ready !== true ? "（配置未完成）" : jobActiveTask(job.id) ? "（已有活动任务）" : "" }}</option>
        </select>
        <small v-if="enabledJobs.length === 0">暂无启用岗位，请先到岗位管理启用岗位。</small>
        <small v-else-if="selectedJob && selectedJob.readiness?.ready !== true" class="error">配置未完成：{{ readinessMissingLabels(selectedJob).join("、") || "请完善岗位配置" }}</small>
        <small v-else-if="selectedJob && jobActiveTask(selectedJob.id)" class="error">该岗位已有活动任务，请先完成或终止现有任务。</small>
      </div>
      <div class="form-field">
        <label for="task-agent">执行 Agent</label>
        <select id="task-agent" v-model="selectedAgentRunId" aria-label="任务 Agent" required>
          <option value="">请选择空闲 Agent</option>
          <option v-for="run in readyRuns" :key="run.id" :value="String(run.id)">{{ run.machine_id }}</option>
        </select>
        <small v-if="readyRuns.length === 0" class="error">没有在线、空闲且已登录 BOSS 的 Agent。</small>
      </div>
      <div class="form-field">
        <label for="task-count">筛选人数</label>
        <input id="task-count" v-model.number="requestedCount" aria-label="筛选人数" type="number" min="1" max="50" required />
      </div>
      <p class="muted span-2">AI 将根据该岗位的完整 JD 自动评分；达到分数门槛后自动打招呼。</p>
      <p v-if="taskError" class="error span-2" role="alert">{{ taskError }}</p>
      <div class="form-actions span-2">
        <button class="btn btn-secondary" type="button" @click="taskFormOpen = false">取消</button>
        <button
          class="btn btn-primary"
          type="submit"
          aria-label="提交筛选任务"
          :disabled="taskBusy || !selectedJobId || !selectedReadyRun || selectedJob?.readiness?.ready !== true || Boolean(selectedJob && jobActiveTask(selectedJob.id)) || requestedCount < 1 || requestedCount > 50"
        >
          {{ taskBusy ? "创建中…" : "创建任务" }}
        </button>
      </div>
    </form>

    <p v-if="taskError && !taskFormOpen" class="error" role="alert">{{ taskError }}</p>

    <article class="panel task-control-boundary">
      <div><p class="eyebrow">TASK CONTROL</p><h2>任务状态</h2></div>
      <template v-if="currentTask">
        <p>
          状态：{{ taskStatusLabel(currentTask.status) }}；达标 {{ currentTask.eligible_count }}；已联系 {{ currentTask.contacted_count }}；待复核 {{ currentTask.review_count }}；失败 {{ currentTask.failed_count }}。
        </p>
        <p v-if="currentTask.pause_reason" class="error">暂停原因：{{ currentTask.pause_reason }}</p>
      </template>
      <p v-else>当前没有活动任务；新建任务后会自动保存，刷新页面也可继续查看与控制。</p>
    </article>

    <article class="panel agent-panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">AGENTS</p>
          <h2>Agent 设备</h2>
        </div>
        <button type="button" aria-label="刷新 Agent 状态" :disabled="loading" @click="loadRuns">
          {{ loading ? "加载中…" : error ? "重试" : "刷新状态" }}
        </button>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="loading && runs.length === 0" aria-live="polite">正在加载 Agent 状态…</p>
      <EmptyState
        v-else-if="runs.length === 0 && !error"
        title="暂无 Agent 设备"
        description="Agent 首次上报运行状态后会显示在这里。"
      />
      <div v-if="runs.length" class="agent-list">
        <article v-for="run in runs" :key="run.id" class="agent-card">
          <div>
            <h3>{{ run.machine_id }}</h3>
            <p class="muted">最后心跳：{{ formatHeartbeat(run.last_heartbeat) }}</p>
          </div>
          <StatusBadge :label="statusLabel(run.status)" :tone="statusTone(run.status)" />
          <p v-if="run.last_error" class="error">最近错误：{{ run.last_error }}</p>
        </article>
      </div>
    </article>
  </section>
</template>
