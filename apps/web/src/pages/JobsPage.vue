<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { createJob, listJobs, updateJob, type Job, type JobWrite } from "../api";
import AppDrawer from "../components/AppDrawer.vue";
import EmptyState from "../components/EmptyState.vue";
import StatusBadge from "../components/StatusBadge.vue";

const jobs = ref<Job[]>([]);
const loading = ref(true);
const loadError = ref("");
const query = ref("");
const status = ref("all");
const detailJob = ref<Job | null>(null);
const formOpen = ref(false);
const editingJob = ref<Job | null>(null);
const saving = ref(false);
const togglingId = ref<number | null>(null);
const saveError = ref("");
const actionError = ref("");

const form = reactive<JobWrite>({
  name: "",
  jd_text: "",
  score_threshold: 80,
  greet_template: "您好，看了您的经历很匹配，方便发一下附件简历吗？",
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

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    jobs.value = await listJobs();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    loadError.value = `加载岗位失败：${message}`;
  } finally {
    loading.value = false;
  }
}

function resetForm(job?: Job): void {
  form.name = job?.name ?? "";
  form.jd_text = job?.jd_text ?? "";
  form.score_threshold = job?.score_threshold ?? 80;
  form.greet_template = job?.greet_template ?? "您好，看了您的经历很匹配，方便发一下附件简历吗？";
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
  };
  try {
    const saved = editingJob.value
      ? await updateJob(editingJob.value.id, payload)
      : await createJob(payload);
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

onMounted(() => void load());
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
      <article data-testid="jobs-candidates"><span>候选人数</span><strong>—</strong><small>暂未接入</small></article>
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
          <StatusBadge :label="job.enabled ? '招聘中' : '已停用'" :tone="job.enabled ? 'success' : 'neutral'" />
          <span class="job-card-id">MISSION {{ String(job.id).padStart(2, "0") }}</span>
        </div>
        <h2>{{ job.name }}</h2>
        <p class="job-summary">{{ job.jd_text }}</p>
        <dl class="job-card-facts">
          <div><dt>候选人数</dt><dd>—</dd></div>
          <div><dt>AI 阈值</dt><dd>{{ job.score_threshold }} 分</dd></div>
          <div><dt>最近运行</dt><dd>—</dd></div>
        </dl>
        <div class="job-card-actions">
          <button type="button" class="secondary" :aria-label="`查看${job.name}详情`" @click="detailJob = job">查看详情</button>
          <button type="button" :class="job.enabled ? 'danger' : 'secondary'" :aria-label="`${job.enabled ? '停用' : '启用'}${job.name}`" :disabled="togglingId !== null" @click="toggleJob(job)">
            {{ togglingId === job.id ? "正在更新…" : job.enabled ? "停用岗位" : "启用岗位" }}
          </button>
        </div>
      </article>
    </div>

    <AppDrawer :open="Boolean(detailJob)" :title="detailJob?.name ?? '岗位详情'" @close="detailJob = null">
      <template v-if="detailJob">
        <StatusBadge :label="detailJob.enabled ? '招聘中' : '已停用'" :tone="detailJob.enabled ? 'success' : 'neutral'" />
        <section class="drawer-section"><p class="eyebrow">JOB DESCRIPTION</p><p>{{ detailJob.jd_text }}</p></section>
        <section class="drawer-section"><p class="eyebrow">HARD REQUIREMENTS</p><p class="muted">硬性条件暂未接入</p></section>
        <section class="drawer-section"><p class="eyebrow">AI SCORE THRESHOLD</p><p>{{ detailJob.score_threshold }} 分</p></section>
        <section class="drawer-section"><p class="eyebrow">GREETING</p><p>{{ detailJob.greet_template }}</p></section>
        <section class="drawer-section"><p class="eyebrow">TASK STATUS</p><p>{{ detailJob.enabled ? "招聘中" : "已停用" }}</p></section>
        <button type="button" aria-label="编辑当前岗位" @click="openEdit">编辑岗位</button>
      </template>
    </AppDrawer>

    <AppDrawer :open="formOpen" :title="editingJob ? '编辑岗位' : '新建岗位'" @close="formOpen = false">
      <form class="form-stack" @submit.prevent="save">
        <label>岗位名称<input v-model="form.name" aria-label="岗位名称" required /></label>
        <label>职位描述<textarea v-model="form.jd_text" aria-label="职位描述" rows="8" required></textarea></label>
        <label>匹配分数阈值<input v-model.number="form.score_threshold" aria-label="匹配分数阈值" type="number" min="0" max="100" required /></label>
        <label>招呼话术<textarea v-model="form.greet_template" aria-label="招呼话术" rows="4" required></textarea></label>
        <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
        <button type="submit" aria-label="保存岗位" :disabled="saving">{{ saving ? "正在保存…" : "保存岗位" }}</button>
      </form>
    </AppDrawer>
  </section>
</template>
