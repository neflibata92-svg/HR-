<script setup lang="ts">
import type { UserMe } from "../api";

defineProps<{ user: UserMe }>();
</script>

<template>
  <section data-testid="candidates-page" data-page-panel>
    <h1>候选人</h1>
    <p>真实候选人数据将在本页面接入。</p>
  </section>
</template>
