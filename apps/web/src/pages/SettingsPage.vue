<script setup lang="ts">
import { onMounted, ref } from "vue";

import {
  createApiKey,
  getMyOutreachQuota,
  listUnknownOutreachEvents,
  listApiKeys,
  releaseUnknownOutreachEvent,
  revokeApiKey,
  type ApiKeyCreated,
  type ApiKeyRow,
  type UserMe,
  type OutreachQuota,
  type UnknownOutreachEvent,
} from "../api";
import AppDrawer from "../components/AppDrawer.vue";
import HrAccountManagement from "../components/HrAccountManagement.vue";
import StatusBadge from "../components/StatusBadge.vue";

const props = defineProps<{ user: UserMe }>();

const keys = ref<ApiKeyRow[]>([]);
const loading = ref(true);
const loadError = ref("");
const actionError = ref("");
const showCreate = ref(false);
const keyName = ref("");
const creating = ref(false);
const newKey = ref<ApiKeyCreated | null>(null);
const revokingId = ref<number | null>(null);
const quota = ref<OutreachQuota | null>(null);
const quotaError = ref("");
const unknownEvents = ref<UnknownOutreachEvent[]>([]);
const unknownLoading = ref(false);
const unknownLoadError = ref("");
const unknownConfirmed = ref<Record<number, boolean>>({});
const unknownReasons = ref<Record<number, string>>({});
const releasingUnknownId = ref<number | null>(null);
const unknownActionError = ref("");
const unknownActionSuccess = ref("");

async function loadQuota(): Promise<void> {
  quotaError.value = "";
  try {
    quota.value = await getMyOutreachQuota();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    quotaError.value = `加载联系额度失败：${message}`;
  }
}

async function loadUnknownEvents(): Promise<void> {
  unknownLoading.value = true;
  unknownLoadError.value = "";
  try {
    unknownEvents.value = await listUnknownOutreachEvents();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    unknownLoadError.value = `加载待核实联系失败：${message}`;
  } finally {
    unknownLoading.value = false;
  }
}

async function releaseUnknown(event: UnknownOutreachEvent): Promise<void> {
  const reason = unknownReasons.value[event.id]?.trim() ?? "";
  if (!unknownConfirmed.value[event.id] || !reason || releasingUnknownId.value !== null) return;

  releasingUnknownId.value = event.id;
  unknownActionError.value = "";
  unknownActionSuccess.value = "";
  try {
    await releaseUnknownOutreachEvent(event.id, reason);
    unknownActionSuccess.value = `已确认候选人“${event.candidate_name}”未发送并退还额度。`;
    delete unknownConfirmed.value[event.id];
    delete unknownReasons.value[event.id];
    await Promise.all([loadUnknownEvents(), loadQuota()]);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    unknownActionError.value = `处理待核实联系失败：${message}`;
  } finally {
    releasingUnknownId.value = null;
  }
}

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  actionError.value = "";
  try {
    keys.value = await listApiKeys();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    loadError.value = `加载 Agent Key 失败：${message}`;
  } finally {
    loading.value = false;
  }
}

async function create(): Promise<void> {
  const name = keyName.value.trim();
  if (!name) {
    actionError.value = "请输入 Key 名称";
    return;
  }
  if (creating.value) return;
  creating.value = true;
  actionError.value = "";
  try {
    const created = await createApiKey(name);
    const { api_key: apiKey, ...publicKey } = created;
    newKey.value = { ...publicKey, api_key: apiKey };
    keys.value.unshift({ ...publicKey, revoked_at: null });
    showCreate.value = false;
    keyName.value = "";
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    actionError.value = `创建 Agent Key 失败：${message}`;
  } finally {
    creating.value = false;
  }
}

async function revoke(key: ApiKeyRow): Promise<void> {
  if (revokingId.value !== null) return;
  revokingId.value = key.id;
  actionError.value = "";
  try {
    const updated = await revokeApiKey(key.id);
    keys.value = keys.value.map((item) => item.id === updated.id ? updated : item);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    actionError.value = `吊销 Agent Key 失败：${message}`;
  } finally {
    revokingId.value = null;
  }
}

onMounted(() => {
  void load();
  void loadQuota();
  if (props.user.role === "admin") void loadUnknownEvents();
});
</script>

<template>
  <section class="page-section settings-page" data-testid="settings-page" data-page-panel>
    <header class="page-heading">
      <div>
        <p class="eyebrow">CONTROL & SECURITY</p>
        <h1>SYSTEM SETTINGS.</h1>
        <p class="muted">管理个人 Agent 访问凭证与当前账号信息。</p>
      </div>
    </header>

    <div class="settings-grid settings-overview">
      <section class="panel settings-account">
        <p class="eyebrow">ACCOUNT & CONNECTION</p>
        <h2>{{ props.user.username }}</h2>
        <StatusBadge
          :label="props.user.role === 'admin' ? 'HR 总负责人' : props.user.role === 'lead' ? 'HR 负责人' : '普通 HR'"
          :tone="props.user.role === 'admin' ? 'warning' : props.user.role === 'lead' ? 'success' : 'neutral'"
        />
        <dl class="settings-facts">
          <div><dt>BOSS 账号</dt><dd>状态暂未接入</dd></div>
          <div><dt>Agent 设备</dt><dd>请前往工作台查看真实状态</dd></div>
        </dl>
        <p class="muted">团队使用共享额度；每位 HR 仍需使用自己的账号和个人 Agent Key。</p>
      </section>

      <section class="rule-hero">
        <p class="eyebrow">PERSONAL OUTREACH LIMIT</p>
        <h2>累计 {{ quota?.limit ?? 200 }} 次</h2>
        <p>每位 HR 自本功能上线后累计最多联系 200 人；历史联系只用于去重，不扣新额度。</p>
        <div v-if="quota" class="quota-values" aria-live="polite">
          <span>已确认 <b>{{ quota.confirmed }}</b></span>
          <span>预留中 <b>{{ quota.reserved }}</b></span>
          <span>可用 <b>{{ quota.remaining }}</b></span>
        </div>
        <p v-else-if="quotaError" class="error-text" role="alert">{{ quotaError }}</p>
        <small v-else>正在加载当前账号额度…</small>
      </section>

      <section class="panel safety-panel">
        <p class="eyebrow">SAFETY AUTOMATION</p>
        <h2>安全自动化</h2>
        <div class="safety-rules">
          <label v-for="label in ['随机发送间隔', '登录失效自动暂停', '连续异常自动暂停', '额度耗尽自动暂停']" :key="label" class="setting-row">
            <span>{{ label }}<small>服务端策略，前端暂不可修改</small></span>
            <input class="switch" type="checkbox" :aria-label="label" disabled />
          </label>
        </div>
      </section>

      <section class="panel capability-panel">
        <p class="eyebrow">SYSTEM BOUNDARY</p>
        <h2>服务端模型配置</h2>
        <p class="muted">大模型 Key 仅在服务端配置，不会在浏览器中展示或保存。</p>
        <p class="muted">BOSS 账号状态暂未接入；安全规则由服务端统一执行。</p>
      </section>
    </div>

    <section class="panel agent-key-panel">
      <div class="section-heading">
        <div><p class="eyebrow">PERSONAL ACCESS</p><h2>Agent Key</h2></div>
        <button type="button" aria-label="创建 Agent Key" @click="showCreate = true">创建 Key</button>
      </div>
      <section v-if="loadError" class="error-state">
        <p class="error" role="alert">{{ loadError }}</p>
        <button type="button" aria-label="重试加载 Agent Key" @click="load">重试</button>
      </section>
      <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
      <p v-if="loading" aria-live="polite">正在加载 Agent Key…</p>
      <div v-else-if="!loadError && keys.length" class="table-scroll">
        <table>
          <thead><tr><th>名称</th><th>前缀</th><th>状态</th><th>操作</th></tr></thead>
          <tbody>
            <tr v-for="key in keys" :key="key.id">
              <td>{{ key.name }}</td><td><code>{{ key.key_prefix }}</code></td><td>{{ key.revoked_at ? "已吊销" : "有效" }}</td>
              <td><button v-if="!key.revoked_at" type="button" class="danger" :aria-label="`吊销${key.name}`" :disabled="revokingId !== null" @click="revoke(key)">吊销</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="!loadError" class="muted">暂未创建 Agent Key。</p>
    </section>

    <HrAccountManagement v-if="props.user.role === 'admin'" />

    <section v-if="props.user.role === 'admin'" class="panel unknown-outreach-panel" aria-labelledby="unknown-outreach-heading">
      <div class="section-heading">
        <div><p class="eyebrow">MANUAL REVIEW</p><h2 id="unknown-outreach-heading">待核实联系</h2></div>
        <button type="button" :disabled="unknownLoading" @click="loadUnknownEvents">刷新列表</button>
      </div>
      <p class="muted">仅在核实候选人确实未收到招呼后，才确认未发送并退还预留额度。</p>
      <p v-if="unknownLoadError" class="error" role="alert">{{ unknownLoadError }} <button type="button" @click="loadUnknownEvents">重试</button></p>
      <p v-if="unknownActionError" class="error" role="alert">{{ unknownActionError }}</p>
      <p v-if="unknownActionSuccess" class="success-message" role="status" aria-live="polite">{{ unknownActionSuccess }}</p>
      <p v-if="unknownLoading" aria-live="polite">正在加载待核实联系…</p>
      <p v-else-if="!unknownLoadError && unknownEvents.length === 0" class="muted">当前没有待核实联系。</p>
      <ul v-else-if="!unknownLoadError" class="unknown-outreach-list">
        <li v-for="event in unknownEvents" :key="event.id" class="setting-row unknown-outreach-item">
          <div>
            <h3>{{ event.candidate_name }} · {{ event.job_name }}</h3>
            <p>额度所属 HR：{{ event.quota_owner_username }}<span v-if="event.task_id !== null"> · 批次 #{{ event.task_id }}</span></p>
            <p>异常原因：{{ event.failure_reason || "未提供" }}</p>
            <time v-if="event.created_at" :datetime="event.created_at">{{ new Date(event.created_at).toLocaleString("zh-CN") }}</time>
          </div>
          <form class="unknown-outreach-review" @submit.prevent="releaseUnknown(event)">
            <label :for="`unknown-reason-${event.id}`">核实理由（必填）</label>
            <textarea
              :id="`unknown-reason-${event.id}`"
              v-model="unknownReasons[event.id]"
              required
              rows="2"
              :disabled="releasingUnknownId !== null"
            />
            <label class="setting-row">
              <input v-model="unknownConfirmed[event.id]" type="checkbox" required :disabled="releasingUnknownId !== null" />
              <span>我已核实该候选人未收到招呼，确认退还额度</span>
            </label>
            <button type="submit" :disabled="!unknownConfirmed[event.id] || !unknownReasons[event.id]?.trim() || releasingUnknownId !== null">
              {{ releasingUnknownId === event.id ? "正在处理…" : "确认未发送并退还额度" }}
            </button>
          </form>
        </li>
      </ul>
    </section>

    <AppDrawer :open="showCreate" title="创建 Agent Key" @close="showCreate = false">
      <div class="grid">
        <label>Key 名称<input v-model="keyName" aria-label="Agent Key 名称" /></label>
        <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
        <div class="row"><button type="button" aria-label="确认创建 Agent Key" :disabled="creating" @click="create">{{ creating ? "正在创建…" : "确认创建" }}</button><button type="button" class="secondary" @click="showCreate = false">取消</button></div>
      </div>
    </AppDrawer>

    <AppDrawer :open="Boolean(newKey)" title="请立即保存 Agent Key" @close="newKey = null">
      <template v-if="newKey">
        <p class="error">仅显示这一次，关闭后无法再次查看。</p><code class="secret-value">{{ newKey.api_key }}</code>
        <button type="button" aria-label="关闭 Agent Key 明文" @click="newKey = null">我已保存</button>
      </template>
    </AppDrawer>
  </section>
</template>
