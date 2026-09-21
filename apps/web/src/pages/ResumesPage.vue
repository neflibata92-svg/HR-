<script setup lang="ts">
import { onMounted, ref, watch } from "vue";

import { listJobs, uploadResume, type Job, type Resume } from "../api";
import EmptyState from "../components/EmptyState.vue";

const jobs = ref<Job[]>([]);
const selectedJobId = ref("");
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const loading = ref(true);
const jobsError = ref("");
const uploadError = ref("");
const uploading = ref(false);
const uploadedResume = ref<Resume | null>(null);

async function loadJobs(): Promise<void> {
  loading.value = true;
  jobsError.value = "";
  try {
    jobs.value = (await listJobs()).filter((job) => job.enabled);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    jobsError.value = `加载岗位失败：${message}`;
  } finally {
    loading.value = false;
  }
}

function chooseFile(event: Event): void {
  selectedFile.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  uploadError.value = "";
}

async function submit(): Promise<void> {
  if (!selectedFile.value || uploading.value) return;
  uploading.value = true;
  uploadError.value = "";
  try {
    uploadedResume.value = await uploadResume(selectedFile.value);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    uploadError.value = `上传简历失败：${message}`;
  } finally {
    uploading.value = false;
  }
}

function retryUpload(): void {
  void submit();
}

watch(selectedJobId, () => {
  uploadedResume.value = null;
  uploadError.value = "";
  selectedFile.value = null;
  if (fileInput.value) fileInput.value.value = "";
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
        <p v-if="loading" aria-live="polite">正在加载岗位…</p>
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
          <small>AI 阈值 {{ job.score_threshold }} 分</small>
        </button>
      </div>
    </section>

    <EmptyState v-if="!loading && !jobsError && jobs.length === 0" title="暂无可用岗位" description="请先在岗位管理中创建或启用岗位。" />
    <EmptyState v-else-if="!jobsError && !selectedJobId" title="CHOOSE A POSITION." description="请先选择岗位；选择岗位后才能进入简历上传区域。" />

    <template v-else-if="selectedJobId && !jobsError">
      <section class="resume-stats" aria-label="简历统计">
        <article v-for="(label, index) in ['岗位简历', '解析完成', '待处理']" :key="label" :data-testid="`resume-stat-${index}`">
          <span>{{ label }}</span><strong>—</strong><small>暂未接入</small>
        </article>
      </section>

      <section class="panel resume-toolbar">
        <label>姓名<input aria-label="按姓名筛选简历" disabled placeholder="暂未接入" /></label>
        <label>分数<select aria-label="按分数筛选简历" disabled><option>暂未接入</option></select></label>
        <label>标签<select aria-label="按标签筛选简历" disabled><option>暂未接入</option></select></label>
        <label>状态<select aria-label="按状态筛选简历" disabled><option>暂未接入</option></select></label>
      </section>

      <section class="panel resume-boundary">
        <p class="eyebrow">LIBRARY STATUS</p>
        <h2>简历列表及岗位关联暂未接入</h2>
        <p>后端尚不支持简历列表及岗位关联。本次选择仅用于进入上传流程，不会虚构岗位归属。</p>
      </section>

      <form class="panel form-stack resume-upload" @submit.prevent="submit">
        <div><p class="eyebrow">UPLOAD / PARSE</p><h2>上传简历</h2></div>
        <label class="upload-dropzone">
          简历文件
          <input ref="fileInput" aria-label="选择简历文件" type="file" @change="chooseFile" />
          <span>{{ selectedFile ? selectedFile.name : "选择待解析文件" }}</span>
        </label>
        <p v-if="selectedFile" class="muted">已选择：{{ selectedFile.name }}</p>
        <p v-if="uploadError" class="error" role="alert">{{ uploadError }}</p>
        <div class="row">
          <button type="submit" :disabled="!selectedFile || uploading">{{ uploading ? "正在上传…" : "上传并解析" }}</button>
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
  </section>
</template>
