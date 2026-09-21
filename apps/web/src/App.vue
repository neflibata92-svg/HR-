<script setup lang="ts">
import { onMounted, ref } from "vue";

import { clearTokens, isLoggedIn, me, setTokens, type UserMe } from "./api";
import FirstPasswordChange from "./components/FirstPasswordChange.vue";
import AppShell from "./layouts/AppShell.vue";
import LoginPage from "./pages/LoginPage.vue";

const user = ref<UserMe | null>(null);
const checkingSession = ref(isLoggedIn());
const sessionError = ref("");

async function loadCurrentUser(): Promise<void> {
  checkingSession.value = true;
  sessionError.value = "";
  user.value = null;
  try {
    user.value = await me();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.startsWith("401")) {
      clearTokens();
    } else {
      sessionError.value = message;
    }
  } finally {
    checkingSession.value = false;
  }
}

async function onAuthenticated(accessToken: string, refreshToken: string): Promise<void> {
  setTokens(accessToken, refreshToken);
  await loadCurrentUser();
}

function onLogout(): void {
  clearTokens();
  user.value = null;
  checkingSession.value = false;
}

onMounted(() => {
  if (isLoggedIn()) {
    void loadCurrentUser();
  }
});
</script>

<template>
  <main v-if="checkingSession" class="session-loading" aria-live="polite">正在确认登录状态…</main>

  <FirstPasswordChange
    v-else-if="user?.must_change_password"
    @changed="onAuthenticated"
    @logout="onLogout"
  />

  <AppShell v-else-if="user" :user="user" @logout="onLogout" />

  <main v-else-if="sessionError" class="session-error">
    <section class="panel">
      <h1>暂时无法确认登录状态</h1>
      <p class="error" role="alert">{{ sessionError }}</p>
      <button type="button" aria-label="重试确认登录状态" @click="loadCurrentUser">重试</button>
    </section>
  </main>

  <LoginPage v-else @authenticated="onAuthenticated" />
</template>
