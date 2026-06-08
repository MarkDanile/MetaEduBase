<template>
  <div class="ui-panel p-4">
    <div class="flex gap-1 mb-4 border-b border-[var(--color-border)]">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="px-4 py-2 text-[var(--text-caption)] border-b-2 transition-colors bg-none border-none cursor-pointer relative"
        :class="activeTab === tab.key
          ? 'border-[var(--color-accent)] text-[var(--color-accent)] font-medium'
          : 'border-transparent text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)]'"
        @click="emit('update:activeTab', tab.key)"
      >
        <span :class="activeTab === tab.key ? 'relative after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-[var(--color-accent)] after:rounded-t' : ''">
          {{ tab.label }}
        </span>
      </button>
    </div>

    <!-- Tab 1: Data preview -->
    <div v-if="activeTab === 'preview'">
      <LoadingSpinner v-if="loadingRows" text="加载数据..." />
      <EmptyState v-else-if="rows.length === 0" title="暂无数据" hint="等待数据解析任务完成" />
      <div v-else class="overflow-auto max-h-[400px]">
        <table class="w-full text-[var(--text-caption)]">
          <thead>
            <tr class="border-b border-[var(--color-border)] text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
              <th class="text-left py-2 px-2 font-medium">#</th>
              <th
                v-for="(col, idx) in selected.column_names"
                :key="idx"
                class="text-left py-2 px-2 font-medium"
              >
                {{ col }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in rows"
              :key="row.id"
              class="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-hover)]"
            >
              <td class="py-2 px-2 text-[var(--color-ink-tertiary)]">{{ row.row_index }}</td>
              <td
                v-for="(col, idx) in selected.column_names"
                :key="idx"
                class="py-2 px-2 text-[var(--color-ink-secondary)]"
              >
                {{ formatCell(row.data[col]) }}
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Pagination -->
        <div v-if="totalRows > pageSize" class="flex items-center justify-between mt-3 pt-2 border-t border-[var(--color-border)]">
          <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
            共 {{ totalRows }} 行
          </span>
          <div class="flex gap-1">
            <button
              class="ui-btn-ghost px-2 py-1 text-[var(--text-micro)]"
              :disabled="offset === 0"
              @click="emit('change-page', -1)"
            >
              上一页
            </button>
            <button
              class="ui-btn-ghost px-2 py-1 text-[var(--text-micro)]"
              :disabled="offset + pageSize >= totalRows"
              @click="emit('change-page', 1)"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 2: KG from this dataset -->
    <div v-if="activeTab === 'kg'">
      <LoadingSpinner v-if="loadingKg" text="加载知识图谱..." />
      <EmptyState v-else-if="kgNodes.length === 0" title="暂无知识节点" hint="等待知识图谱抽取任务完成" />
      <div v-else class="relative">
        <KGGraph
          :nodes="kgNodes"
          :edges="kgEdges"
          :height="420"
          @node-click="emit('node-click', $event)"
        />
        <div class="mt-2 flex flex-wrap gap-2">
          <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
            {{ kgNodes.length }} 节点 / {{ kgEdges.length }} 关系
          </span>
          <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">· 点击节点查看详情</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import KGGraph from "@/components/KGGraph.vue";
import type { DatasetDTO, DatasetRowDTO } from "@/services/structured-data";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";

defineProps<{
  selected: DatasetDTO;
  rows: DatasetRowDTO[];
  kgNodes: KnowledgeNodeDTO[];
  kgEdges: KnowledgeEdgeDTO[];
  totalRows: number;
  offset: number;
  pageSize: number;
  loadingRows: boolean;
  loadingKg: boolean;
  activeTab: string;
}>();

const emit = defineEmits<{
  "update:activeTab": [key: string];
  "change-page": [delta: number];
  "node-click": [node: KnowledgeNodeDTO];
}>();

const tabs = [
  { key: "preview", label: "数据预览" },
  { key: "kg", label: "知识图谱(本表)" },
];

// --- Cell formatter (private) ---
function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 0);
}
</script>
