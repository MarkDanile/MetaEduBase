<template>
  <div class="ui-panel p-6 text-center">
    <slot name="icon">
      <FileText :size="40" :stroke-width="1.25" class="mx-auto mb-4 text-[var(--color-ink-dim)]" aria-hidden="true" />
    </slot>
    <div class="max-w-[420px] mx-auto px-4">
      <p class="text-[var(--color-ink)] text-[var(--text-body)] font-medium">{{ title }}</p>
      <p v-if="hint" class="text-[var(--color-ink-tertiary)] mt-1">{{ hint }}</p>
    </div>
    <div class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { FileText } from "lucide-vue-next";

withDefaults(defineProps<{
  title: string;
  hint?: string;
}>(), {});
</script>
