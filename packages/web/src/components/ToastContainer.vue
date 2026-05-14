<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-item"
          :class="`toast-${toast.type}`"
          @click="remove(toast.id)"
        >
          <span class="flex-1">{{ toast.text }}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="flex-shrink-0 cursor-pointer"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { useToast } from "@/composables/useToast";

const { toasts, remove } = useToast();
</script>
