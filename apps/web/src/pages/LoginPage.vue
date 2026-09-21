<script setup lang="ts">
import { ref } from "vue";

import { login } from "../api";

const emit = defineEmits<{
  authenticated: [accessToken: string, refreshToken: string];
}>();

const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);

async function submit(): Promise<void> {
  if (submitting.value) return;
  error.value = "";
  const normalizedUsername = username.value.trim();
  if (!normalizedUsername) {
    error.value = "请输入用户名";
    return;
  }
  submitting.value = true;
  try {
    const tokens = await login(normalizedUsername, password.value);
    emit("authenticated", tokens.access_token, tokens.refresh_token);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <main class="login-page" data-testid="login-page">
    <section class="login-story" aria-label="LEION HR 品牌介绍">
      <div class="brand"><span class="brand-mark" aria-hidden="true"></span>LEION HR</div>
      <div>
        <h1>FIND.<br /><em>SCORE.</em><br />CONNECT.</h1>
        <p>让人才发现、智能判断与真实沟通自然流动。</p>
      </div>
      <small>RECRUITING INTELLIGENCE</small>
    </section>

    <section class="login-form-panel">
      <p class="eyebrow">SECURE WORKSPACE</p>
      <h2>欢迎回来</h2>
      <p class="muted">使用公司分配的账号登录招聘工作台</p>
      <form class="form-stack" @submit.prevent="submit">
        <label>
          用户名
          <input v-model="username" aria-label="用户名" autocomplete="username" required />
        </label>
        <label>
          密码
          <input
            v-model="password"
            aria-label="密码"
            autocomplete="current-password"
            type="password"
            required
          />
        </label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" :disabled="submitting">
          {{ submitting ? "正在登录…" : "登录" }}
        </button>
      </form>
      <p class="muted account-note">账号由 HR 总负责人统一创建。</p>
    </section>
  </main>
</template>
