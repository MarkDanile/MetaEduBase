<template>
  <div class="space-y-2 border-l-2 border-[var(--color-accent)] pl-3" data-testid="document-source-list">
    <div
      v-for="source in sources"
      :key="source.file_id"
      class="border border-[var(--color-border-subtle)] rounded-[var(--radius-md)] bg-[var(--color-bg-warm)]"
    >
      <div class="flex items-start gap-2 p-2.5">
        <button
          type="button"
          class="ui-btn ui-btn-ghost w-7 h-7 !p-0 !rounded-[var(--radius-sm)] shrink-0"
          :aria-label="isExpanded(source.file_id) ? '收起命中片段' : '展开命中片段'"
          :disabled="source.chunks.length === 0"
          @click="toggle(source.file_id)"
        >
          <ChevronDown
            :size="14"
            :class="['transition-transform', isExpanded(source.file_id) ? 'rotate-180' : '']"
          />
        </button>

        <div class="flex-1 min-w-0">
          <button
            type="button"
            class="text-left font-medium text-[var(--color-ink)] hover:text-[var(--color-accent)] truncate block max-w-full"
            @click="$emit('open-document', source)"
          >
            {{ source.title || source.file_name || source.file_id }}
          </button>
          <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
            <span v-if="source.doc_type" class="ui-tag">{{ source.doc_type }}</span>
            <span class="ui-tag">{{ source.chunks.length }} 个片段</span>
            <span
              v-for="channel in source.channels"
              :key="channel"
              class="ui-tag opacity-75"
            >
              {{ channel }}
            </span>
            <span v-if="source.best_score != null" class="ml-auto">
              {{ (source.best_score * 100).toFixed(0) }}%
            </span>
          </div>
        </div>

        <button
          type="button"
          class="ui-btn ui-btn-ghost w-7 h-7 !p-0 !rounded-[var(--radius-sm)] shrink-0"
          aria-label="查看文档"
          @click="$emit('open-document', source)"
        >
          <ExternalLink :size="14" />
        </button>
      </div>

      <div
        v-if="isExpanded(source.file_id) && source.chunks.length > 0"
        class="px-2.5 pb-2.5 space-y-1.5"
      >
        <button
          v-for="chunk in source.chunks"
          :key="`${source.file_id}-${chunk.evidence_index}-${chunk.chunk_id ?? 'no-chunk'}`"
          type="button"
          data-testid="document-source-chunk"
          aria-label="定位到该 chunk"
          class="w-full text-left p-2 rounded-[var(--radius-sm)] bg-[var(--color-bg-elevated)] border border-[var(--color-border-subtle)] hover:border-[var(--color-accent)]"
          @click="$emit('open-chunk', source, chunk)"
        >
          <div class="flex items-center gap-1.5 text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
            <span class="ui-tag ui-tag-blue">[{{ chunk.evidence_index }}]</span>
            <span v-if="chunk.chunk_index != null">Chunk {{ chunk.chunk_index }}</span>
            <span v-if="chunk.title" class="truncate">{{ chunk.title }}</span>
          </div>
          <p class="mt-1 text-[var(--text-caption)] text-[var(--color-ink-secondary)] line-clamp-2">
            {{ chunk.snippet }}
          </p>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { ChevronDown, ExternalLink } from "lucide-vue-next";
import type { DocumentSource, DocumentSourceChunk } from "@/types/evidence";

defineProps<{
  sources: DocumentSource[];
}>();

defineEmits<{
  (e: "open-document", source: DocumentSource): void;
  (e: "open-chunk", source: DocumentSource, chunk: DocumentSourceChunk): void;
}>();

const expanded = ref<Set<string>>(new Set());

function isExpanded(fileId: string): boolean {
  return expanded.value.has(fileId);
}

function toggle(fileId: string) {
  const next = new Set(expanded.value);
  if (next.has(fileId)) {
    next.delete(fileId);
  } else {
    next.add(fileId);
  }
  expanded.value = next;
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
