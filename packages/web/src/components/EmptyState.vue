<template>
  <div class="py-16 text-center animate-slide-up stagger-1">
    <slot name="icon">
      <svg class="mx-auto mb-5" :width="iconWidth" :height="iconHeight" viewBox="0 0 80 60" fill="none">
        <rect x="8" y="4" width="64" height="48" rx="4" stroke="var(--color-border)" stroke-width="1.5"/>
        <line x1="8" y1="20" x2="72" y2="20" stroke="var(--color-border)" stroke-width="1"/>
        <line x1="8" y1="36" x2="72" y2="36" stroke="var(--color-border)" stroke-width="1"/>
        <rect x="16" y="9" width="12" height="7" rx="1.5" fill="var(--color-accent-bg)" stroke="var(--color-accent)" stroke-width="0.8"/>
        <rect x="32" y="9" width="16" height="7" rx="1.5" fill="var(--color-accent-bg)" stroke="var(--color-accent)" stroke-width="0.8"/>
        <rect x="16" y="25" width="20" height="7" rx="1.5" fill="var(--color-tag-green)" stroke="var(--color-tag-green-text)" stroke-width="0.8"/>
        <rect x="40" y="25" width="8" height="7" rx="1.5" fill="var(--color-tag-green)" stroke="var(--color-tag-green-text)" stroke-width="0.8"/>
        <rect x="16" y="41" width="14" height="7" rx="1.5" fill="var(--color-tag-amber)" stroke="var(--color-tag-amber-text)" stroke-width="0.8"/>
        <rect x="34" y="41" width="22" height="7" rx="1.5" fill="var(--color-tag-amber)" stroke="var(--color-tag-amber-text)" stroke-width="0.8"/>
      </svg>
    </slot>
    <p class="text-[var(--color-ink-secondary)] text-[14px] font-medium">{{ title }}</p>
    <p v-if="hint" class="text-[var(--color-ink-tertiary)] text-[12px] mt-1">{{ hint }}</p>
    <slot name="action" />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  title: string;
  hint?: string;
  iconWidth?: number;
  iconHeight?: number;
}>(), {
  iconWidth: 80,
  iconHeight: 60,
});
</script>
