<script setup lang="ts">
import { onMounted, ref } from "vue";
import FirstPasswordChange from "./components/FirstPasswordChange.vue";
import HrAccountManagement from "./components/HrAccountManagement.vue";
import {
  clearTokens,
  createApiKey,
  createJob,
  isLoggedIn,
  listAgentRuns,
  listApiKeys,
  listCandidates,
  listJobs,
  login,
  markExchange,
  me,
  register,
  revokeApiKey,
  setTokens,
  uploadResume,
  type AgentRun,
  type ApiKeyRow,
  type Candidate,
  type Job,
  type UserMe,
} from "./api";

const username = ref("");
const password = ref("");
const user = ref<UserMe | null>(null);
const jobs = ref<Job[]>([]);
const candidates = ref<Candidate[]>([]);
const runs = ref<AgentRun[]>([]);
const apiKeys = ref<ApiKeyRow[]>([]);
const newApiKeyPlain = ref("");
const query = ref("");
const error = ref("");
const jobName = ref("");
const jobJd = ref("");
const jobThreshold = ref(80);
const jobGreet = ref("您好，看了您的经历很匹配，方便发一下附件简历吗？");
const operator = ref("hr");

function resetWorkspace(): void {
  jobs.value = [];
  candidates.value = [];
  runs.value = [];
  apiKeys.value = [];
  newApiKeyPlain.value = "";
}

async function loadWorkspace(): Promise<void> {
  jobs.value = await listJobs();
  candidates.value = await listCandidates(query.value.trim());
  runs.value = await listAgentRuns();
  apiKeys.value = await listApiKeys();
}

async function loadCurrentUser(): Promise<void> {
  error.value = "";
  try {
    const currentUser = await me();
    user.value = currentUser;
    if (currentUser.must_change_password) {
      resetWorkspace();
      return;
    }
    await loadWorkspace();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    if (error.value.startsWith("401")) {
      clearTokens();
      user.value = null;
      resetWorkspace();
    }
  }
}

async function onPasswordChanged(accessToken: string, refreshToken: string): Promise<void> {
  setTokens(accessToken, refreshToken);
  await loadCurrentUser();
}

async function onLogin(): Promise<void> {
  error.value = "";
  try {
    const tokens = await login(username.value.trim(), password.value);
    setTokens(tokens.access_token, tokens.refresh_token);
    await loadCurrentUser();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function onRegister(): Promise<void> {
  error.value = "";
  try {
    const tokens = await register(username.value.trim(), password.value);
    setTokens(tokens.access_token, tokens.refresh_token);
    await loadCurrentUser();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function onLogout(): void {
  clearTokens();
  user.value = null;
  resetWorkspace();
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
  await loadCurrentUser();
}

async function onMark(id: number): Promise<void> {
  await markExchange(id, operator.value || user.value?.username || "hr");
  await loadCurrentUser();
}

async function onUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  await uploadResume(file);
  input.value = "";
  await loadCurrentUser();
}

async function onCreateKey(): Promise<void> {
  const created = await createApiKey("agent");
  newApiKeyPlain.value = created.api_key;
  await loadCurrentUser();
}

async function onRevokeKey(id: number): Promise<void> {
  await revokeApiKey(id);
  await loadCurrentUser();
}

onMounted(() => {
  if (isLoggedIn()) {
    void loadCurrentUser();
  }
});
</script>

<template>
  <FirstPasswordChange
    v-if="user?.must_change_password"
    @changed="onPasswordChanged"
    @logout="onLogout"
  />

  <div v-else class="layout">
    <h1>简历库管理台</h1>
    <p class="muted">云端共享 JD、候选人、交换冷却；本机 Agent 使用个人 API Key。</p>

    <section v-if="!user" class="panel">
      <h2>登录</h2>
      <div class="grid">
        <input v-model="username" placeholder="用户名" />
        <input v-model="password" type="password" placeholder="密码" />
        <div class="row">
          <button type="button" @click="onLogin">登录</button>
          <button type="button" @click="onRegister">注册（首个为 admin）</button>
        </div>
      </div>
      <p v-if="error" style="color: #a33">{{ error }}</p>
    </section>

    <template v-else>
      <section class="panel">
        <div class="row">
          <span>{{ user.username }}（{{ user.role === "admin" ? "HR 总负责人" : "HR" }}）</span>
          <button type="button" @click="loadCurrentUser">刷新</button>
          <button type="button" @click="onLogout">退出</button>
        </div>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
      </section>

      <HrAccountManagement v-if="user.role === 'admin'" />

      <section class="panel">
        <h2>API Key（给本机 Agent）</h2>
        <div class="row">
          <button type="button" @click="onCreateKey">生成新密钥</button>
        </div>
        <p v-if="newApiKeyPlain" style="word-break: break-all">
          请立即复制（只显示一次）：<code>{{ newApiKeyPlain }}</code>
        </p>
        <table>
          <thead>
            <tr>
              <th>名称</th>
              <th>前缀</th>
              <th>状态</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="k in apiKeys" :key="k.id">
              <td>{{ k.name }}</td>
              <td>{{ k.key_prefix }}</td>
              <td>{{ k.revoked_at ? "已吊销" : "有效" }}</td>
              <td>
                <button v-if="!k.revoked_at" type="button" @click="onRevokeKey(k.id)">吊销</button>
              </td>
            </tr>
          </tbody>
        </table>
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
          <button type="button" @click="loadCurrentUser">搜索</button>
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
    </template>
  </div>
</template>
