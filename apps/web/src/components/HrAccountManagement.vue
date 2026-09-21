<script setup lang="ts">
import { onMounted, ref } from "vue";

import {
  createHr,
  listUsers,
  resetUserPassword,
  setUserStatus,
  type UserRow,
} from "../api";
import AppDrawer from "./AppDrawer.vue";

const users = ref<UserRow[]>([]);
const loading = ref(true);
const loadError = ref("");
const error = ref("");
const showCreate = ref(false);
const username = ref("");
const temporaryPassword = ref("");
const passwordConfirmation = ref("");
const pendingDisable = ref<UserRow | null>(null);
const pendingReset = ref<UserRow | null>(null);
const resetPassword = ref("");
const resetPasswordConfirmation = ref("");
const creating = ref(false);
const disabling = ref(false);
const enablingId = ref<number | null>(null);
const resetting = ref(false);

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";
  try {
    users.value = await listUsers();
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

function replaceUser(updated: UserRow): void {
  users.value = users.value.map((user) => user.id === updated.id ? updated : user);
}

async function submitCreate(): Promise<void> {
  if (creating.value) return;
  error.value = "";
  if (temporaryPassword.value !== passwordConfirmation.value) {
    error.value = "两次输入的密码不一致";
    return;
  }
  creating.value = true;
  try {
    const created = await createHr(username.value, temporaryPassword.value);
    users.value = [...users.value, created];
    showCreate.value = false;
    username.value = "";
    temporaryPassword.value = "";
    passwordConfirmation.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    creating.value = false;
  }
}

async function confirmDisable(): Promise<void> {
  if (!pendingDisable.value || disabling.value) return;
  const user = pendingDisable.value;
  disabling.value = true;
  try {
    replaceUser(await setUserStatus(user.id, false));
    pendingDisable.value = null;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    disabling.value = false;
  }
}

async function enable(user: UserRow): Promise<void> {
  if (enablingId.value !== null) return;
  error.value = "";
  enablingId.value = user.id;
  try {
    replaceUser(await setUserStatus(user.id, true));
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    enablingId.value = null;
  }
}

async function confirmReset(): Promise<void> {
  if (!pendingReset.value || resetting.value) return;
  error.value = "";
  if (resetPassword.value !== resetPasswordConfirmation.value) {
    error.value = "两次输入的密码不一致";
    return;
  }
  resetting.value = true;
  try {
    replaceUser(await resetUserPassword(pendingReset.value.id, resetPassword.value));
    pendingReset.value = null;
    resetPassword.value = "";
    resetPasswordConfirmation.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    resetting.value = false;
  }
}

onMounted(() => void load());
</script>

<template>
  <section class="panel">
    <div class="section-heading">
      <div>
        <p class="eyebrow">仅 HR 总负责人</p>
        <h2>HR 账号管理</h2>
      </div>
      <button type="button" aria-label="新增 HR" @click="showCreate = true">新增 HR</button>
    </div>
    <p class="muted">每位 HR 使用自己的账号和个人 Agent API Key。停用不会删除历史记录。</p>
    <section v-if="loadError" class="error-state">
      <p class="error" role="alert">加载 HR 账号失败：{{ loadError }}</p>
      <button type="button" aria-label="重试加载 HR 账号" @click="load">重试</button>
    </section>
    <p v-else-if="loading" aria-live="polite">正在加载 HR 账号…</p>
    <p v-if="error && !showCreate && !pendingDisable && !pendingReset" class="error" role="alert">{{ error }}</p>

    <div v-if="!loadError" class="table-scroll">
      <table>
        <thead><tr><th>用户名</th><th>账号类型</th><th>状态</th><th>首次改密</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="account in users" :key="account.id">
            <td>{{ account.username }}</td>
            <td>{{ account.role === "admin" ? "HR 总负责人" : "普通 HR" }}</td>
            <td>{{ account.is_active ? "正常" : "已停用" }}</td>
            <td>{{ account.must_change_password ? "待完成" : "已完成" }}</td>
            <td class="row">
              <template v-if="account.role === 'member'">
                <button
                  v-if="account.is_active"
                  class="danger"
                  type="button"
                  :aria-label="`停用 ${account.username}`"
                  @click="error = ''; pendingDisable = account"
                >停用</button>
                <button
                  v-else
                  type="button"
                  :aria-label="`重新启用 ${account.username}`"
                  :disabled="enablingId !== null"
                  @click="enable(account)"
                >{{ enablingId === account.id ? "正在启用…" : "重新启用" }}</button>
                <button
                  class="secondary"
                  type="button"
                  :aria-label="`重置 ${account.username} 密码`"
                  @click="error = ''; pendingReset = account"
                >重置密码</button>
              </template>
              <span v-else>不可操作</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <AppDrawer :open="showCreate" title="新增 HR" @close="showCreate = false">
      <form class="grid" @submit.prevent="submitCreate">
        <label>用户名<input v-model="username" aria-label="用户名" required minlength="2" /></label>
        <label>临时密码<input v-model="temporaryPassword" aria-label="临时密码" type="password" required minlength="8" /></label>
        <label>确认密码<input v-model="passwordConfirmation" aria-label="确认密码" type="password" required minlength="8" /></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="row"><button type="submit" :disabled="creating">{{ creating ? "正在创建…" : "创建账号" }}</button><button class="secondary" type="button" @click="showCreate = false">取消</button></div>
      </form>
    </AppDrawer>

    <AppDrawer :open="Boolean(pendingDisable)" title="停用确认" @close="pendingDisable = null">
      <template v-if="pendingDisable">
        <h3>停用 {{ pendingDisable.username }}？</h3>
        <p>该 HR 将无法登录，但历史数据仍会保留。</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="row"><button class="danger" type="button" aria-label="确认停用" :disabled="disabling" @click="confirmDisable">{{ disabling ? "正在停用…" : "确认停用" }}</button><button class="secondary" type="button" aria-label="取消停用" @click="pendingDisable = null">取消</button></div>
      </template>
    </AppDrawer>

    <AppDrawer :open="Boolean(pendingReset)" title="重置密码确认" @close="pendingReset = null">
      <template v-if="pendingReset">
        <h3>重置 {{ pendingReset.username }} 的密码</h3>
        <label>新临时密码<input v-model="resetPassword" aria-label="重置临时密码" type="password" minlength="8" required /></label>
        <label>确认临时密码<input v-model="resetPasswordConfirmation" aria-label="确认重置临时密码" type="password" minlength="8" required /></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="row"><button type="button" aria-label="确认重置密码" :disabled="resetting || resetPassword.length < 8 || resetPasswordConfirmation.length < 8" @click="confirmReset">{{ resetting ? "正在重置…" : "确认重置" }}</button><button class="secondary" type="button" @click="pendingReset = null">取消</button></div>
      </template>
    </AppDrawer>
  </section>
</template>
