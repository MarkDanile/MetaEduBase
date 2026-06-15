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
        @click="emit('update:active-tab', tab.key)"
      >
        <span :class="activeTab === tab.key ? 'relative after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-[var(--color-accent)] after:rounded-t' : ''">
          {{ tab.label }}
        </span>
      </button>
    </div>

    <!-- Tab 1: Structured extraction -->
    <div v-if="activeTab === 'structured'">
      <!-- REQ-002-3 AC-12: 溯源元信息卡（仅在 template.id 存在时显示；老数据 / layer none 不显示） -->
      <div
        v-if="templateMeta !== null"
        class="p-3 mb-3 rounded-lg border border-[var(--color-border)] flex flex-wrap gap-3 text-[var(--text-small)]"
        data-testid="template-source-meta"
      >
        <span>
          <span class="text-[var(--color-ink-tertiary)]">模板 ID：</span>
          <code class="text-[var(--color-ink)]">{{ templateMeta.id }}</code>
        </span>
        <span>
          <span class="text-[var(--color-ink-tertiary)]">版本：</span>
          <span class="text-[var(--color-ink)]">{{ templateMeta.version ?? '-' }}</span>
        </span>
        <span v-if="templateMeta.layer !== 'none'">
          <span class="text-[var(--color-ink-tertiary)]">命中：</span>
          <span class="text-[var(--color-ink)] font-medium">{{ templateMeta.layer }}</span>
        </span>
        <span v-else>
          <span class="text-[var(--color-ink-tertiary)]">未命中：</span>
          <span class="text-[var(--color-ink)]">{{ templateMeta.reason || '无匹配模板' }}</span>
        </span>
      </div>
      <EmptyState
        v-if="!filteredTemplateData || Object.keys(filteredTemplateData).length === 0"
        title="暂无结构化数据"
        hint="等待模板抽取任务完成"
      />
      <div v-else class="p-3 rounded-lg border border-[var(--color-border)] space-y-1">
        <!-- String(key) keeps the contract narrow if templateData ever becomes Record<string | number, unknown> (TD-029). -->
        <!-- BUG-006 #1: 顶层传 templates + field-key 让 FieldValue 递归子时能查 children.label + 走 dot-path -->
        <FieldValue
          v-for="(value, key) in filteredTemplateData"
          :key="key"
          :label="getFieldLabel(String(key))"
          :field-key="String(key)"
          :templates="templates"
          :value="value"
          :depth="0"
        />
      </div>
    </div>

    <!-- Tab 2: Chunks -->
    <div v-if="activeTab === 'chunks'">
      <LoadingSpinner v-if="chunksLoading" text="加载切片..." />
      <EmptyState v-else-if="chunks.length === 0" title="暂无切片" hint="等待切片任务完成" />
      <div v-else class="space-y-2">
        <div
          v-for="chunk in chunks"
          :id="`chunk-${chunk.id}`"
          :key="chunk.id"
          class="p-3 rounded-lg border transition-colors duration-700"
          :class="
            chunk.id === highlightChunkId
              ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)]'
              : 'border-[var(--color-border)] hover:bg-[var(--color-bg-hover)]'
          "
        >
          <div class="flex items-start justify-between gap-3 mb-1">
            <div class="flex items-center gap-2">
              <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">#{{ chunk.chunk_index }}</span>
              <span class="text-[var(--text-caption)] text-[var(--color-ink)] font-medium">
                {{ chunk.section_title || '无标题' }}
              </span>
              <span v-if="chunk.section_path" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                {{ chunk.section_path }}
              </span>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span
                :class="chunk.has_embedding ? 'ui-tag-green' : 'ui-tag-amber'"
                class="text-[var(--text-micro)]"
              >
                {{ chunk.has_embedding ? '已向量化' : '未向量化' }}
              </span>
              <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                {{ chunk.content.length }} 字
              </span>
            </div>
          </div>
          <p class="text-[var(--text-caption)] text-[var(--color-ink-secondary)] line-clamp-3">
            {{ chunk.content }}
          </p>
        </div>
      </div>
    </div>

    <!-- Tab 3: Knowledge graph -->
    <div v-if="activeTab === 'kg'">
      <LoadingSpinner v-if="kgLoading" text="加载知识图谱..." />
      <EmptyState v-else-if="kgNodes.length === 0" title="暂无知识节点" hint="等待知识图谱抽取任务完成" />
      <div v-else class="relative">
        <KGGraph
          :nodes="kgNodes"
          :edges="kgEdges"
          :height="420"
          @node-click="emit('node-click', $event)"
        />
        <!-- Legend -->
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
import { computed } from "vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import KGGraph from "@/components/KGGraph.vue";
import FieldValue from "./FieldValue.vue";
import { getTemplateStructuredData, TEMPLATE_META_RESERVED_KEYS } from "@metaedu/shared/schemas/document";
import { getTemplateFieldLabel } from "@/utils/templateLabels";
import type { ChunkDTO } from "@/services/document";
import type { Template } from "@/services/template";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";

const props = defineProps<{
  activeTab: string;
  templates: Template[];
  chunks: ChunkDTO[];
  chunksLoading: boolean;
  kgNodes: KnowledgeNodeDTO[];
  kgEdges: KnowledgeEdgeDTO[];
  kgLoading: boolean;
  structuredData: unknown;
  highlightChunkId?: string | null;
}>();

const emit = defineEmits<{
  "update:active-tab": [val: string];
  "node-click": [node: KnowledgeNodeDTO];
}>();

const tabs = [
  { key: "structured", label: "结构化抽取" },
  { key: "chunks", label: "切片列表" },
  { key: "kg", label: "知识图谱" },
];

const templateData = computed(() => getTemplateStructuredData(props.structuredData as Parameters<typeof getTemplateStructuredData>[0]));

// REQ-002-3 AC-11: 6 个溯源保留键不入字段列表（用户在 Tab 1 只看到 LLM 抽取字段）。
// Single source of truth: TEMPLATE_META_RESERVED_KEYS from @metaedu/shared/schemas/document.
// Python codegen path tracked in TD-043.
const filteredTemplateData = computed<Record<string, unknown>>(() => {
  const t = templateData.value;
  if (!t || typeof t !== "object") return {};
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(t)) {
    if (!TEMPLATE_META_RESERVED_KEYS.has(k)) {
      out[k] = v;
    }
  }
  return out;
});

// REQ-002-3 AC-12: 溯源元信息卡数据源。注意：这里直接读 props.structuredData.template，
// 故意不走 getTemplateStructuredData() 那个 helper —— 因为 Task 6 已经在 v-for 之前
// 过滤了保留键，共享同一个 helper 会让"取保留键用于卡渲染"和"过滤保留键用于字段渲染"
// 互相打架；独立读 props 既能拿到保留键，也明确表达"渲染元信息卡是另一条数据通路"。
type TemplateMeta = {
  id: string;
  version: number | null;
  layer: string;
  matched_type: string | null;
  confidence: number | null;
  reason: string | null;
};

const templateMeta = computed<TemplateMeta | null>(() => {
  const sd = props.structuredData as
    | { template?: Record<string, unknown> | null }
    | null
    | undefined;
  const t = sd?.template;
  if (!t || typeof t !== "object") return null;
  if (!("id" in t) || typeof t.id !== "string" || t.id === "") return null;
  return {
    id: t.id,
    version: (t.version as number | null | undefined) ?? null,
    layer: (t.layer as string | undefined) ?? "none",
    matched_type: (t.matched_type as string | null | undefined) ?? null,
    confidence: (t.confidence as number | null | undefined) ?? null,
    reason: (t.reason as string | null | undefined) ?? null,
  };
});

// --- Structured data helpers (private to this component) ---
// BUG-006 #1: 委托给 utils/templateLabels.ts 公共模块 (含 children 递归 + dot-path)
function getFieldLabel(key: string, prefix: string = ""): string {
  return getTemplateFieldLabel(props.templates, key, prefix);
}
</script>
