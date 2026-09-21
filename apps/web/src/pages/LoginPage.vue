<script setup lang="ts">
import { ref } from "vue";

import { login } from "../api";

const emit = defineEmits<{
  authenticated: [accessToken: string, refreshToken: string];
}>();

const rememberedUsernameKey = "leion-hr:remembered-username";
const rememberedUsername = localStorage.getItem(rememberedUsernameKey) ?? "";
const username = ref(rememberedUsername);
const password = ref("");
const rememberUsername = ref(Boolean(rememberedUsername));
const showPassword = ref(false);
const forgottenNotice = ref("");
const error = ref("");
const submitting = ref(false);

function showForgottenPasswordHelp(): void {
  forgottenNotice.value = "请联系企业管理员重置密码。";
}

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
    if (rememberUsername.value) {
      localStorage.setItem(rememberedUsernameKey, normalizedUsername);
    } else {
      localStorage.removeItem(rememberedUsernameKey);
    }
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
      <div class="login-story-copy">
        <p class="eyebrow login-eyebrow">RECRUITING INTELLIGENCE</p>
        <h1>FIND.<br /><em>SCORE.</em><br />CONNECT.</h1>
        <p>让人才发现、智能判断与真实沟通自然流动。</p>
      </div>
      <small>BEYOND THE RESUME · BUILT FOR HUMAN POTENTIAL</small>
    </section>

    <section class="login-form-panel">
      <div class="login-form-card">
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
            <span class="password-field">
              <input
                v-model="password"
                aria-label="密码"
                autocomplete="current-password"
                :type="showPassword ? 'text' : 'password'"
                required
              />
              <button
                class="password-toggle"
                type="button"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                {{ showPassword ? "隐藏" : "显示" }}
              </button>
            </span>
          </label>
          <div class="login-options">
            <label class="check-label">
              <input v-model="rememberUsername" aria-label="记住账号" type="checkbox" />
              记住账号
            </label>
            <button class="text-button" type="button" aria-label="忘记密码" @click="showForgottenPasswordHelp">
              忘记密码？
            </button>
          </div>
          <p v-if="forgottenNotice" class="capability-message" role="status">{{ forgottenNotice }}</p>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <button class="login-submit" type="submit" :disabled="submitting">
            {{ submitting ? "正在登录…" : "进入工作台" }}
          </button>
        </form>
        <p class="muted account-note">账号由 HR 总负责人统一创建。</p>
      </div>
    </section>
  </main>
</template>
