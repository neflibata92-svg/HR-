<script setup lang="ts">
import type { UserMe } from "../api";

defineProps<{ user: UserMe }>();
</script>

<template>
  <section data-testid="settings-page" data-page-panel>
    <h1>系统设置</h1>
    <p>当前账号与 Agent 设置将在本页面接入。</p>
  </section>
</template>
