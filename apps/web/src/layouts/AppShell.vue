<script setup lang="ts">
import { ref } from "vue";

import type { UserMe } from "../api";
import CandidatesPage from "../pages/CandidatesPage.vue";
import DashboardPage from "../pages/DashboardPage.vue";
import JobsPage from "../pages/JobsPage.vue";
import ResumesPage from "../pages/ResumesPage.vue";
import SettingsPage from "../pages/SettingsPage.vue";
import { navigation, type PageId } from "../types";

const props = defineProps<{ user: UserMe }>();
const emit = defineEmits<{ logout: [] }>();

const activePage = ref<PageId>("dashboard");
</script>

<template>
  <div class="app-shell" data-testid="authenticated-app">
    <header class="app-header">
      <div class="brand"><span class="brand-mark" aria-hidden="true"></span>LEION HR</div>
      <div class="header-actions">
        <button
          class="agent-summary"
          type="button"
          aria-label="前往工作台查看 Agent 状态"
          @click="activePage = 'dashboard'"
        >
          Agent 状态
        </button>
        <span>{{ props.user.username }}</span>
        <button type="button" aria-label="退出登录" @click="emit('logout')">退出登录</button>
      </div>
    </header>

    <nav class="app-sidebar" aria-label="主要页面">
      <button
        v-for="item in navigation"
        :key="item.id"
        type="button"
        :aria-label="`前往${item.label}`"
        :aria-current="activePage === item.id ? 'page' : undefined"
        :class="{ active: activePage === item.id }"
        @click="activePage = item.id"
      >
        {{ item.label }}
      </button>
    </nav>

    <main class="app-content">
      <DashboardPage v-if="activePage === 'dashboard'" />
      <JobsPage v-else-if="activePage === 'jobs'" />
      <CandidatesPage v-else-if="activePage === 'candidates'" :user="props.user" />
      <ResumesPage v-else-if="activePage === 'resumes'" />
      <SettingsPage v-else :user="props.user" />
    </main>
  </div>
</template>
