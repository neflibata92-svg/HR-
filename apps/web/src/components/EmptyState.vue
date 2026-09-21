<script setup lang="ts">
defineProps<{
  title: string;
  description: string;
}>();
</script>

<template>
  <section class="empty-state" aria-live="polite">
    <div class="empty-state-mark" aria-hidden="true"></div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </section>
</template>
