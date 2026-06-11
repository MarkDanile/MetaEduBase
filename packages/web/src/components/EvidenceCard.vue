<template>
  <div
    class="ui-panel p-2.5 text-[var(--text-caption)]"
    :class="{ 'cursor-pointer hover:bg-[var(--color-bg-warm)]': hasFile }"
    role="article"
    :aria-label="`Evidence ${index}`"
    @click="handleClick"
  >
    <div class="flex items-start gap-2">
      <span
        class="ui-tag ui-tag-blue shrink-0"
        :title="`Source ${index} — ${sourceLabel}`"
      >
        [{{ index }}]
      </span>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="font-medium text-[var(--color-ink)] truncate">
            {{ evidence.title || evidence.structured_path || evidence.evidence_id }}
          </span>
          <span class="ui-tag text-[10px]">{{ sourceLabel }}</span>
          <span
            v-for="ch in evidence.channels"
            :key="ch"
            class="ui-tag text-[10px] opacity-70"
            >{{ ch }}</span
          >
          <span
            v-if="evidence.score != null"
            class="opacity-50 text-[var(--text-micro)] ml-auto"
            >{{ (evidence.score * 100).toFixed(0) }}%</span
          >
        </div>
        <p
          v-if="evidence.snippet || evidence.content"
          class="text-[var(--color-ink-tertiary)] mt-1 line-clamp-2"
        >
          {{ evidence.snippet || evidence.content }}
        </p>
        <p
          v-if="hasFile"
          class="text-[var(--text-micro)] text-[var(--color-accent)] mt-1.5"
        >
          📎 查看源文件
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { EvidenceItem } from "@/types/evidence";

const props = defineProps<{
  index: number;
  evidence: EvidenceItem;
}>();

const emit = defineEmits<{
  (e: "open-file", evidence: EvidenceItem): void;
}>();

const SOURCE_TYPE_LABELS: Record<string, string> = {
  chunk: "原文切片",
  knowledge_node: "知识节点",
  knowledge_edge: "知识关系",
  structured_field: "结构化字段",
};

const sourceLabel = computed(
  () => SOURCE_TYPE_LABELS[props.evidence.source_type] || props.evidence.source_type
);

const hasFile = computed(() => !!props.evidence.file_id);

function handleClick() {
  if (hasFile.value) {
    emit("open-file", props.evidence);
  }
}
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
