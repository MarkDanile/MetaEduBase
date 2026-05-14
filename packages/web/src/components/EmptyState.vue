<template>
  <div class="py-12 text-center animate-slide-up stagger-1">
    <slot name="icon">
      <FileText :size="48" :stroke-width="1" class="mx-auto mb-5 text-[var(--color-border)]" aria-hidden="true" />
    </slot>
    <div class="max-w-[420px] mx-auto px-4">
      <p class="text-[var(--color-ink-secondary)] text-[var(--text-body)] font-medium">{{ title }}</p>
      <p v-if="hint" class="text-[var(--color-ink-tertiary)] mt-1">{{ hint }}</p>
    </div>
    <slot name="action" />
  </div>
</template>

<script setup lang="ts">
import { FileText } from "lucide-vue-next";

withDefaults(defineProps<{
  title: string;
  hint?: string;
}>(), {});
</script>
