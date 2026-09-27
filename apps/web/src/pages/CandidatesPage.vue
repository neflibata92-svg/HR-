<script setup lang="ts">
import { onMounted, ref } from "vue";

import {
  ApiError,
  downloadResumeFile,
  listCandidateJobs,
  listCandidateResumes,
  listCandidates,
  listJobs,
  listReviews,
  markExchange,
  mergeCandidates,
  previewCandidateMerge,
  reEvaluateCandidateJob,
  reviewCandidateJob,
  revertCandidateMerge,
  type Candidate,
  type CandidateJob,
  type CandidateMerge,
  type CandidateMergePayload,
  type CandidateMergePreview,
  type Job,
  type MergeConflict,
  type Resume,
  type ReviewItem,
  type UserMe,
} from "../api";
import AppDrawer from "../components/AppDrawer.vue";
import EmptyState from "../components/EmptyState.vue";

const props = defineProps<{ user: UserMe }>();

const candidates = ref<Candidate[]>([]);
const jobs = ref<Job[]>([]);
const query = ref("");
const selectedJobId = ref("");
const selectedStatus = ref("");
const minimumScore = ref("");
const needsReview = ref(false);
const loading = ref(true);
const loadError = ref("");
const actionError = ref("");
const selected = ref<Candidate | null>(null);
const candidateJobs = ref<CandidateJob[]>([]);
const candidateResumes = ref<Resume[]>([]);
const detailLoading = ref(false);
const detailError = ref("");
const markingId = ref<number | null>(null);
const reviews = ref<ReviewItem[]>([]);
const reviewBusyId = ref<number | null>(null);
const feedback = ref("");
const showMerge = ref(false);
const mergeTargetId = ref("");
const mergeChoices = ref<Record<string, "source" | "target">>({
  name: "target",
  phone_normalized: "target",
  email_normalized: "target",
  age: "target",
  years_of_experience: "target",
  source: "target",
});
const mergePreview = ref<CandidateMergePreview | null>(null);
const previewedMergePayload = ref<CandidateMergePayload | null>(null);
let mergePreviewRequestId = 0;
const lastMerge = ref<CandidateMerge | null>(null);
const mergeError = ref("");
const mergeBusy = ref(false);
const mergeFields = [
  { key: "name", label: "姓名" },
  { key: "phone_normalized", label: "手机号" },
  { key: "email_normalized", label: "邮箱" },
  { key: "age", label: "年龄" },
  { key: "years_of_experience", label: "工作经验" },
  { key: "source", label: "来源" },
] as const;

function canMerge(): boolean {
  return props.user.role === "admin" || props.user.role === "lead";
}

function mergePayload(): CandidateMergePayload | null {
  if (!selected.value || !mergeTargetId.value) return null;
  return {
    source_candidate_id: selected.value.id,
    target_candidate_id: Number(mergeTargetId.value),
    field_choices: { ...mergeChoices.value },
  };
}

function conflictsFrom(error: unknown): MergeConflict[] {
  if (!(error instanceof ApiError) || typeof error.detail !== "object" || error.detail === null) return [];
  const conflicts = (error.detail as { conflicts?: unknown }).conflicts;
  return Array.isArray(conflicts) ? conflicts as MergeConflict[] : [];
}

async function previewMerge(): Promise<void> {
  const payload = mergePayload();
  if (!payload || mergeBusy.value) return;
  const requestId = ++mergePreviewRequestId;
  const immutablePayload: CandidateMergePayload = {
    ...payload,
    field_choices: { ...payload.field_choices },
  };
  mergeBusy.value = true;
  mergeError.value = "";
  mergePreview.value = null;
  previewedMergePayload.value = null;
  try {
    const preview = await previewCandidateMerge(immutablePayload);
    if (requestId !== mergePreviewRequestId) return;
    mergePreview.value = preview;
    previewedMergePayload.value = immutablePayload;
  } catch (err) {
    if (requestId !== mergePreviewRequestId) return;
    const conflicts = conflictsFrom(err);
    mergeError.value = conflicts.length
      ? conflicts.map((conflict) => conflict.reason).join("；")
      : `合并预览失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    if (requestId === mergePreviewRequestId) mergeBusy.value = false;
  }
}

function invalidateMergePreview(): void {
  mergePreviewRequestId += 1;
  mergePreview.value = null;
  previewedMergePayload.value = null;
  mergeBusy.value = false;
}

async function confirmMerge(): Promise<void> {
  const payload = previewedMergePayload.value;
  if (!payload || !mergePreview.value || mergePreview.value.conflicts.length || mergeBusy.value) return;
  mergeBusy.value = true;
  mergeError.value = "";
  try {
    lastMerge.value = await mergeCandidates(payload);
    const mergeId = lastMerge.value.id;
    showMerge.value = false;
    selected.value = null;
    const refreshed = await load();
    feedback.value = refreshed
      ? `合并 #${mergeId} 已完成`
      : `合并 #${mergeId} 已完成，但列表刷新失败，请重试刷新后再继续操作`;
  } catch (err) {
    const conflicts = conflictsFrom(err);
    mergeError.value = conflicts.length
      ? conflicts.map((conflict) => conflict.reason).join("；")
      : `合并失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    mergeBusy.value = false;
  }
}

async function revertLastMerge(): Promise<void> {
  if (!lastMerge.value || mergeBusy.value) return;
  const mergeId = lastMerge.value.id;
  mergeBusy.value = true;
  mergeError.value = "";
  try {
    await revertCandidateMerge(mergeId);
    const refreshed = await load();
    if (refreshed) lastMerge.value = null;
    feedback.value = refreshed
      ? `合并 #${mergeId} 已撤销`
      : `合并 #${mergeId} 已撤销，但列表刷新失败，请重试刷新后再继续操作`;
  } catch (err) {
    const conflicts = conflictsFrom(err);
    mergeError.value = conflicts.length
      ? conflicts.map((conflict) => conflict.reason).join("；")
      : `撤销合并失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    mergeBusy.value = false;
  }
}

async function load(): Promise<boolean> {
  loading.value = true;
  loadError.value = "";
  actionError.value = "";
  feedback.value = "";
  try {
    const filters = {
      jobId: selectedJobId.value ? Number(selectedJobId.value) : undefined,
      status: selectedStatus.value || undefined,
      minScore: minimumScore.value ? Number(minimumScore.value) : undefined,
      needsReview: needsReview.value || undefined,
    };
    const hasFilters = Object.values(filters).some((value) => value !== undefined);
    const [candidateRows, reviewRows] = await Promise.all([
      hasFilters
        ? listCandidates(query.value.trim(), filters)
        : listCandidates(query.value.trim()),
      needsReview.value ? listReviews(filters.jobId) : Promise.resolve([]),
    ]);
    candidates.value = candidateRows;
    reviews.value = reviewRows;
    return true;
  } catch (err) {
    candidates.value = [];
    const message = err instanceof Error ? err.message : String(err);
    loadError.value = `加载候选人失败：${message}`;
    return false;
  } finally {
    loading.value = false;
  }
}

async function loadJobs(): Promise<void> {
  try {
    jobs.value = await listJobs();
  } catch {
    jobs.value = [];
  }
}

async function openCandidate(candidate: Candidate): Promise<void> {
  selected.value = candidate;
  showMerge.value = false;
  mergeTargetId.value = "";
  invalidateMergePreview();
  mergeError.value = "";
  candidateJobs.value = [];
  candidateResumes.value = [];
  detailError.value = "";
  detailLoading.value = true;
  try {
    const [jobLinks, resumes] = await Promise.all([
      listCandidateJobs(candidate.id),
      listCandidateResumes(candidate.id),
    ]);
    candidateJobs.value = jobLinks;
    candidateResumes.value = resumes;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    detailError.value = `候选人详情加载失败：${message}`;
  } finally {
    detailLoading.value = false;
  }
}

function selectedReviews(): ReviewItem[] {
  return selected.value ? reviews.value.filter((item) => item.candidate.id === selected.value?.id) : [];
}

function removePendingReview(item: ReviewItem): void {
  reviews.value = reviews.value.filter((row) => row.candidate_job_id !== item.candidate_job_id);
  if (!reviews.value.some((row) => row.candidate.id === item.candidate.id)) {
    candidates.value = candidates.value.filter((row) => row.id !== item.candidate.id);
  }
}

async function openResumeFile(resume: Resume): Promise<void> {
  actionError.value = "";
  try {
    const blob = await downloadResumeFile(resume.id);
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  } catch (err) {
    actionError.value = `查看简历失败：${err instanceof Error ? err.message : String(err)}`;
  }
}

async function actOnReview(item: ReviewItem, action: "keep_pending" | "archive"): Promise<void> {
  if (reviewBusyId.value !== null) return;
  reviewBusyId.value = item.candidate_job_id;
  actionError.value = "";
  feedback.value = "";
  try {
    await reviewCandidateJob(item.candidate_job_id, action);
    if (action === "archive") {
      removePendingReview(item);
      if (!reviews.value.some((row) => row.candidate.id === item.candidate.id)) {
        selected.value = null;
      }
      feedback.value = `已归档${item.candidate.name}在${item.job.name}的待复核记录`;
    } else {
      feedback.value = `${item.candidate.name}继续保持待复核`;
    }
  } catch (err) {
    actionError.value = `复核操作失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    reviewBusyId.value = null;
  }
}

async function reEvaluateReview(item: ReviewItem): Promise<void> {
  const link = candidateJobs.value.find((row) => row.id === item.candidate_job_id);
  const job = jobs.value.find((row) => row.id === item.job.id);
  if (!link?.active_resume_id || reviewBusyId.value !== null) return;
  reviewBusyId.value = item.candidate_job_id;
  actionError.value = "";
  feedback.value = "";
  try {
    const score = await reEvaluateCandidateJob(item.candidate.id, item.job.id, link.active_resume_id);
    if (score.decision !== "needs_review") {
      removePendingReview(item);
      feedback.value = `${item.candidate.name}已退出待复核队列；不会自动恢复旧任务发送`;
      return;
    }
    reviews.value = reviews.value.map((row) => row.candidate_job_id === item.candidate_job_id ? {
      ...row,
      score: score.score,
      reason: score.reason,
      confidence: score.confidence,
      missing_critical_fields: score.missing_fields,
      estimated_fields: score.estimated_fields,
      evidence: score.evidence,
      model: score.model,
      scored_at: score.created_at,
    } : row);
    feedback.value = `已重新评估${item.candidate.name}；仍需人工复核，不会自动恢复旧任务发送`;
  } catch (err) {
    actionError.value = `重新评估失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    reviewBusyId.value = null;
  }
}

async function recordExchange(candidate: Candidate): Promise<void> {
  if (markingId.value !== null) return;
  markingId.value = candidate.id;
  actionError.value = "";
  feedback.value = "";
  try {
    await markExchange(candidate.id, props.user.username);
    feedback.value = `已记录${candidate.name}的简历交换`;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    actionError.value = `记录交换失败：${message}`;
  } finally {
    markingId.value = null;
  }
}

onMounted(() => {
  void load();
  void loadJobs();
});
</script>

<template>
  <section class="page-section candidates-page" data-testid="candidates-page" data-page-panel>
    <header class="page-heading">
      <div>
        <p class="eyebrow">TALENT DISCOVERY</p>
        <h1>HUMAN POTENTIAL.</h1>
        <p class="muted">查询真实候选人基础资料并记录简历交换。</p>
      </div>
    </header>

    <section class="candidate-stats" aria-label="候选人统计">
      <article data-testid="candidate-total"><span>候选人总数</span><strong>{{ candidates.length }}</strong></article>
      <article data-testid="candidate-high-score"><span>高分人才</span><strong>—</strong><small>暂未接入</small></article>
      <article data-testid="candidate-contacted"><span>已联系</span><strong>—</strong><small>暂未接入</small></article>
      <article data-testid="candidate-resume"><span>收到简历</span><strong>—</strong><small>暂未接入</small></article>
    </section>

    <form class="panel candidate-toolbar" @submit.prevent="load">
      <label>
        姓名或 BOSS ID
        <input v-model="query" aria-label="搜索候选人" placeholder="输入姓名或 BOSS ID" />
      </label>
      <label>
        岗位
        <select v-model="selectedJobId" aria-label="筛选候选人岗位">
          <option value="">全部岗位</option>
          <option v-for="job in jobs" :key="job.id" :value="String(job.id)">{{ job.name }}</option>
        </select>
      </label>
      <label>
        处理状态
        <select v-model="selectedStatus" aria-label="筛选处理状态">
          <option value="">全部状态</option>
          <option value="pending">待处理</option>
          <option value="needs_review">待复核</option>
          <option value="eligible">达标</option>
          <option value="contacted">已联系</option>
          <option value="archived">已归档</option>
        </select>
      </label>
      <label>
        AI 最低分
        <input v-model="minimumScore" aria-label="筛选 AI 分数" type="number" min="0" max="100" placeholder="不限" />
      </label>
      <label class="check-row">
        <input v-model="needsReview" aria-label="筛选待复核候选人" type="checkbox" />
        仅看待复核
      </label>
      <button type="submit" :disabled="loading">搜索</button>
    </form>

    <p v-if="loading" aria-live="polite">正在加载候选人…</p>
    <section v-else-if="loadError" class="panel">
      <p class="error" role="alert">{{ loadError }}</p>
      <button type="button" aria-label="重试加载候选人" @click="load">重试</button>
    </section>
    <p v-if="feedback" class="panel success-message" aria-live="polite">{{ feedback }}</p>
    <p v-if="actionError" class="panel error" role="alert">{{ actionError }}</p>
    <section v-if="lastMerge" class="panel">
      <p>合并 #{{ lastMerge.id }} 已完成。只能撤销本次会话刚完成的合并；服务端暂未提供历史合并查询。</p>
      <button type="button" class="danger" aria-label="撤销刚完成的候选人合并" :disabled="mergeBusy" @click="revertLastMerge">
        {{ mergeBusy ? "正在撤销…" : "撤销刚完成的合并" }}
      </button>
      <p v-if="mergeError" class="error" role="alert">{{ mergeError }}</p>
    </section>

    <EmptyState v-if="!loading && !loadError && candidates.length === 0" title="暂无候选人" description="当前条件下没有查询到候选人。" />
    <div v-else-if="!loading && !loadError" class="candidate-list">
      <article v-for="candidate in candidates" :key="candidate.id" class="panel candidate-card candidate-row">
        <div class="candidate-identity">
          <span class="candidate-avatar">{{ (candidate.name || '?').slice(0, 1) }}</span>
          <div><h2>{{ candidate.name || "未命名候选人" }}</h2><p class="muted">BOSS ID：{{ candidate.boss_id || "未提供" }}</p></div>
        </div>
        <div><small>基础资料</small><p>{{ candidate.age ?? "年龄未知" }}<template v-if="candidate.age !== null"> 岁</template> · {{ candidate.years_of_experience ?? "经验未知" }}<template v-if="candidate.years_of_experience !== null"> 年经验</template></p></div>
        <div><small>来源</small><p>{{ candidate.source }}</p></div>
        <div><small>AI 评估</small><p>— · 暂未接入</p></div>
        <div class="candidate-actions">
          <button type="button" class="secondary" :aria-label="`查看${candidate.name}详情`" @click="openCandidate(candidate)">查看详情</button>
          <button type="button" :aria-label="`标记${candidate.name}已交换简历`" :disabled="markingId !== null" @click="recordExchange(candidate)">
            {{ markingId === candidate.id ? "正在记录…" : "标记已交换简历" }}
          </button>
        </div>
      </article>
    </div>

    <AppDrawer :open="Boolean(selected)" :title="selected?.name || '候选人详情'" @close="selected = null">
      <template v-if="selected">
        <section v-if="canMerge()" class="drawer-section">
          <p class="eyebrow">CANDIDATE MERGE</p>
          <button type="button" :aria-label="`合并${selected.name}候选人`" @click="showMerge = !showMerge">
            {{ showMerge ? "收起合并" : "合并候选人" }}
          </button>
          <div v-if="showMerge" class="form-stack">
            <label>
              合并到主候选人
              <select v-model="mergeTargetId" aria-label="合并目标候选人" @change="invalidateMergePreview">
                <option value="">请选择不同的目标候选人</option>
                <option v-for="candidate in candidates.filter((row) => row.id !== selected?.id)" :key="candidate.id" :value="String(candidate.id)">
                  {{ candidate.name }} · {{ candidate.boss_id || `候选人 #${candidate.id}` }}
                </option>
              </select>
            </label>
            <label v-for="field in mergeFields" :key="field.key">
              {{ field.label }}保留来源
              <select v-model="mergeChoices[field.key]" :aria-label="`${field.label}保留来源`" @change="invalidateMergePreview">
                <option value="target">目标候选人</option>
                <option value="source">当前候选人</option>
              </select>
            </label>
            <button type="button" aria-label="预览候选人合并" :disabled="!mergeTargetId || mergeBusy" @click="previewMerge">
              {{ mergeBusy ? "正在处理…" : "预览合并影响" }}
            </button>
            <p v-if="mergeError" class="error" role="alert">{{ mergeError }}</p>
            <template v-if="mergePreview">
              <p><strong>迁移数量：</strong>{{ Object.entries(mergePreview.moved_counts).map(([key, count]) => `${key} ${count}`).join("；") || "无" }}</p>
              <p><strong>合并后字段：</strong>{{ Object.entries(mergePreview.merged_fields).map(([key, value]) => `${key}=${value ?? "空"}`).join("；") }}</p>
              <ul v-if="mergePreview.conflicts.length" class="error">
                <li v-for="(conflict, index) in mergePreview.conflicts" :key="`${conflict.entity_type}-${conflict.entity_id}-${index}`">
                  {{ conflict.entity_type }} #{{ conflict.entity_id ?? "未知" }}：{{ conflict.reason }}
                </li>
              </ul>
              <button
                type="button"
                class="danger"
                aria-label="确认执行候选人合并"
                :disabled="mergeBusy || mergePreview.conflicts.length > 0"
                @click="confirmMerge"
              >确认执行合并</button>
            </template>
          </div>
        </section>
        <section v-for="review in selectedReviews()" :key="review.candidate_job_id" class="drawer-section review-section">
          <p class="eyebrow">PENDING REVIEW</p>
          <h3>{{ review.job.name }} · 待复核</h3>
          <p><strong>评分：</strong>{{ review.score ?? "无评分" }} / 门槛 {{ review.threshold }}</p>
          <p><strong>评分原因：</strong>{{ review.reason || "暂无说明" }}</p>
          <p><strong>资料未提及：</strong>{{ review.missing_critical_fields.join("、") || "无" }}</p>
          <p><strong>普通估算：</strong>{{ review.estimated_fields.join("、") || "无" }}</p>
          <p><strong>证据：</strong>{{ review.evidence.join("；") || "无" }}</p>
          <p class="muted">模型：{{ review.model || "未知" }}。重新评估将使用岗位当前 JD 与当前简历。</p>
          <div class="row">
            <button type="button" :aria-label="`重新评估${selected.name}`" :disabled="reviewBusyId !== null || !candidateJobs.find((row) => row.id === review.candidate_job_id)?.active_resume_id" @click="reEvaluateReview(review)">重新评估</button>
            <button type="button" class="secondary" :aria-label="`继续待定${selected.name}`" :disabled="reviewBusyId !== null" @click="actOnReview(review, 'keep_pending')">继续待定</button>
            <button type="button" class="danger" :aria-label="`归档${selected.name}`" :disabled="reviewBusyId !== null" @click="actOnReview(review, 'archive')">归档</button>
          </div>
        </section>
        <dl class="detail-list">
          <div><dt>BOSS ID</dt><dd>{{ selected.boss_id || "未提供" }}</dd></div>
          <div><dt>年龄</dt><dd>{{ selected.age === null ? "未提供" : `${selected.age} 岁` }}</dd></div>
          <div><dt>工作经验</dt><dd>{{ selected.years_of_experience === null ? "未提供" : `${selected.years_of_experience} 年经验` }}</dd></div>
          <div><dt>来源</dt><dd>{{ selected.source }}</dd></div>
          <div><dt>录入时间</dt><dd>{{ selected.created_at || "未提供" }}</dd></div>
        </dl>
        <section class="drawer-section">
          <p class="eyebrow">JOB LINKS</p>
          <p v-if="detailLoading">正在加载岗位关联…</p>
          <p v-else-if="detailError" class="error" role="alert">{{ detailError }}</p>
          <ul v-else-if="candidateJobs.length">
            <li v-for="link in candidateJobs" :key="link.id">
              岗位 #{{ link.job_id }} · {{ link.status }} · 当前简历 #{{ link.active_resume_id ?? "未设置" }}
            </li>
          </ul>
          <p v-else>暂无岗位关联。</p>
        </section>
        <section class="drawer-section">
          <p class="eyebrow">RESUME VERSIONS</p>
          <ul v-if="candidateResumes.length">
            <li v-for="resume in candidateResumes" :key="resume.id">
              {{ resume.original_filename || `简历 #${resume.id}` }} · 版本 {{ resume.version_number ?? "未知" }} · {{ resume.parse_status }}
              <button type="button" class="secondary" :aria-label="`查看简历${resume.original_filename || resume.id}`" @click="openResumeFile(resume)">查看 PDF</button>
            </li>
          </ul>
          <p v-else-if="!detailLoading">暂无简历版本。</p>
        </section>
        <section class="drawer-section"><p class="eyebrow">EXPERIENCE</p><p>{{ selected.years_of_experience === null ? "经历详情暂未接入" : `${selected.years_of_experience} 年工作经验；经历详情暂未接入` }}</p></section>
        <section class="drawer-section"><p class="eyebrow">MATCH EVIDENCE</p><p class="muted">匹配证据暂未接入</p></section>
        <section class="drawer-section"><p class="eyebrow">RISK NOTE</p><p class="muted">风险提示暂未接入</p></section>
        <section class="drawer-section"><p class="eyebrow">ACTIVITY</p><p class="muted">活动时间线暂未接入</p></section>
        <p class="muted">AI 分数、匹配证据、风险和时间线详情接口暂未提供；评分证据与活动时间线读取接口暂未提供。</p>
        <button type="button" :aria-label="`查看${selected.name}简历`" :disabled="candidateResumes.length === 0">
          {{ candidateResumes.length ? `已加载 ${candidateResumes.length} 个简历版本` : "查看简历 · 暂无记录" }}
        </button>
      </template>
    </AppDrawer>
  </section>
</template>
