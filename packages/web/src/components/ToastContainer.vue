<template>
  <Teleport to="body">
    <div class="toast-container" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          class="toast-item"
          :class="`toast-${toast.type}`"
          :role="toast.type === 'error' ? 'alert' : 'status'"
        >
          <span class="flex-1">{{ toast.text }}</span>
          <button
            class="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-sm hover:bg-black/5 transition-colors cursor-pointer border-none bg-none"
            :aria-label="`关闭${toast.type === 'error' ? '错误' : '通知'}`"
            @click.stop="remove(toast.id)"
          >
            <X :size="14" :stroke-width="1.5" color="var(--color-ink-tertiary)" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { X } from "lucide-vue-next";
import { useToast } from "@/composables/useToast";

const { toasts, remove } = useToast();
</script>
