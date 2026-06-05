<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader :title="file?.filename ?? '文件详情'" subtitle="处理状态与数据预览">
      <template #extra>
        <div class="flex gap-2 mt-2">
          <button class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5" @click="goBack">
            <ArrowLeft :size="14" /> 返回
          </button>
          <button class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5" @click="reinitializeMutation.mutate()">
            <RefreshCw :size="14" /> 重新初始化
          </button>
          <button
            class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5 text-red-500"
            @click="showDelete = true"
          >
            <Trash2 :size="14" /> 删除
          </button>
        </div>
      </template>
    </PageHeader>

    <LoadingSpinner v-if="fileQuery.isLoading.value" text="加载文件..." />

    <template v-else-if="file">
      <!-- File meta bar -->
      <div class="ui-panel p-4 mb-4 flex flex-wrap items-center gap-4">
        <div class="flex items-center gap-2">
          <FileText :size="18" class="text-[var(--color-accent)]" />
          <span class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">{{ file.filename }}</span>
        </div>
        <span class="ui-tag-blue text-[var(--text-micro)]">{{ file.doc_type || file.file_type }}</span>
        <span :class="statusTagClass(file.status)">{{ statusLabel(file.status) }}</span>
        <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatSize(file.file_size) }}</span>
        <div v-if="file.tags?.length" class="flex gap-1">
          <span v-for="tag in file.tags" :key="tag" class="ui-tag-purple text-[var(--text-micro)]">{{ tag }}</span>
        </div>
      </div>

      <!-- Pipeline status -->
      <div class="ui-panel p-4 mb-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">处理流水线</h3>
          <div class="flex items-center gap-2">
            <span v-if="polling" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">自动刷新中...</span>
            <button class="ui-btn-ghost px-2 py-1" @click="refreshAll">
              <RefreshCw :size="14" :class="{ 'animate-spin': loadingTasks || fileQuery.isFetching.value }" />
            </button>
          </div>
        </div>

        <LoadingSpinner v-if="loadingTasks" text="加载任务..." />
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
              @click="retryMutation.mutate()"
            >
              重试
            </button>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="ui-panel p-4">
        <div class="flex gap-1 mb-4 border-b border-[var(--color-border)]">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="px-4 py-2 text-[var(--text-caption)] border-b-2 transition-colors bg-none border-none cursor-pointer relative"
            :class="activeTab === tab.key
              ? 'border-[var(--color-accent)] text-[var(--color-accent)] font-medium'
              : 'border-transparent text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)]'"
            @click="activeTab = tab.key"
          >
            <span :class="activeTab === tab.key ? 'relative after:absolute after:bottom-0 after:left-0 after:right-0 after:h-0.5 after:bg-[var(--color-accent)] after:rounded-t' : ''">
              {{ tab.label }}
            </span>
          </button>
        </div>

        <!-- Tab 1: Structured extraction -->
        <div v-if="activeTab === 'structured'">
          <EmptyState
            v-if="!templateData || Object.keys(templateData).length === 0"
            title="暂无结构化数据"
            hint="等待模板抽取任务完成"
          />
          <div v-else class="p-3 rounded-lg border border-[var(--color-border)] space-y-1">
            <FieldValue
              v-for="(value, key) in templateData"
              :key="key"
              :label="templateFieldLabel(key)"
              :value="value"
              :depth="0"
            />
          </div>
        </div>

        <!-- Tab 2: Chunks -->
        <div v-if="activeTab === 'chunks'">
          <LoadingSpinner v-if="chunksQuery.isFetching.value" text="加载切片..." />
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
          <LoadingSpinner v-if="kgQuery.isFetching.value" text="加载知识图谱..." />
          <EmptyState v-else-if="kgNodes.length === 0" title="暂无知识节点" hint="等待知识图谱抽取任务完成" />
          <div v-else class="relative">
            <KGGraph
              :nodes="kgNodes"
              :edges="kgEdges"
              :height="420"
              @node-click="selectedKgNode = $event"
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

    <!-- Delete dialog -->
    <ConfirmDialog
      v-model:open="showDelete"
      title="删除文件"
      :message="`确定删除文件「${file?.filename}」？此操作不可恢复。`"
      @confirm="deleteMutation.mutate()"
    />

    <!-- KG node detail panel -->
    <KGDetailPanel
      :node="selectedKgNode"
      :edges="kgEdges"
      :nodes="kgNodes"
      @close="selectedKgNode = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft, FileText, Trash2, RefreshCw,
  FileSearch, Scissors, Cpu, Search, LayoutTemplate,
} from "lucide-vue-next";
import type { Component } from "vue";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import KGGraph from "@/components/KGGraph.vue";
import KGDetailPanel from "@/components/KGDetailPanel.vue";
import FieldValue from "./FieldValue.vue";
import { useToast } from "@/composables/useToast";
import { type FileDTO, type ChunkDTO, type TaskDTO } from "@/services/document";
import { type KnowledgeNodeDTO, type KnowledgeEdgeDTO } from "@/services/knowledge";
import { type Template } from "@/services/template";
import { DOC_TASK_STEPS, TASK_STATUS_MAP, FILE_STATUS_MAP } from "@/constants/pipeline";
import {
  useFileQuery,
  useFileTasksQuery,
  useFileChunksQuery,
  useFileKgQuery,
  useTemplatesQuery,
  useRetryTasksMutation,
  useReinitializeFileMutation,
  useDeleteFileMutation,
  fileKeys,
} from "@/views/resource/queries";
import { useQueryClient } from "@tanstack/vue-query";

const route = useRoute();
const router = useRouter();
const toast = useToast();

const fileId = computed(() => route.params.id as string);

// --- State ---
const selectedKgNode = ref<KnowledgeNodeDTO | null>(null);
const activeTab = ref("structured");
const showDelete = ref(false);

const tabs = [
  { key: "structured", label: "结构化抽取" },
  { key: "chunks", label: "切片列表" },
  { key: "kg", label: "知识图谱" },
];

// --- Queries (Vue Query) ---
const queryClient = useQueryClient();
const fileQuery = useFileQuery(fileId);
const file = computed<FileDTO | null>(() => fileQuery.data.value ?? null);

const tasksQuery = useFileTasksQuery(fileId);
const tasks = computed<TaskDTO[]>(() => tasksQuery.data.value ?? []);
const loadingTasks = computed(() => tasksQuery.isFetching.value);
const polling = computed(() =>
  tasks.value.some((t) => t.status === "running" || t.status === "pending"),
);

const chunksQuery = useFileChunksQuery(
  fileId,
  // Lazy-load: only fetch chunks when the chunks tab is active.
  computed(() => activeTab.value === "chunks"),
);
const chunks = computed<ChunkDTO[]>(() => chunksQuery.data.value ?? []);

const kgQuery = useFileKgQuery(
  fileId,
  // Lazy-load: only fetch kg when the kg tab is active.
  computed(() => activeTab.value === "kg"),
);
const kgNodes = computed<KnowledgeNodeDTO[]>(() => kgQuery.data.value?.nodes ?? []);
const kgEdges = computed<KnowledgeEdgeDTO[]>(() => kgQuery.data.value?.edges ?? []);

const templatesQuery = useTemplatesQuery();
const templates = computed<Template[]>(() => templatesQuery.data.value ?? []);

// --- Mutations (Vue Query) ---
const retryMutation = useRetryTasksMutation(fileId, () => {
  toast.success("已重新提交任务");
});
const reinitializeMutation = useReinitializeFileMutation(fileId, () => {
  toast.success("已开始重新初始化");
  // Clear stale chunks/kg caches so the next tab switch re-fetches.
  // The legacy behavior was to reset the local refs; with Vue Query we
  // remove the cached entries and let the active-tab query refetch on
  // next access.
  queryClient.removeQueries({ queryKey: fileKeys.chunks(fileId.value) });
  queryClient.removeQueries({ queryKey: fileKeys.kg(fileId.value) });
});
const deleteMutation = useDeleteFileMutation(fileId, () => {
  toast.success("文件已删除");
  router.push("/resource");
});

// --- Structured data helpers ---
const templateData = computed(() => {
  if (!file.value?.structured_data) return null;
  return (file.value.structured_data as Record<string, unknown>)["template"] as Record<string, unknown> | null ?? null;
});

function templateFieldLabel(key: string): string {
  return getFieldLabel(key);
}

// --- Data loading (Vue Query) ---
async function refreshAll() {
  await Promise.all([
    fileQuery.refetch(),
    chunksQuery.refetch(),
    kgQuery.refetch(),
  ]);
}

function getFieldLabel(key: string): string {
  // Try to find a template field with matching key
  for (const t of templates.value) {
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

// --- Pipeline helpers ---
function taskByType(type: string) {
  return tasks.value.find((t) => t.task_type === type);
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

// --- File helpers ---
function statusLabel(status: string) {
  return FILE_STATUS_MAP[status]?.label ?? status;
}

function statusTagClass(status: string) {
  const color = FILE_STATUS_MAP[status]?.color ?? "blue";
  return `ui-tag-${color} text-[var(--text-micro)]`;
}

function formatSize(bytes: number | null) {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// --- Actions ---
function goBack() {
  router.push("/resource");
}

// --- Tab data loading ---
// Tab switching is handled by the `enabled` ref on each query; switching
// to a tab triggers a refetch via the `enabled` reactive computation. No
// explicit watch needed.

watch(polling, (now, prev) => {
  if (prev && !now) {
    // Tasks just finished — refresh file detail and the active tab's data.
    void fileQuery.refetch();
    if (activeTab.value === "chunks") void chunksQuery.refetch();
    if (activeTab.value === "kg") void kgQuery.refetch();
  }
});
</script>
