<template>
  <div class="panel" :data-testid="testid">
    <div class="panel-title" :class="toneClass">{{ title }}</div>
    <ul v-if="items && items.length > 0" class="bullet-list">
      <li v-for="(item, i) in items" :key="i" class="bullet-item">{{ item }}</li>
    </ul>
    <p v-else class="bullet-empty" :data-testid="`${testid}-empty`">无</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{
  title: string;
  items?: string[];
  testid: string;
  tone?: "default" | "risk" | "review";
}>(), {
  items: () => [],
  tone: "default",
});

const toneClass = computed(() => ({
  "tone-risk": props.tone === "risk",
  "tone-review": props.tone === "review",
}));
</script>

<style scoped>
.panel {
  background: #ffffff;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
  margin-bottom: 10px;
}
.panel-title.tone-risk {
  color: #b91c1c;
}
.panel-title.tone-review {
  color: #b45309;
}
.bullet-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding-left: 18px;
}
.bullet-item {
  font-size: 13px;
  color: var(--color-ink);
  line-height: 1.6;
}
.bullet-empty {
  font-size: 13px;
  color: var(--color-ink-tertiary);
  margin: 0;
}
</style>
