<script setup lang="ts">
import { ref } from "vue";

import { changePassword } from "../api";

const emit = defineEmits<{
  changed: [accessToken: string, refreshToken: string];
  logout: [];
}>();

const currentPassword = ref("");
const newPassword = ref("");
const confirmation = ref("");
const error = ref("");
const submitting = ref(false);

async function submit(): Promise<void> {
  if (submitting.value) return;
  error.value = "";
  if (newPassword.value !== confirmation.value) {
    error.value = "两次输入的新密码不一致";
    return;
  }
  submitting.value = true;
  try {
    const tokens = await changePassword(currentPassword.value, newPassword.value);
    emit("changed", tokens.access_token, tokens.refresh_token);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.startsWith("401")) {
      emit("logout");
      return;
    }
    error.value = message;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="password-change-page">
    <section class="panel password-change-card">
      <p class="eyebrow">首次登录安全设置</p>
      <h1>请先修改初始密码</h1>
      <p class="muted">完成后才能进入招聘工作台。新密码至少需要 8 位。</p>
      <form class="grid" @submit.prevent="submit">
        <label>
          当前密码
          <input v-model="currentPassword" aria-label="当前密码" type="password" required />
        </label>
        <label>
          新密码
          <input v-model="newPassword" aria-label="新密码" type="password" minlength="8" required />
        </label>
        <label>
          确认新密码
          <input v-model="confirmation" aria-label="确认新密码" type="password" minlength="8" required />
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" :disabled="submitting">
          {{ submitting ? "正在保存…" : "保存新密码" }}
        </button>
        <button class="secondary" type="button" aria-label="退出登录" @click="emit('logout')">
          退出登录
        </button>
      </form>
    </section>
  </main>
</template>
