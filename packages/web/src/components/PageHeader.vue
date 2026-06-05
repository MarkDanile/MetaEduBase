<template>
  <div class="ui-page-section">
    <slot name="greeting" />
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="min-w-0">
        <h1 class="text-[var(--text-page-title)] font-semibold tracking-tight leading-tight">
          <slot name="title">{{ title }}</slot>
        </h1>
        <p v-if="subtitle" class="text-[var(--color-ink-tertiary)] mt-1 text-[var(--text-body)]">
          {{ subtitle }}
        </p>
      </div>
      <slot name="extra" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title?: string;
  subtitle?: string;
}>(), {
  title: "",
  subtitle: "",
});
</script>
