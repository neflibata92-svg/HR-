<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  createJob,
  listAgentRuns,
  listCandidates,
  listJobs,
  markExchange,
  setToken,
  uploadResume,
  type AgentRun,
  type Candidate,
  type Job,
} from "./api";

const tokenInput = ref(localStorage.getItem("api_token") || "dev-token-change-me");
const jobs = ref<Job[]>([]);
const candidates = ref<Candidate[]>([]);
const runs = ref<AgentRun[]>([]);
const query = ref("");
const error = ref("");
const jobName = ref("");
const jobJd = ref("");
const jobThreshold = ref(80);
const jobGreet = ref("您好，看了您的经历很匹配，方便发一下附件简历吗？");
const operator = ref("hr");

async function refresh(): Promise<void> {
  error.value = "";
  try {
    setToken(tokenInput.value.trim());
    jobs.value = await listJobs();
    candidates.value = await listCandidates(query.value.trim());
    runs.value = await listAgentRuns();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function onCreateJob(): Promise<void> {
  await createJob({
    name: jobName.value,
    jd_text: jobJd.value,
    score_threshold: jobThreshold.value,
    greet_template: jobGreet.value,
  });
  jobName.value = "";
  jobJd.value = "";
  await refresh();
}

async function onMark(id: number): Promise<void> {
  await markExchange(id, operator.value || "hr");
  await refresh();
}

async function onUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  await uploadResume(file);
  input.value = "";
  await refresh();
}

onMounted(() => {
  void refresh();
});
</script>

<template>
  <div class="layout">
    <h1>简历库管理台</h1>
    <p class="muted">内网共享 JD、候选人、交换冷却与 Agent 状态。</p>

    <section class="panel">
      <div class="row">
        <input v-model="tokenInput" placeholder="API Token" style="max-width: 280px" />
        <button type="button" @click="refresh">保存并刷新</button>
      </div>
      <p v-if="error" style="color: #a33">{{ error }}</p>
    </section>

    <section class="panel">
      <h2>创建岗位</h2>
      <div class="grid">
        <input v-model="jobName" placeholder="岗位名称" />
        <textarea v-model="jobJd" rows="4" placeholder="JD 原文" />
        <input v-model.number="jobThreshold" type="number" placeholder="分数阈值" />
        <textarea v-model="jobGreet" rows="2" placeholder="招呼话术" />
        <button type="button" @click="onCreateJob">创建</button>
      </div>
    </section>

    <section class="panel">
      <h2>岗位列表</h2>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>名称</th>
            <th>阈值</th>
            <th>启用</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.id">
            <td>{{ job.id }}</td>
            <td>{{ job.name }}</td>
            <td>{{ job.score_threshold }}</td>
            <td>{{ job.enabled ? "是" : "否" }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2>候选人 / 交换标记</h2>
      <div class="row">
        <input v-model="query" placeholder="搜索姓名/BOSS ID" style="max-width: 240px" />
        <input v-model="operator" placeholder="操作人" style="max-width: 140px" />
        <button type="button" @click="refresh">搜索</button>
        <label>
          上传简历
          <input type="file" @change="onUpload" />
        </label>
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>姓名</th>
            <th>年龄</th>
            <th>年限</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in candidates" :key="c.id">
            <td>{{ c.id }}</td>
            <td>{{ c.name }}</td>
            <td>{{ c.age ?? "-" }}</td>
            <td>{{ c.years_of_experience ?? "-" }}</td>
            <td>
              <button type="button" @click="onMark(c.id)">标记已交换</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Agent 状态</h2>
      <table>
        <thead>
          <tr>
            <th>机器</th>
            <th>状态</th>
            <th>错误</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="run in runs" :key="run.machine_id">
            <td>{{ run.machine_id }}</td>
            <td>{{ run.status }}</td>
            <td>{{ run.last_error || "-" }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>
