<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader :title="file?.filename ?? '文件详情'" subtitle="处理状态与数据预览">
      <template #extra>
        <div class="flex gap-2 mt-2">
          <button class="liquid-btn-ghost px-3 py-1.5 flex items-center gap-1.5" @click="goBack">
            <ArrowLeft :size="14" /> 返回
          </button>
          <button class="liquid-btn-ghost px-3 py-1.5 flex items-center gap-1.5" @click="reinitialize">
            <RefreshCw :size="14" /> 重新初始化
          </button>
          <button
            class="liquid-btn-ghost px-3 py-1.5 flex items-center gap-1.5 text-red-500"
            @click="showDelete = true"
          >
            <Trash2 :size="14" /> 删除
          </button>
        </div>
      </template>
    </PageHeader>

    <LoadingSpinner v-if="loading" text="加载文件..." />

    <template v-else-if="file">
      <!-- File meta bar -->
      <div class="liquid-card p-4 mb-4 flex flex-wrap items-center gap-4">
        <div class="flex items-center gap-2">
          <FileText :size="18" class="text-[var(--color-accent)]" />
          <span class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">{{ file.filename }}</span>
        </div>
        <span class="liquid-tag-blue text-[var(--text-micro)]">{{ file.doc_type || file.file_type }}</span>
        <span :class="statusTagClass(file.status)">{{ statusLabel(file.status) }}</span>
        <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatSize(file.file_size) }}</span>
        <div v-if="file.tags?.length" class="flex gap-1">
          <span v-for="tag in file.tags" :key="tag" class="liquid-tag-purple text-[var(--text-micro)]">{{ tag }}</span>
        </div>
      </div>

      <!-- Pipeline status -->
      <div class="liquid-card p-4 mb-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">处理流水线</h3>
          <div class="flex items-center gap-2">
            <span v-if="polling" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">自动刷新中...</span>
            <button class="liquid-btn-ghost px-2 py-1" @click="refreshAll">
              <RefreshCw :size="14" :class="{ 'animate-spin': loadingTasks || loading }" />
            </button>
          </div>
        </div>

        <LoadingSpinner v-if="loadingTasks" text="加载任务..." />
        <div v-else class="flex gap-1">
          <div
            v-for="(step, idx) in DOC_TASK_STEPS"
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
              @click="retryTasks"
            >
              重试
            </button>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="liquid-card p-4">
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
          <div v-else class="space-y-3">
            <div
              v-for="(value, key) in templateData"
              :key="key"
              class="p-3 rounded-lg border border-[var(--color-border)]"
            >
              <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1">{{ templateFieldLabel(key) }}</p>
              <p class="text-[var(--text-caption)] text-[var(--color-ink)]">{{ formatTemplateValue(value) }}</p>
            </div>
          </div>
        </div>

        <!-- Tab 2: Chunks -->
        <div v-if="activeTab === 'chunks'">
          <LoadingSpinner v-if="loadingChunks" text="加载切片..." />
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
                    :class="chunk.has_embedding ? 'liquid-tag-green' : 'liquid-tag-amber'"
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
          <LoadingSpinner v-if="loadingKg" text="加载知识图谱..." />
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
      @confirm="doDelete"
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
import { ref, onMounted, onUnmounted, computed, watch } from "vue";
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
import { useToast } from "@/composables/useToast";
import { documentApi, type FileDTO, type ChunkDTO, type TaskDTO } from "@/services/document";
import { knowledgeApi, type KnowledgeNodeDTO, type KnowledgeEdgeDTO } from "@/services/knowledge";
import { DOC_TASK_STEPS, TASK_STATUS_MAP, FILE_STATUS_MAP } from "@/constants/pipeline";

const route = useRoute();
const router = useRouter();
const toast = useToast();

const fileId = computed(() => route.params.id as string);

// --- State ---
const file = ref<FileDTO | null>(null);
const tasks = ref<TaskDTO[]>([]);
const chunks = ref<ChunkDTO[]>([]);
const kgNodes = ref<KnowledgeNodeDTO[]>([]);
const kgEdges = ref<KnowledgeEdgeDTO[]>([]);
const selectedKgNode = ref<KnowledgeNodeDTO | null>(null);
const loading = ref(true);
const loadingTasks = ref(false);
const loadingChunks = ref(false);
const loadingKg = ref(false);
const activeTab = ref("structured");
const showDelete = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const tabs = [
  { key: "structured", label: "结构化抽取" },
  { key: "chunks", label: "切片列表" },
  { key: "kg", label: "知识图谱" },
];

const polling = computed(() => tasks.value.some((t) => t.status === "running" || t.status === "pending"));

// --- Structured data helpers ---
const templateData = computed(() => {
  if (!file.value?.structured_data) return null;
  return (file.value.structured_data as Record<string, unknown>)["template"] as Record<string, unknown> | null ?? null;
});

function templateFieldLabel(key: string): string {
  const labels: Record<string, string> = {
    course_name: "课程名称",
    chapter: "章节",
    objectives: "教学目标",
    key_points: "重点",
    difficulties: "难点",
    methods: "教学方法",
    duration: "课时",
    title: "文档标题",
    summary: "摘要",
    sections: "主要章节",
    keywords: "关键词",
  };
  return labels[key] ?? key;
}

function formatTemplateValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value || "-";
  if (Array.isArray(value)) {
    if (value.length === 0) return "-";
    return value.map((v) => String(v)).join("、");
  }
  return JSON.stringify(value);
}

// --- Data loading ---
async function loadFile() {
  loading.value = true;
  try {
    const { data } = await documentApi.getFile(fileId.value);
    file.value = data;
  } catch {
    toast.error("加载文件失败");
  } finally {
    loading.value = false;
  }
}

async function loadTasks() {
  loadingTasks.value = true;
  try {
    const { data } = await documentApi.listTasks(fileId.value);
    tasks.value = data;
  } catch {
    toast.error("加载任务失败");
  } finally {
    loadingTasks.value = false;
  }
}

async function refreshAll() {
  loadingTasks.value = true;
  loading.value = true;
  try {
    await Promise.all([loadFile(), loadTasks()]);
    if (activeTab.value === "chunks") await loadChunks();
    if (activeTab.value === "kg") await loadKg();
  } finally {
    loadingTasks.value = false;
    loading.value = false;
  }
}

async function loadChunks() {
  loadingChunks.value = true;
  try {
    const { data } = await documentApi.listChunks(fileId.value);
    chunks.value = data;
  } catch {
    toast.error("加载切片失败");
  } finally {
    loadingChunks.value = false;
  }
}

async function loadKg() {
  loadingKg.value = true;
  try {
    const [nodesRes, edgesRes] = await Promise.all([
      knowledgeApi.listNodes({ source_file_id: fileId.value }),
      knowledgeApi.listEdges({ source_file_id: fileId.value }),
    ]);
    kgNodes.value = nodesRes.data;
    kgEdges.value = edgesRes.data;
  } catch {
    toast.error("加载知识图谱失败");
  } finally {
    loadingKg.value = false;
  }
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
  return `liquid-tag-${color} text-[var(--text-micro)]`;
}

// --- File helpers ---
function statusLabel(status: string) {
  return FILE_STATUS_MAP[status]?.label ?? status;
}

function statusTagClass(status: string) {
  const color = FILE_STATUS_MAP[status]?.color ?? "blue";
  return `liquid-tag-${color} text-[var(--text-micro)]`;
}

function formatSize(bytes: number | null) {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatJsonValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 0);
}

// --- Actions ---
function goBack() {
  router.push("/resource");
}

async function retryTasks() {
  try {
    await documentApi.retryTasks(fileId.value);
    toast.success("已重新提交任务");
    await loadTasks();
  } catch {
    toast.error("重试失败");
  }
}

async function reinitialize() {
  try {
    await documentApi.reinitializeFile(fileId.value);
    toast.success("已开始重新初始化");
    await loadFile();
    await loadTasks();
    chunks.value = [];
    kgNodes.value = [];
    kgEdges.value = [];
    startPolling();
  } catch {
    toast.error("重新初始化失败");
  }
}

async function doDelete() {
  try {
    await documentApi.deleteFile(fileId.value);
    toast.success("文件已删除");
    router.push("/resource");
  } catch {
    toast.error("删除失败");
  }
}

// --- Tab data loading ---
watch(activeTab, () => {
  if (activeTab.value === "structured") loadFile();
  if (activeTab.value === "chunks") loadChunks();
  if (activeTab.value === "kg") loadKg();
});

// --- Auto-poll ---
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    await loadTasks();
    if (polling.value) return;
    // All tasks finished — refresh file data + all tabs
    stopPolling();
    await loadFile();
    await loadChunks();
    await loadKg();
  }, 3000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

// --- Init ---
onMounted(async () => {
  await loadFile();
  await loadTasks();
  startPolling();
});

onUnmounted(() => {
  stopPolling();
});
</script>
