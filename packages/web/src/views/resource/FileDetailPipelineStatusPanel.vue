<template>
  <div class="ui-panel p-4 mb-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">处理流水线</h3>
      <div class="flex items-center gap-2">
        <span v-if="polling" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">自动刷新中...</span>
        <button class="ui-btn-ghost px-2 py-1" @click="emit('refresh')">
          <RefreshCw :size="14" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

    <LoadingSpinner v-if="loading" text="加载任务..." />
    <div v-else class="flex gap-1">
      <div
        v-for="step in DOC_TASK_STEPS"
        :key="step.type"
        class="flex-1 flex flex-col items-center gap-1.5 py-2 px-1 rounded-lg transition-colors"
        :class="stepBgClass(step.type)"
      >
        <div class="flex items-center gap-1">
          <component :is="stepIcon(step.type)" :size="14" />
          <span v-if="stepStatus(step.type) === 'running'" class="text-[var(--text-micro)] text-[var(--color-accent)]">
            {{ stepProgress(step.type) }}%
          </span>
        </div>
        <span class="text-[var(--text-small)] text-[var(--color-ink-secondary)]">{{ step.label }}</span>
        <span :class="stepLabelClass(step.type)">{{ stepStatusLabel(step.type) }}</span>
        <button
          v-if="stepStatus(step.type) === 'failed'"
          class="text-[var(--text-micro)] text-[var(--color-accent)] hover:underline"
          @click="emit('retry')"
        >
          重试
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FileSearch, Scissors, Cpu, Search, LayoutTemplate, RefreshCw } from "lucide-vue-next";
import type { Component } from "vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { DOC_TASK_STEPS, TASK_STATUS_MAP } from "@/constants/pipeline";
import type { TaskDTO } from "@/services/document";

const props = defineProps<{
  tasks: TaskDTO[];
  polling: boolean;
  loading: boolean;
}>();

const emit = defineEmits<{
  "retry": [];
  "refresh": [];
}>();

// --- Pipeline helpers (private to this component) ---
function taskByType(type: string): TaskDTO | undefined {
  return props.tasks.find((t) => t.task_type === type);
}

function stepStatus(type: string) {
  return taskByType(type)?.status ?? "pending";
}

function stepProgress(type: string) {
  return taskByType(type)?.progress ?? 0;
}

function stepStatusLabel(type: string) {
  return TASK_STATUS_MAP[stepStatus(type)]?.label ?? "等待中";
}

const stepIconMap: Record<string, Component> = {
  FileSearch, Scissors, Cpu, Search, LayoutTemplate,
};

function stepIcon(type: string): Component {
  const step = DOC_TASK_STEPS.find((s) => s.type === type);
  return stepIconMap[step?.icon ?? ""] ?? FileSearch;
}

function stepBgClass(type: string) {
  const s = stepStatus(type);
  if (s === "success") return "bg-[var(--color-accent-bg)]";
  if (s === "running") return "bg-[var(--color-accent-bg)]";
  if (s === "failed") return "bg-red-50 dark:bg-red-950/20";
  return "";
}

function stepLabelClass(type: string) {
  const color = TASK_STATUS_MAP[stepStatus(type)]?.color ?? "amber";
  return `ui-tag-${color} text-[var(--text-micro)]`;
}
</script>
