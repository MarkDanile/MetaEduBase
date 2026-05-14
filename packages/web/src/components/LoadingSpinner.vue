<template>
  <div class="py-20 text-center" role="status" aria-live="polite">
    <div class="inline-flex items-center gap-2 text-[var(--color-ink-tertiary)] text-[var(--text-body)]">
      <Loader2 :size="16" class="animate-spin" aria-hidden="true" />
      <span>{{ text }}</span>
    </div>
    <span class="sr-only">加载中</span>
  </div>
</template>

<script setup lang="ts">
import { Loader2 } from "lucide-vue-next";

withDefaults(defineProps<{
  text?: string;
}>(), {
  text: "加载中...",
});
</script>
