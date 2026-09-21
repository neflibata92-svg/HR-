<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{
  open: boolean;
  title: string;
}>();

const emit = defineEmits<{
  close: [];
}>();

const titleId = `drawer-title-${Math.random().toString(36).slice(2)}`;
const dialog = ref<HTMLElement | null>(null);
let previousFocus: HTMLElement | null = null;

function focusableElements(): HTMLElement[] {
  if (!dialog.value) return [];
  return Array.from(
    dialog.value.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
    ),
  );
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    emit("close");
    return;
  }
  if (event.key !== "Tab") return;
  const items = focusableElements();
  if (items.length === 0) {
    event.preventDefault();
    dialog.value?.focus();
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      await nextTick();
      dialog.value?.focus();
    } else {
      previousFocus?.focus();
      previousFocus = null;
    }
  },
  { immediate: true },
);

onBeforeUnmount(() => previousFocus?.focus());
</script>

<template>
  <Teleport to="body">
    <div v-if="props.open" class="drawer-backdrop" @click.self="emit('close')">
      <aside
        ref="dialog"
        class="app-drawer"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
        :aria-labelledby="titleId"
        @keydown="onKeydown"
      >
        <header class="drawer-header">
          <h2 :id="titleId">{{ props.title }}</h2>
          <button
            class="icon-button"
            type="button"
            :aria-label="`关闭${props.title}`"
            @click="emit('close')"
          >
            关闭
          </button>
        </header>
        <div class="drawer-content">
          <slot />
        </div>
      </aside>
    </div>
  </Teleport>
</template>
