<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { listAgentRuns, type UserMe } from "../api";
import CandidatesPage from "../pages/CandidatesPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import JobsPage from "../pages/JobsPage.vue";
import ResumesPage from "../pages/ResumesPage.vue";
import SettingsPage from "../pages/SettingsPage.vue";
import { navigation, type PageId } from "../types";

const props = defineProps<{ user: UserMe }>();
const emit = defineEmits<{ logout: [] }>();

const activePage = ref<PageId>("dashboard");
const agentState = ref<"loading" | "online" | "empty" | "error">("loading");
const agentMachine = ref("");
const agentError = ref("");

const userInitials = computed(() => props.user.username.slice(0, 2).toUpperCase());
const agentLabel = computed(() => {
  if (agentState.value === "loading") return "检查中";
  if (agentState.value === "online") return agentMachine.value || "在线";
  if (agentState.value === "empty") return "暂无设备";
  return "状态未知";
});

async function loadAgentSummary(): Promise<void> {
  agentState.value = "loading";
  agentError.value = "";
  try {
    const runs = await listAgentRuns();
    const connected = runs.find((run) => ["online", "idle", "running"].includes(run.status));
    if (connected) {
      agentMachine.value = connected.machine_id;
      agentState.value = "online";
    } else {
      agentMachine.value = "";
      agentState.value = "empty";
    }
  } catch (err) {
    agentMachine.value = "";
    agentError.value = err instanceof Error ? err.message : String(err);
    agentState.value = "error";
  }
}

onMounted(() => void loadAgentSummary());
</script>

<template>
  <div class="app-shell" data-testid="authenticated-app">
    <header class="app-header">
      <div class="brand-block">
        <div class="brand"><span class="brand-mark" aria-hidden="true"></span>LEION HR</div>
        <span class="brand-subtitle">RECRUITING AUTOMATION</span>
      </div>
      <div class="header-actions">
        <button
          class="connection-chip"
          type="button"
          :aria-label="agentState === 'error' ? '重试 Agent 状态' : '前往工作台查看 Agent 状态'"
          :title="agentError || undefined"
          @click="agentState === 'error' ? loadAgentSummary() : (activePage = 'dashboard')"
        >
          <span
            class="connection-dot"
            :class="{ 'connection-dot--unknown': agentState !== 'online' }"
            aria-hidden="true"
          ></span>
          <span><small>AGENT</small>{{ agentLabel }}</span>
        </button>
        <div class="connection-chip boss-chip" aria-label="BOSS 账号状态暂未接入">
          <span class="connection-dot connection-dot--muted" aria-hidden="true"></span>
          <span><small>BOSS ACCOUNT</small>状态暂未接入</span>
        </div>
        <button class="user-menu" type="button" aria-label="退出登录" @click="emit('logout')">
          <span class="user-avatar">{{ userInitials }}</span>
          <span><small>ME</small>{{ props.user.username }}</span>
        </button>
      </div>
    </header>

    <nav class="app-sidebar" aria-label="主要页面">
      <button
        v-for="(item, index) in navigation"
        :key="item.id"
        type="button"
        :aria-label="`前往${item.label}`"
        :aria-current="activePage === item.id ? 'page' : undefined"
        :class="{ active: activePage === item.id }"
        @click="activePage = item.id"
      >
        <span class="nav-number">{{ String(index + 1).padStart(2, "0") }}</span>
        <span>{{ item.label }}</span>
      </button>
      <div class="sidebar-meta">
        <small>CURRENT DEVICE</small>
        <strong>{{ agentLabel }}</strong>
        <small>BOSS ACCOUNT</small>
        <strong>状态暂未接入</strong>
      </div>
    </nav>

    <main class="app-content">
      <DashboardPage v-if="activePage === 'dashboard'" />
      <JobsPage v-else-if="activePage === 'jobs'" />
      <CandidatesPage v-else-if="activePage === 'candidates'" :user="props.user" />
      <ResumesPage v-else-if="activePage === 'resumes'" />
      <SettingsPage v-else :user="props.user" />
    </main>

    <div class="shell-marquee" aria-hidden="true">
      <span>BEYOND THE RESUME · BUILT FOR HUMAN POTENTIAL · BEYOND THE RESUME · BUILT FOR HUMAN POTENTIAL</span>
    </div>
  </div>
</template>
