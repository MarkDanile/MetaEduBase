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
      <EmptyState
        v-if="!filteredTemplateData || Object.keys(filteredTemplateData).length === 0"
        title="暂无结构化数据"
        hint="等待模板抽取任务完成"
      />
      <div v-else class="p-3 rounded-lg border border-[var(--color-border)] space-y-1">
        <!-- String(key) keeps the contract narrow if templateData ever becomes Record<string | number, unknown> (TD-029). -->
        <FieldValue
          v-for="(value, key) in filteredTemplateData"
          :key="key"
          :label="templateFieldLabel(String(key))"
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
          :key="chunk.id"
          class="p-3 rounded-lg border border-[var(--color-border)] hover:bg-[var(--color-bg-hover)]"
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
import { getTemplateStructuredData } from "@metaedu/shared/schemas/document";
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
const RESERVED_META_KEYS: ReadonlySet<string> = new Set([
  "id",
  "version",
  "layer",
  "matched_type",
  "confidence",
  "reason",
]);

const filteredTemplateData = computed<Record<string, unknown>>(() => {
  const t = templateData.value;
  if (!t || typeof t !== "object") return {};
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(t)) {
    if (!RESERVED_META_KEYS.has(k)) {
      out[k] = v;
    }
  }
  return out;
});

// --- Structured data helpers (private to this component) ---
function templateFieldLabel(key: string): string {
  return getFieldLabel(key);
}

function getFieldLabel(key: string): string {
  // Try to find a template field with matching key
  for (const t of props.templates) {
    const field = t.fields.find((f) => f.key === key);
    if (field) return field.label;
  }
  // Fallback to hard-coded map
  const labels: Record<string, string> = {
    course_name: "课程名称",
    course_code: "课程代码",
    semester: "授课学期",
    department: "开课单位",
    teacher: "主讲教师",
    target_class: "授课班级",
    total_hours: "课程总学时",
    theory_hours: "理论学时",
    practice_hours: "实践学时",
    exam_mode: "考核方式",
    textbook: "教材及参考书",
    course_description: "课程简介",
    teaching_objectives: "教学目标",
    teaching_content_outline: "教学内容纲要",
    teaching_schedule: "教学进度安排",
    evaluation_plan: "课程评价方案",
    title: "文档标题",
    summary: "摘要",
    sections: "主要章节",
    keywords: "关键词",
  };
  return labels[key] ?? key;
}
</script>
