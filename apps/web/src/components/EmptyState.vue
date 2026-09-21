<script setup lang="ts">
withDefaults(defineProps<{
  title: string;
  description: string;
  kind?: "empty" | "unavailable" | "error";
}>(), {
  kind: "empty",
});
</script>

<template>
  <section :class="['empty-state', `empty-state--${kind}`]" aria-live="polite">
    <div class="empty-state-mark" aria-hidden="true"></div>
    <h3>{{ title }}</h3>
    <p>{{ description }}</p>
    <slot />
  </section>
</template>
