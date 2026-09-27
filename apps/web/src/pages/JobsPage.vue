<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";

import {
  createJob,
  listCandidates,
  listJobs,
  listResumes,
  listScreeningTasks,
  updateJob,
  type Job,
  type JobWrite,
  type ScreeningTask,
} from "../api";
import AppDrawer from "../components/AppDrawer.vue";
import EmptyState from "../components/EmptyState.vue";
import StatusBadge from "../components/StatusBadge.vue";

const props = withDefaults(defineProps<{ targetJobId?: number | null; editTarget?: boolean }>(), {
  targetJobId: null,
  editTarget: false,
});

const jobs = ref<Job[]>([]);
const tasks = ref<ScreeningTask[]>([]);
const candidateCounts = ref<Record<number, number>>({});
const resumeCounts = ref<Record<number, number>>({});
const statsErrors = ref<Record<number, string[]>>({});
const statsLoadingIds = ref<Set<number>>(new Set());
const loading = ref(true);
const loadError = ref("");
const tasksError = ref("");
const query = ref("");
const status = ref("all");
const detailJob = ref<Job | null>(null);
const formOpen = ref(false);
const editingJob = ref<Job | null>(null);
const saving = ref(false);
const togglingId = ref<number | null>(null);
const saveError = ref("");
const actionError = ref("");
let taskPollTimer: ReturnType<typeof setInterval> | null = null;
let operationalPollBusy = false;
let jobsRequestId = 0;
let tasksRequestId = 0;
const statsRequestIds = new Map<number, number>();

function openDetail(job: Job): void {
  detailJob.value = job;
}

function closeDetail(): void {
  detailJob.value = null;
}

const form = reactive<JobWrite>({
  name: "",
  jd_text: "",
  score_threshold: 80,
  greet_template: "您好，看了您的经历很匹配，方便发一下附件简历吗？",
  boss_entry_url: "",
  hourly_greet_limit: 20,
  min_action_delay_ms: 1500,
  max_action_delay_ms: 4000,
  default_requested_count: 20,
});

const filteredJobs = computed(() => {
  const keyword = query.value.trim().toLowerCase();
  return jobs.value.filter((job) => {
    const nameMatches = !keyword || job.name.toLowerCase().includes(keyword);
    const statusMatches = status.value === "all"
      || (status.value === "enabled" ? job.enabled : !job.enabled);
    return nameMatches && statusMatches;
  });
});
const runningJobs = computed(() => jobs.value.filter((job) => job.enabled).length);
const totalScreened = computed(() => tasks.value.reduce((sum, task) => sum + task.processed_count, 0));

function jobTasks(jobId: number): ScreeningTask[] {
  return tasks.value.filter((task) => task.job_id === jobId);
}

function activeTask(jobId: number): ScreeningTask | undefined {
  return jobTasks(jobId).find((task) => ["ready", "running", "pausing", "paused", "cancelling"].includes(task.status));
}

function screenedCount(jobId: number): number {
  return jobTasks(jobId).reduce((sum, task) => sum + task.processed_count, 0);
}

function taskStatusLabel(value: string): string {
  return ({ ready: "等待领取", running: "执行中", pausing: "正在暂停", paused: "已暂停", cancelling: "正在停止", completed: "已完成", cancelled: "已取消", failed: "失败" } as Record<string, string>)[value] ?? value;
}

function formatTaskTime(value: string | null): string {
  if (!value) return "尚未运行";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

async function loadJobStats(job: Job): Promise<void> {
  const requestId = (statsRequestIds.get(job.id) ?? 0) + 1;
  statsRequestIds.set(job.id, requestId);
  statsLoadingIds.value = new Set(statsLoadingIds.value).add(job.id);
  const [candidateResult, resumeResult] = await Promise.allSettled([
    listCandidates("", { jobId: job.id }),
    listResumes({ jobId: job.id }),
  ]);
  if (statsRequestIds.get(job.id) !== requestId) return;
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
  statsErrors.value = { ...statsErrors.value, [job.id]: errors };
  const loadingIds = new Set(statsLoadingIds.value);
  loadingIds.delete(job.id);
  statsLoadingIds.value = loadingIds;
}

async function loadStats(jobRows: Job[]): Promise<void> {
  await Promise.all(jobRows.map((job) => loadJobStats(job)));
}

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  tasksError.value = "";
  const jobsRequest = ++jobsRequestId;
  const requestId = ++tasksRequestId;
  const [jobResult, taskResult] = await Promise.allSettled([listJobs(), listScreeningTasks()]);
  if (jobsRequest === jobsRequestId) {
    if (jobResult.status === "fulfilled") {
      jobs.value = jobResult.value;
      if (props.targetJobId === 0 && props.editTarget) {
        openCreate();
      } else {
        const target = props.targetJobId == null ? null : jobResult.value.find((job) => job.id === props.targetJobId);
        if (target) {
          openDetail(target);
          if (props.editTarget) openEdit();
        }
      }
      await loadStats(jobResult.value);
    } else {
      const message = jobResult.reason instanceof Error ? jobResult.reason.message : String(jobResult.reason);
      loadError.value = `加载岗位失败：${message}`;
    }
  }
  if (requestId === tasksRequestId) {
    if (taskResult.status === "fulfilled") {
      tasks.value = taskResult.value;
    } else {
      const message = taskResult.reason instanceof Error ? taskResult.reason.message : String(taskResult.reason);
      tasksError.value = `任务历史加载失败：${message}`;
    }
    loading.value = false;
  }
}

function resetForm(job?: Job): void {
  form.name = job?.name ?? "";
  form.jd_text = job?.jd_text ?? "";
  form.score_threshold = job?.score_threshold ?? 80;
  form.greet_template = job?.greet_template ?? "您好，看了您的经历很匹配，方便发一下附件简历吗？";
  form.boss_entry_url = job?.boss_entry_url ?? "";
  form.hourly_greet_limit = job?.hourly_greet_limit ?? 20;
  form.min_action_delay_ms = job?.min_action_delay_ms ?? 1500;
  form.max_action_delay_ms = job?.max_action_delay_ms ?? 4000;
  form.default_requested_count = job?.default_requested_count ?? 20;
  saveError.value = "";
}

function openCreate(): void {
  editingJob.value = null;
  resetForm();
  formOpen.value = true;
}

function openEdit(): void {
  if (!detailJob.value) return;
  editingJob.value = detailJob.value;
  resetForm(detailJob.value);
  detailJob.value = null;
  formOpen.value = true;
}

function replaceJob(updated: Job): void {
  const index = jobs.value.findIndex((job) => job.id === updated.id);
  if (index === -1) jobs.value.unshift(updated);
  else jobs.value[index] = updated;
  if (detailJob.value?.id === updated.id) detailJob.value = updated;
}

async function save(): Promise<void> {
  if (saving.value) return;
  saving.value = true;
  saveError.value = "";
  const payload: JobWrite = {
    name: form.name.trim(),
    jd_text: form.jd_text.trim(),
    score_threshold: Number(form.score_threshold),
    greet_template: form.greet_template.trim(),
    boss_entry_url: form.boss_entry_url.trim(),
    hourly_greet_limit: Number(form.hourly_greet_limit),
    min_action_delay_ms: Number(form.min_action_delay_ms),
    max_action_delay_ms: Number(form.max_action_delay_ms),
    default_requested_count: form.default_requested_count === null ? null : Number(form.default_requested_count),
  };
  try {
    const saved = editingJob.value
      ? await updateJob(editingJob.value.id, payload)
      : await createJob(payload);
    jobsRequestId += 1;
    replaceJob(saved);
    formOpen.value = false;
    editingJob.value = null;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    saveError.value = `保存岗位失败：${message}`;
  } finally {
    saving.value = false;
  }
}

async function toggleJob(job: Job): Promise<void> {
  if (togglingId.value !== null) return;
  togglingId.value = job.id;
  actionError.value = "";
  try {
    replaceJob(await updateJob(job.id, { enabled: !job.enabled }));
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    actionError.value = `更新岗位状态失败：${message}`;
  } finally {
    togglingId.value = null;
  }
}

async function refreshOperationalData(): Promise<void> {
  const requestId = ++tasksRequestId;
  try {
    const taskRows = await listScreeningTasks();
    if (requestId !== tasksRequestId) return;
    tasks.value = taskRows;
    tasksError.value = "";
    await loadStats(jobs.value);
  } catch (err) {
    if (requestId !== tasksRequestId) return;
    const message = err instanceof Error ? err.message : String(err);
    tasksError.value = `任务状态同步失败：${message}`;
  }
}

onMounted(() => {
  operationalPollBusy = true;
  void load().finally(() => {
    operationalPollBusy = false;
  });
  taskPollTimer = setInterval(() => {
    if (operationalPollBusy) return;
    operationalPollBusy = true;
    void refreshOperationalData().finally(() => {
      operationalPollBusy = false;
    });
  }, 5000);
});

onUnmounted(() => {
  if (taskPollTimer !== null) clearInterval(taskPollTimer);
  taskPollTimer = null;
});
</script>

<template>
  <section class="page-section jobs-page" data-testid="jobs-page" data-page-panel>
    <header class="page-heading">
      <div>
        <p class="eyebrow">RECRUITING CONTROL</p>
        <h1>JOB MISSIONS.</h1>
        <p class="muted">管理真实招聘岗位、筛选规则和招呼话术。</p>
      </div>
      <button type="button" aria-label="新建岗位" @click="openCreate">新建岗位</button>
    </header>

    <section class="jobs-stats" aria-label="岗位统计">
      <article data-testid="jobs-total"><span>全部岗位</span><strong>{{ jobs.length }}</strong></article>
      <article data-testid="jobs-running"><span>招聘中</span><strong>{{ runningJobs }}</strong></article>
      <article data-testid="jobs-candidates"><span>筛选记录</span><strong>{{ totalScreened }}</strong><small>按任务已处理人数累计</small></article>
    </section>

    <div class="panel filter-bar jobs-toolbar">
      <label>
        搜索
        <input v-model="query" aria-label="搜索岗位名称" placeholder="输入岗位名称" />
      </label>
      <label>
        状态
        <select v-model="status" aria-label="筛选岗位状态">
          <option value="all">全部</option>
          <option value="enabled">招聘中</option>
          <option value="disabled">已停用</option>
        </select>
      </label>
    </div>

    <p v-if="actionError" class="panel error" role="alert">{{ actionError }}</p>
    <section v-if="tasksError" class="panel error" data-testid="tasks-sync-error" role="alert">
      <p>{{ tasksError }}</p>
      <button type="button" class="secondary" aria-label="重试任务状态" @click="refreshOperationalData">重试任务状态</button>
    </section>
    <p v-if="loading" aria-live="polite">正在加载岗位…</p>
    <section v-else-if="loadError" class="panel">
      <p class="error" role="alert">{{ loadError }}</p>
      <button type="button" aria-label="重试加载岗位" @click="load">重试</button>
    </section>
    <EmptyState v-else-if="jobs.length === 0" title="暂无岗位" description="新建第一个岗位后，可在这里统一管理招聘要求。" />
    <EmptyState v-else-if="filteredJobs.length === 0" title="没有匹配的岗位" description="请调整搜索词或状态筛选。" />
    <div v-else class="job-grid job-card-grid">
      <article v-for="job in filteredJobs" :key="job.id" class="panel job-card">
        <div class="job-card-top">
          <StatusBadge
            :label="activeTask(job.id) ? `活动任务：${taskStatusLabel(activeTask(job.id)!.status)}` : job.enabled ? '招聘中' : '已停用'"
            :tone="activeTask(job.id) ? 'warning' : job.enabled ? 'success' : 'neutral'"
          />
          <span class="job-card-id">MISSION {{ String(job.id).padStart(2, "0") }}</span>
        </div>
        <h2>{{ job.name }}</h2>
        <p class="job-summary">{{ job.jd_text }}</p>
        <dl class="job-card-facts">
          <div><dt>候选人数</dt><dd :data-testid="`job-candidate-count-${job.id}`">{{ candidateCounts[job.id] ?? "—" }}</dd></div>
          <div><dt>简历数</dt><dd :data-testid="`job-resume-count-${job.id}`">{{ resumeCounts[job.id] ?? "—" }}</dd></div>
          <div><dt>筛选记录</dt><dd>{{ screenedCount(job.id) }}</dd></div>
          <div><dt>AI 阈值</dt><dd>{{ job.score_threshold }} 分</dd></div>
          <div><dt>最近运行</dt><dd>{{ formatTaskTime(jobTasks(job.id)[0]?.started_at ?? jobTasks(job.id)[0]?.created_at ?? null) }}</dd></div>
        </dl>
        <div v-if="statsErrors[job.id]?.length" :data-testid="`job-stats-error-${job.id}`" class="error" role="alert">
          <p>{{ statsErrors[job.id].join("；") }}</p>
          <button type="button" class="secondary" :aria-label="`重试${job.name}统计`" :disabled="statsLoadingIds.has(job.id)" @click="loadJobStats(job)">
            {{ statsLoadingIds.has(job.id) ? "重试中…" : "重试统计" }}
          </button>
        </div>
        <div class="job-card-actions">
          <button type="button" class="secondary" :aria-label="`查看${job.name}详情`" @click="openDetail(job)">查看详情</button>
          <button type="button" :class="job.enabled ? 'danger' : 'secondary'" :aria-label="`${job.enabled ? '停用' : '启用'}${job.name}`" :disabled="togglingId !== null" @click="toggleJob(job)">
            {{ togglingId === job.id ? "正在更新…" : job.enabled ? "停用岗位" : "启用岗位" }}
          </button>
        </div>
      </article>
    </div>

    <AppDrawer :open="Boolean(detailJob)" :title="detailJob?.name ?? '岗位详情'" @close="closeDetail">
      <template v-if="detailJob">
        <StatusBadge :label="detailJob.enabled ? '招聘中' : '已停用'" :tone="detailJob.enabled ? 'success' : 'neutral'" />
        <section class="drawer-section"><p class="eyebrow">JOB DESCRIPTION</p><p>{{ detailJob.jd_text }}</p></section>
        <section class="drawer-section">
          <p class="eyebrow">LAUNCH CONFIGURATION</p>
          <p>BOSS 岗位入口：{{ detailJob.boss_entry_url || "未配置" }}</p>
          <p>招呼限速：每小时 {{ detailJob.hourly_greet_limit }} 次</p>
          <p>操作间隔：{{ detailJob.min_action_delay_ms }}–{{ detailJob.max_action_delay_ms }} 毫秒</p>
          <p>默认筛选 {{ detailJob.default_requested_count ?? "未配置" }} 人</p>
        </section>
        <section class="drawer-section"><p class="eyebrow">AI SCORE THRESHOLD</p><p>{{ detailJob.score_threshold }} 分</p></section>
        <section class="drawer-section">
          <p class="eyebrow">GREETING</p>
          <p>{{ detailJob.greet_template }}</p>
          <p class="muted">允许的模板变量：<code v-pre>{{candidate_name}}</code>、<code v-pre>{{job_name}}</code>。其他变量会被服务端拒绝。</p>
        </section>
        <section class="drawer-section"><p class="eyebrow">TASK STATUS</p><p>{{ activeTask(detailJob.id) ? `活动任务：${taskStatusLabel(activeTask(detailJob.id)!.status)}` : detailJob.enabled ? "招聘中，暂无活动任务" : "已停用" }}</p></section>
        <section class="drawer-section">
          <p class="eyebrow">TASK HISTORY</p>
          <p v-if="jobTasks(detailJob.id).length === 0" class="muted">暂无任务历史。</p>
          <article v-for="task in jobTasks(detailJob.id)" :key="task.id" class="task-history-item">
            <strong>任务 #{{ task.id }} · {{ taskStatusLabel(task.status) }}</strong>
            <p>已处理 {{ task.processed_count }} / {{ task.requested_count }}；达标 {{ task.eligible_count }}；已联系 {{ task.contacted_count }}；待复核 {{ task.review_count }}</p>
            <small>{{ formatTaskTime(task.started_at ?? task.created_at) }}</small>
          </article>
        </section>
        <button type="button" aria-label="编辑当前岗位" @click="openEdit">编辑岗位</button>
      </template>
    </AppDrawer>

    <AppDrawer :open="formOpen" :title="editingJob ? '编辑岗位' : '新建岗位'" @close="formOpen = false">
      <form class="form-stack" @submit.prevent="save">
        <label>岗位名称<input v-model="form.name" aria-label="岗位名称" required /></label>
        <label>职位描述<textarea v-model="form.jd_text" aria-label="职位描述" rows="8" required></textarea></label>
        <label>匹配分数阈值<input v-model.number="form.score_threshold" aria-label="匹配分数阈值" type="number" min="0" max="100" required /></label>
        <label>招呼话术<textarea v-model="form.greet_template" aria-label="招呼话术" rows="4" required></textarea></label>
        <label>BOSS 岗位入口<input v-model="form.boss_entry_url" aria-label="BOSS 岗位入口" type="url" placeholder="https://www.zhipin.com/..." /></label>
        <label>每小时招呼上限<input v-model.number="form.hourly_greet_limit" aria-label="每小时招呼上限" type="number" min="1" required /></label>
        <label>最小操作间隔（毫秒）<input v-model.number="form.min_action_delay_ms" aria-label="最小操作间隔" type="number" min="0" required /></label>
        <label>最大操作间隔（毫秒）<input v-model.number="form.max_action_delay_ms" aria-label="最大操作间隔" type="number" min="0" required /></label>
        <label>默认筛选人数<input v-model.number="form.default_requested_count" aria-label="默认筛选人数" type="number" min="1" max="50" required /></label>
        <p class="muted">学历、经验、技能及其他筛选要求请直接写入职位描述，AI 将依据完整 JD 评分。</p>
        <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
        <button type="submit" aria-label="保存岗位" :disabled="saving">{{ saving ? "正在保存…" : "保存岗位" }}</button>
      </form>
    </AppDrawer>
  </section>
</template>
