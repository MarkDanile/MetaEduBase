<template>
  <div class="mb-8 animate-slide-up" :class="staggerClass">
    <slot name="greeting" />
    <h1 class="text-[var(--font-page-title)] font-semibold tracking-tight" style="letter-spacing:-0.5px">
      <slot name="title">{{ title }}</slot>
    </h1>
    <p v-if="subtitle" class="text-[13px] text-[var(--color-ink-tertiary)] mt-1">{{ subtitle }}</p>
    <div class="wet-line mt-2.5" :style="{ width: lineWidth + 'px' }"></div>
    <slot name="extra" />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{
  title?: string;
  subtitle?: string;
  lineWidth?: number;
  stagger?: number;
}>(), {
  title: "",
  subtitle: "",
  lineWidth: 40,
  stagger: 0,
});

const staggerClass = computed(() =>
  props.stagger > 0 ? `stagger-${Math.min(props.stagger, 5)}` : ""
);
</script>
