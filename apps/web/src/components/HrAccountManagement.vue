<script setup lang="ts">
import { onMounted, ref } from "vue";

import {
  createHr,
  listUsers,
  resetUserPassword,
  setUserStatus,
  type UserRow,
} from "../api";

const users = ref<UserRow[]>([]);
const error = ref("");
const showCreate = ref(false);
const username = ref("");
const temporaryPassword = ref("");
const passwordConfirmation = ref("");
const pendingDisable = ref<UserRow | null>(null);
const pendingReset = ref<UserRow | null>(null);
const resetPassword = ref("");
const resetPasswordConfirmation = ref("");

async function load(): Promise<void> {
  error.value = "";
  try {
    users.value = await listUsers();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function replaceUser(updated: UserRow): void {
  users.value = users.value.map((user) => user.id === updated.id ? updated : user);
}

async function submitCreate(): Promise<void> {
  error.value = "";
  if (temporaryPassword.value !== passwordConfirmation.value) {
    error.value = "两次输入的密码不一致";
    return;
  }
  try {
    const created = await createHr(username.value, temporaryPassword.value);
    users.value = [...users.value, created];
    showCreate.value = false;
    username.value = "";
    temporaryPassword.value = "";
    passwordConfirmation.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function confirmDisable(): Promise<void> {
  if (!pendingDisable.value) return;
  const user = pendingDisable.value;
  try {
    replaceUser(await setUserStatus(user.id, false));
    pendingDisable.value = null;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function enable(user: UserRow): Promise<void> {
  error.value = "";
  try {
    replaceUser(await setUserStatus(user.id, true));
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function confirmReset(): Promise<void> {
  if (!pendingReset.value) return;
  error.value = "";
  if (resetPassword.value !== resetPasswordConfirmation.value) {
    error.value = "两次输入的密码不一致";
    return;
  }
  try {
    replaceUser(await resetUserPassword(pendingReset.value.id, resetPassword.value));
    pendingReset.value = null;
    resetPassword.value = "";
    resetPasswordConfirmation.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
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
    <p v-if="error" class="error" role="alert">{{ error }}</p>

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
                @click="pendingDisable = account"
              >停用</button>
              <button
                v-else
                type="button"
                :aria-label="`重新启用 ${account.username}`"
                @click="enable(account)"
              >重新启用</button>
              <button
                class="secondary"
                type="button"
                :aria-label="`重置 ${account.username} 密码`"
                @click="pendingReset = account"
              >重置密码</button>
            </template>
            <span v-else>不可操作</span>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop">
      <section class="modal" role="dialog" aria-modal="true" aria-label="新增 HR 表单">
        <h3>新增 HR</h3>
        <form class="grid" @submit.prevent="submitCreate">
          <label>用户名<input v-model="username" aria-label="用户名" required minlength="2" /></label>
          <label>临时密码<input v-model="temporaryPassword" aria-label="临时密码" type="password" required minlength="8" /></label>
          <label>确认密码<input v-model="passwordConfirmation" aria-label="确认密码" type="password" required minlength="8" /></label>
          <div class="row"><button type="submit">创建账号</button><button class="secondary" type="button" @click="showCreate = false">取消</button></div>
        </form>
      </section>
    </div>

    <div v-if="pendingDisable" class="modal-backdrop">
      <section class="modal" role="dialog" aria-modal="true" aria-label="停用确认">
        <h3>停用 {{ pendingDisable.username }}？</h3>
        <p>该 HR 将无法登录，但历史数据仍会保留。</p>
        <div class="row"><button class="danger" type="button" aria-label="确认停用" @click="confirmDisable">确认停用</button><button class="secondary" type="button" aria-label="取消停用" @click="pendingDisable = null">取消</button></div>
      </section>
    </div>

    <div v-if="pendingReset" class="modal-backdrop">
      <section class="modal" role="dialog" aria-modal="true" aria-label="重置密码确认">
        <h3>重置 {{ pendingReset.username }} 的密码</h3>
        <label>新临时密码<input v-model="resetPassword" aria-label="重置临时密码" type="password" minlength="8" required /></label>
        <label>确认临时密码<input v-model="resetPasswordConfirmation" aria-label="确认重置临时密码" type="password" minlength="8" required /></label>
        <div class="row"><button type="button" aria-label="确认重置密码" :disabled="resetPassword.length < 8 || resetPasswordConfirmation.length < 8" @click="confirmReset">确认重置</button><button class="secondary" type="button" @click="pendingReset = null">取消</button></div>
      </section>
    </div>
  </section>
</template>
