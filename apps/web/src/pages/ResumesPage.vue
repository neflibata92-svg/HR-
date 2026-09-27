<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";

import {
  batchImportResumes,
  createJob,
  listCandidateJobs,
  listCandidates,
  listJobs,
  listResumes,
  reEvaluateCandidateJob,
  setActiveResume,
  uploadResume,
  type Candidate,
  type CandidateJob,
  type Job,
  type JobWrite,
  type Resume,
  type ScoreEvent,
} from "../api";
import AppDrawer from "../components/AppDrawer.vue";
import EmptyState from "../components/EmptyState.vue";

const jobs = ref<Job[]>([]);
const candidates = ref<Candidate[]>([]);
const resumes = ref<Resume[]>([]);
const candidateJobByCandidate = ref<Record<number, CandidateJob>>({});
const selectedJobId = ref("");
const selectedCandidateId = ref("");
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const loading = ref(true);
const jobsError = ref("");
const listError = ref("");
const uploadError = ref("");
const versionError = ref("");
const versionFeedback = ref("");
const versionBusyId = ref<number | null>(null);
const latestScore = ref<ScoreEvent | null>(null);
const uploading = ref(false);
const uploadedResume = ref<Resume | null>(null);
const jobFormOpen = ref(false);
const jobSaving = ref(false);
const jobSaveError = ref("");
const jobName = ref("");
const directFiles = ref<File[]>([]);
const directFileInput = ref<HTMLInputElement | null>(null);
const directImportResult = ref<import("../api").ResumeBatchImportResult | null>(null);
const directImporting = ref(false);

function openJobCreate(): void {
  jobName.value = "";
  jobSaveError.value = "";
  jobFormOpen.value = true;
}

let jobsRequestId = 0;
let jobDataRequestId = 0;

async function saveJob(): Promise<void> {
  if (jobSaving.value) return;
  jobSaving.value = true;
  jobSaveError.value = "";
  const payload: JobWrite = {
    name: jobName.value.trim(),
    jd_text: "",
    score_threshold: 80,
    greet_template: "您好，看了您的经历很匹配，方便发一下附件简历吗？",
    boss_entry_url: "",
    hourly_greet_limit: 20,
    min_action_delay_ms: 1500,
    max_action_delay_ms: 4000,
    default_requested_count: null,
    critical_fields: [],
    critical_fields_confirmed: false,
  };
  try {
    const created = await createJob(payload);
    jobsRequestId += 1;
    jobs.value.unshift(created);
    selectedJobId.value = String(created.id);
    jobFormOpen.value = false;
  } catch (err) {
    jobSaveError.value = `创建岗位失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    jobSaving.value = false;
  }
}

async function loadJobs(): Promise<void> {
  const requestId = ++jobsRequestId;
  loading.value = true;
  jobsError.value = "";
  try {
    const jobRows = await listJobs();
    if (requestId !== jobsRequestId) return;
    jobs.value = jobRows;
  } catch (err) {
    if (requestId !== jobsRequestId) return;
    const message = err instanceof Error ? err.message : String(err);
    jobsError.value = `加载岗位失败：${message}`;
  } finally {
    if (requestId === jobsRequestId) loading.value = false;
  }
}

async function loadCandidatesForJob(): Promise<void> {
  const requestId = jobDataRequestId;
  const jobId = selectedJobId.value;
  if (!jobId) {
    candidates.value = [];
    selectedCandidateId.value = "";
    return;
  }
  try {
    const rows = await listCandidates("", { jobId: Number(jobId) });
    if (requestId !== jobDataRequestId || selectedJobId.value !== jobId) return;
    candidates.value = rows;
    if (!rows.some((candidate) => candidate.id === Number(selectedCandidateId.value))) {
      selectedCandidateId.value = "";
    }
  } catch (err) {
    if (requestId !== jobDataRequestId || selectedJobId.value !== jobId) return;
    uploadError.value = `加载岗位候选人失败：${err instanceof Error ? err.message : String(err)}`;
    candidates.value = [];
    selectedCandidateId.value = "";
  }
}

async function loadResumeList(): Promise<void> {
  const requestId = jobDataRequestId;
  const jobId = selectedJobId.value;
  if (!jobId) {
    resumes.value = [];
    candidateJobByCandidate.value = {};
    return;
  }
  listError.value = "";
  try {
    const resumeRows = await listResumes({ jobId: Number(jobId) });
    if (requestId !== jobDataRequestId || selectedJobId.value !== jobId) return;
    const candidateIds = [...new Set(resumeRows.map((resume) => resume.candidate_id).filter((id): id is number => id !== null))];
    const jobRows = await Promise.all(candidateIds.map((candidateId) => listCandidateJobs(candidateId)));
    if (requestId !== jobDataRequestId || selectedJobId.value !== jobId) return;
    resumes.value = resumeRows;
    candidateJobByCandidate.value = Object.fromEntries(
      jobRows.flat()
        .filter((link) => link.job_id === Number(jobId))
        .map((link) => [link.candidate_id, link]),
    );
  } catch (err) {
    if (requestId !== jobDataRequestId || selectedJobId.value !== jobId) return;
    const message = err instanceof Error ? err.message : String(err);
    listError.value = `加载简历列表失败：${message}`;
    resumes.value = [];
    candidateJobByCandidate.value = {};
  }
}

function isActiveResume(resume: Resume): boolean {
  return resume.candidate_id !== null
    && candidateJobByCandidate.value[resume.candidate_id]?.active_resume_id === resume.id;
}

async function activateResume(resume: Resume): Promise<void> {
  if (resume.candidate_id === null || !selectedJobId.value || versionBusyId.value !== null) return;
  const jobId = selectedJobId.value;
  const operationVersion = jobDataRequestId;
  versionBusyId.value = resume.id;
  versionError.value = "";
  versionFeedback.value = "";
  latestScore.value = null;
  try {
    const link = await setActiveResume(resume.candidate_id, Number(jobId), resume.id);
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== jobId) return;
    candidateJobByCandidate.value = { ...candidateJobByCandidate.value, [resume.candidate_id]: link };
    versionFeedback.value = "已切换当前版本，未自动重新评分";
  } catch (err) {
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== jobId) return;
    versionError.value = `切换简历版本失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    if (jobDataRequestId === operationVersion && selectedJobId.value === jobId) versionBusyId.value = null;
  }
}

async function reEvaluate(resume: Resume): Promise<void> {
  if (resume.candidate_id === null || !selectedJobId.value || versionBusyId.value !== null) return;
  const jobId = selectedJobId.value;
  const operationVersion = jobDataRequestId;
  versionBusyId.value = resume.id;
  versionError.value = "";
  versionFeedback.value = "";
  latestScore.value = null;
  try {
    const score = await reEvaluateCandidateJob(
      resume.candidate_id,
      Number(jobId),
      resume.id,
    );
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== jobId) return;
    latestScore.value = score;
    await loadResumeList();
    if (selectedJobId.value === jobId) versionFeedback.value = "重新评估已完成；不会自动联系候选人。";
  } catch (err) {
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== jobId) return;
    versionError.value = `重新评估失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    if (jobDataRequestId === operationVersion && selectedJobId.value === jobId) versionBusyId.value = null;
  }
}

function chooseDirectFiles(event: Event): void {
  directFiles.value = Array.from((event.target as HTMLInputElement).files ?? []);
  directImportResult.value = null;
  uploadError.value = "";
}

async function importDirectFiles(): Promise<void> {
  if (!directFiles.value.length || !selectedJobId.value || directImporting.value) return;
  const files = [...directFiles.value];
  const jobId = selectedJobId.value;
  const operationVersion = jobDataRequestId;
  directImporting.value = true;
  uploadError.value = "";
  directImportResult.value = null;
  try {
    const result = await batchImportResumes(files, Number(jobId));
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== jobId) return;
    directImportResult.value = result;
    await loadResumeList();
  } catch (err) {
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== jobId) return;
    uploadError.value = `添加岗位简历失败：${err instanceof Error ? err.message : String(err)}`;
  } finally {
    if (jobDataRequestId === operationVersion && selectedJobId.value === jobId) directImporting.value = false;
  }
}

function chooseFile(event: Event): void {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  uploadError.value = "";
}

async function submit(): Promise<void> {
  if (!selectedFile.value || !selectedCandidateId.value || !selectedJobId.value || uploading.value) return;
  const file = selectedFile.value;
  const candidateId = Number(selectedCandidateId.value);
  const jobId = Number(selectedJobId.value);
  const operationVersion = jobDataRequestId;
  uploading.value = true;
  uploadError.value = "";
  try {
    const uploaded = await uploadResume(file, candidateId, jobId);
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== String(jobId)) return;
    uploadedResume.value = uploaded;
    await loadResumeList();
  } catch (err) {
    if (jobDataRequestId !== operationVersion || selectedJobId.value !== String(jobId)) return;
    const message = err instanceof Error ? err.message : String(err);
    uploadError.value = `上传简历失败：${message}`;
  } finally {
    if (jobDataRequestId === operationVersion && selectedJobId.value === String(jobId)) uploading.value = false;
  }
}

function retryUpload(): void {
  void submit();
}

watch(selectedJobId, () => {
  jobDataRequestId += 1;
  candidates.value = [];
  resumes.value = [];
  candidateJobByCandidate.value = {};
  selectedCandidateId.value = "";
  directFiles.value = [];
  directImportResult.value = null;
  directImporting.value = false;
  if (directFileInput.value) directFileInput.value.value = "";
  uploading.value = false;
  versionBusyId.value = null;
  uploadedResume.value = null;
  latestScore.value = null;
  versionError.value = "";
  versionFeedback.value = "";
  uploadError.value = "";
  selectedFile.value = null;
  if (fileInput.value) fileInput.value.value = "";
  void Promise.all([loadCandidatesForJob(), loadResumeList()]);
});

onMounted(() => void loadJobs());
</script>

<template>
  <section class="page-section resumes-page" data-testid="resumes-page" data-page-panel>
    <header class="page-heading">
      <div>
        <p class="eyebrow">TALENT DOCUMENTS</p>
        <h1>RESUME LIBRARY.</h1>
        <p class="muted">先选择招聘岗位，再上传简历进行真实解析。</p>
      </div>
    </header>

    <section v-if="jobsError" class="panel">
      <p class="error" role="alert">{{ jobsError }}</p>
      <button type="button" aria-label="重试加载岗位" @click="loadJobs">重试</button>
    </section>
    <section v-else class="panel job-picker-panel">
      <div class="section-heading">
        <div><p class="eyebrow">STEP 01 / 选择一个岗位</p><h2>招聘岗位</h2></div>
        <div class="row">
          <p v-if="loading" aria-live="polite">正在加载岗位…</p>
          <button type="button" aria-label="在简历库新建岗位" @click="openJobCreate">新建岗位</button>
        </div>
      </div>
      <div v-if="jobs.length" class="job-picker">
        <button
          v-for="job in jobs"
          :key="job.id"
          type="button"
          class="pick-card"
          :class="{ active: selectedJobId === String(job.id) }"
          :aria-label="`选择岗位${job.name}`"
          :aria-pressed="selectedJobId === String(job.id)"
          @click="selectedJobId = String(job.id)"
        >
          <span>POSITION {{ String(job.id).padStart(2, "0") }}</span>
          <strong>{{ job.name }}</strong>
          <small>{{ job.enabled ? `AI 阈值 ${job.score_threshold} 分` : "已停用" }}</small>
        </button>
      </div>
    </section>

    <EmptyState v-if="!loading && !jobsError && jobs.length === 0" title="暂无可用岗位" description="可点击上方“新建岗位”直接创建，成功后会自动选中。" />
    <EmptyState v-else-if="!jobsError && !selectedJobId" title="CHOOSE A POSITION." description="请先选择岗位；选择岗位后才能进入简历上传区域。" />

    <template v-else-if="selectedJobId && !jobsError">
      <section class="resume-stats" aria-label="简历统计">
        <article data-testid="resume-stat-0"><span>岗位简历</span><strong>{{ resumes.length }}</strong></article>
        <article data-testid="resume-stat-1"><span>解析完成</span><strong>{{ resumes.filter((resume) => resume.parse_status === 'parsed').length }}</strong></article>
        <article data-testid="resume-stat-2"><span>待处理</span><strong>{{ resumes.filter((resume) => resume.parse_status !== 'parsed').length }}</strong></article>
      </section>

      <section class="panel resume-toolbar">
        <label>姓名<input aria-label="按姓名筛选简历" disabled placeholder="暂无按姓名筛选接口" /></label>
        <label>分数<select aria-label="按分数筛选简历" disabled><option>暂无分数筛选接口</option></select></label>
        <label>标签<select aria-label="按标签筛选简历" disabled><option>暂无标签筛选接口</option></select></label>
        <label>状态<select aria-label="按状态筛选简历" disabled><option>暂无状态筛选接口</option></select></label>
      </section>

      <section class="panel resume-boundary">
        <p class="eyebrow">LIBRARY STATUS</p>
        <h2>岗位简历版本</h2>
        <p v-if="listError" class="error" role="alert">{{ listError }}</p>
        <p v-if="versionError" class="error" role="alert">{{ versionError }}</p>
        <p v-if="versionFeedback" class="success-message" aria-live="polite">{{ versionFeedback }}</p>
        <p class="muted">重新评估会使用该岗位当前的完整 JD 与所选简历版本。</p>
        <ul v-if="resumes.length" class="resume-list">
          <li v-for="resume in resumes" :key="resume.id">
            <strong>{{ resume.original_filename || `简历 #${resume.id}` }}</strong>
            <span>
              候选人 #{{ resume.candidate_id ?? "未关联" }} · 版本 {{ resume.version_number ?? "未知" }} · {{ resume.parse_status }} ·
              {{ isActiveResume(resume) ? "当前使用" : "尚未启用" }}
            </span>
            <div v-if="resume.candidate_id !== null" class="row">
              <button
                type="button"
                class="secondary"
                :aria-label="`设 ${resume.original_filename || `简历 #${resume.id}`} 为当前版本`"
                :disabled="isActiveResume(resume) || versionBusyId !== null"
                @click="activateResume(resume)"
              >{{ isActiveResume(resume) ? "当前版本" : "设为当前版本" }}</button>
              <button
                type="button"
                :aria-label="`使用 ${resume.original_filename || `简历 #${resume.id}`} 重新评估`"
                :disabled="versionBusyId !== null"
                @click="reEvaluate(resume)"
              >{{ versionBusyId === resume.id ? "正在处理…" : "使用此版本重新评估" }}</button>
            </div>
          </li>
        </ul>
        <p v-else-if="!listError">该岗位暂无简历记录。</p>
        <section v-if="latestScore" class="drawer-section" aria-live="polite">
          <h3>最新手动评估结果</h3>
          <p><strong>{{ latestScore.score === null ? "无分数" : `${latestScore.score} 分` }}</strong> · {{ latestScore.decision }}</p>
          <p>{{ latestScore.reason }}</p>
          <p>证据：{{ latestScore.evidence.join("；") || "无" }}</p>
          <p>置信度：{{ latestScore.confidence === null ? "未知" : `${Math.round(latestScore.confidence * 100)}%` }} · 模型：{{ latestScore.model }}</p>
        </section>
        <p class="muted">上传新版不会自动切换或评分；手动重评会生成新评分，但不会自动联系候选人。高级姓名、分数、标签和状态筛选接口暂未提供。</p>
      </section>

      <form class="panel form-stack direct-resume-upload" @submit.prevent="importDirectFiles">
        <div><p class="eyebrow">ADD RESUMES</p><h2>添加岗位简历</h2></div>
        <p class="muted">直接选择一份或多份 PDF，简历会归档到当前岗位，暂未识别候选人的文件会显示为“未关联”。</p>
        <label class="upload-dropzone">
          岗位简历文件
          <input ref="directFileInput" aria-label="选择岗位简历文件" type="file" accept="application/pdf,.pdf" multiple @change="chooseDirectFiles" />
          <span>{{ directFiles.length ? `已选择 ${directFiles.length} 份 PDF` : "选择 PDF 简历" }}</span>
        </label>
        <p v-if="uploadError" class="error" role="alert">{{ uploadError }}</p>
        <button type="submit" :disabled="directFiles.length === 0 || directImporting">{{ directImporting ? "正在添加…" : "添加到当前岗位" }}</button>
        <p v-if="directImportResult" class="success-message" aria-live="polite">
          成功 {{ directImportResult.summary.imported }} 份 · 重复 {{ directImportResult.summary.duplicate }} 份 · 失败 {{ directImportResult.summary.failed }} 份
        </p>
        <ul v-if="directImportResult?.items.some((item) => item.status === 'failed')" class="error">
          <li v-for="item in directImportResult.items.filter((row) => row.status === 'failed')" :key="item.original_filename">
            {{ item.original_filename }}：{{ item.error }}
          </li>
        </ul>
      </form>

      <form class="panel form-stack resume-version-upload" @submit.prevent="submit">
        <div><p class="eyebrow">EXISTING CANDIDATE</p><h2>给已有候选人上传新版</h2></div>
        <label>
          关联候选人
          <select v-model="selectedCandidateId" aria-label="选择简历候选人" required>
            <option value="">请选择候选人</option>
            <option v-for="candidate in candidates" :key="candidate.id" :value="String(candidate.id)">
              {{ candidate.name }} · {{ candidate.boss_id || `候选人 #${candidate.id}` }}
            </option>
          </select>
        </label>
        <p v-if="candidates.length === 0" class="muted">暂无候选人，请先通过采集或候选人接口创建记录。</p>
        <label class="upload-dropzone">
          简历文件
          <input ref="fileInput" aria-label="选择简历文件" type="file" @change="chooseFile" />
          <span>{{ selectedFile ? selectedFile.name : "选择待解析文件" }}</span>
        </label>
        <p v-if="selectedFile" class="muted">已选择：{{ selectedFile.name }}</p>
        <p v-if="uploadError" class="error" role="alert">{{ uploadError }}</p>
        <div class="row">
          <button type="submit" :disabled="!selectedFile || !selectedCandidateId || uploading">{{ uploading ? "正在上传…" : "上传并解析" }}</button>
          <button v-if="uploadError" type="button" class="secondary" aria-label="重新上传简历" :disabled="uploading" @click="retryUpload">重新上传</button>
        </div>
      </form>
      <section v-if="uploadedResume" class="panel resume-result" aria-live="polite">
        <p class="eyebrow">PARSE RESULT</p>
        <h2>上传结果</h2>
        <p v-if="selectedFile">文件：{{ selectedFile.name }}</p>
        <p>解析状态：{{ uploadedResume.parse_status }}</p>
        <p class="muted">记录编号：{{ uploadedResume.id }}</p>
      </section>
    </template>

    <AppDrawer :open="jobFormOpen" title="新建岗位" @close="jobFormOpen = false">
      <form class="form-stack" aria-label="简历库新建岗位表单" @submit.prevent="saveJob">
        <label>岗位名称<input v-model="jobName" aria-label="岗位名称" required /></label>
        <p class="muted">创建后可立即添加简历。职位描述、BOSS 地址和筛选标准请到“岗位管理”中补充；配置完整前不会启动自动招聘。</p>
        <p v-if="jobSaveError" class="error" role="alert">{{ jobSaveError }}</p>
        <button type="submit" aria-label="保存并选择岗位" :disabled="jobSaving || !jobName.trim()">{{ jobSaving ? "正在保存…" : "保存并选择岗位" }}</button>
      </form>
    </AppDrawer>
  </section>
</template>
