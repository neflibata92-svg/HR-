<script setup lang="ts">
import { onMounted, ref } from "vue";

import {
  createApiKey,
  listApiKeys,
  revokeApiKey,
  type ApiKeyCreated,
  type ApiKeyRow,
  type UserMe,
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

onMounted(() => void load());
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
        <p class="eyebrow">DAILY SHARED QUOTA</p>
        <h2>200 次 / 天</h2>
        <p>每位 HR 每日 200 次，全岗位共享。</p>
        <div class="quota-values"><span>今日已用 <b>—</b></span><span>今日剩余 <b>—</b></span></div>
        <small>用量接口暂未接入</small>
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
