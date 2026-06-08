<template>
  <div class="ui-panel p-4">
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <GitBranch :size="18" class="text-[var(--color-accent)]" />
        <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">知识图谱总览</h3>
        <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
          {{ nodes.length }} 节点 · {{ edges.length }} 关系
        </span>
      </div>
      <button
        class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5"
        :disabled="rebuilding"
        @click="emit('rebuild')"
      >
        <RefreshCw :size="14" :class="{ 'animate-spin': rebuilding }" />
        <span>{{ rebuilding ? '重建中...' : '重新生成' }}</span>
      </button>
    </div>

    <LoadingSpinner v-if="loading" text="加载知识图谱..." />
    <EmptyState v-else-if="nodes.length === 0" title="暂无知识图谱" hint="从数据集构建" />
    <div v-else class="relative">
      <KGGraph
        :nodes="nodes"
        :edges="edges"
        :height="560"
        @node-click="emit('node-click', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { GitBranch, RefreshCw } from "lucide-vue-next";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import KGGraph from "@/components/KGGraph.vue";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";

defineProps<{
  nodes: KnowledgeNodeDTO[];
  edges: KnowledgeEdgeDTO[];
  loading: boolean;
  rebuilding: boolean;
}>();

const emit = defineEmits<{
  "rebuild": [];
  "node-click": [node: KnowledgeNodeDTO];
}>();
</script>
