<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader title="数据库" subtitle="数据集管理与知识图谱构建">
      <template #extra>
        <button class="liquid-btn-primary px-3 py-1.5 flex items-center gap-1.5" @click="showUpload = true">
          <Upload :size="14" /> 上传数据集
        </button>
      </template>
    </PageHeader>

    <div class="flex gap-4">
      <!-- Left panel: dataset list -->
      <div class="w-[260px] shrink-0 flex flex-col gap-3">
        <div class="liquid-card p-3 flex flex-col gap-2">
          <div class="flex items-center justify-between">
            <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">数据集列表</span>
            <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">{{ datasets.length }} 个</span>
          </div>

          <LoadingSpinner v-if="loading" text="加载中..." />

          <template v-else>
            <EmptyState v-if="datasets.length === 0" title="暂无数据集" hint="上传 Excel 文件创建数据集" compact />

            <div v-else class="flex flex-col gap-1">
              <button
                v-for="ds in datasets"
                :key="ds.id"
                class="w-full text-left px-2 py-2 rounded-lg transition-colors text-[var(--text-caption)]"
                :class="selectedId === ds.id
                  ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-ink-secondary)]'"
                @click="selectDataset(ds)"
              >
                <div class="flex items-center justify-between gap-2">
                  <span class="truncate font-medium">{{ ds.name }}</span>
                  <span :class="dsStatusTagClass(ds.status)" class="text-[var(--text-micro)] shrink-0">{{ dsStatusLabel(ds.status) }}</span>
                </div>
                <div class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-0.5">
                  {{ ds.row_count }} 行 · {{ ds.column_names?.length ?? 0 }} 列
                </div>
              </button>
            </div>
          </template>
        </div>

        <!-- KG overview button -->
        <button
          class="liquid-card p-3 flex items-center justify-between text-[var(--text-caption)] hover:bg-[var(--color-bg-hover)] transition-colors cursor-pointer"
          @click="showKgOverview = true"
        >
          <div class="flex items-center gap-2">
            <GitBranch :size="14" class="text-[var(--color-accent)]" />
            <span class="text-[var(--color-ink-secondary)]">知识图谱总览</span>
          </div>
          <ChevronRight :size="14" class="text-[var(--color-ink-tertiary)]" />
        </button>
      </div>

      <!-- Right panel: dataset detail -->
      <div class="flex-1 min-w-0">
        <LoadingSpinner v-if="loadingDetail" text="加载数据集..." />

        <template v-else-if="selected">
          <div class="liquid-card p-4 mb-4 flex flex-wrap items-center gap-4">
            <div class="flex items-center gap-2">
              <FileSpreadsheet :size="18" class="text-[var(--color-accent)]" />
              <span class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">{{ selected.name }}</span>
            </div>
            <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
              {{ selected.row_count }} 行 × {{ selected.column_names?.length ?? 0 }} 列
            </span>
            <div v-if="selected.tags?.length" class="flex gap-1">
              <span v-for="tag in selected.tags" :key="tag" class="liquid-tag-purple text-[var(--text-micro)]">{{ tag }}</span>
            </div>
            <button
              class="liquid-btn-ghost px-3 py-1.5 flex items-center gap-1.5 text-red-500 ml-auto"
              @click="showDelete = true"
            >
              <Trash2 :size="14" /> 删除
            </button>
          </div>

          <!-- Pipeline status -->
          <div class="liquid-card p-4 mb-4">
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">处理流水线</h3>
              <div class="flex items-center gap-2">
                <span v-if="polling" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">自动刷新中...</span>
                <button class="liquid-btn-ghost px-2 py-1" @click="loadTasks">
                  <RefreshCw :size="14" :class="{ 'animate-spin': loadingTasks }" />
                </button>
              </div>
            </div>

            <LoadingSpinner v-if="loadingTasks" text="加载任务..." />
            <div v-else class="flex gap-1">
              <div
                v-for="step in DS_TASK_STEPS"
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
                class="px-4 py-2 text-[var(--text-caption)] border-b-2 transition-colors bg-none border-none cursor-pointer"
                :class="activeTab === tab.key
                  ? 'border-[var(--color-accent)] text-[var(--color-accent)]'
                  : 'border-transparent text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)]'"
                @click="activeTab = tab.key"
              >
                {{ tab.label }}
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
                      class="liquid-btn-ghost px-2 py-1 text-[var(--text-micro)]"
                      :disabled="offset === 0"
                      @click="changePage(-1)"
                    >
                      上一页
                    </button>
                    <button
                      class="liquid-btn-ghost px-2 py-1 text-[var(--text-micro)]"
                      :disabled="offset + pageSize >= totalRows"
                      @click="changePage(1)"
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
              <div v-else>
                <h4 class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">知识节点 ({{ kgNodes.length }})</h4>
                <div class="flex flex-wrap gap-2">
                  <div
                    v-for="node in kgNodes"
                    :key="node.id"
                    class="liquid-card px-3 py-2 flex items-center gap-2"
                  >
                    <GitBranch :size="12" class="text-[var(--color-accent)]" />
                    <span class="text-[var(--text-caption)] text-[var(--color-ink)]">{{ node.title }}</span>
                    <span class="liquid-tag-blue text-[var(--text-micro)]">{{ node.domain }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>

        <EmptyState v-else title="请选择数据集" hint="从左侧列表选择数据集查看详情" />
      </div>
    </div>

    <!-- KG Overview Dialog -->
    <div
      v-if="showKgOverview"
      class="fixed inset-0 z-[var(--z-dialog)] flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      @keydown.escape="showKgOverview = false"
    >
      <div class="absolute inset-0 bg-black/50" @click="showKgOverview = false" />
      <div class="relative liquid-card p-6 w-[700px] max-h-[80vh] overflow-auto">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-[var(--text-page-title)] font-medium text-[var(--color-ink)]">知识图谱总览</h2>
          <button class="liquid-btn-ghost p-1" @click="showKgOverview = false">
            <X :size="18" />
          </button>
        </div>

        <LoadingSpinner v-if="loadingKgOverview" text="加载知识图谱..." />
        <template v-else>
          <div class="mb-3">
            <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
              {{ kgOverviewNodes.length }} 节点 · {{ kgOverviewEdges.length }} 关系
            </span>
          </div>
          <EmptyState v-if="kgOverviewNodes.length === 0" title="暂无知识图谱" hint="从数据集构建" />
          <div v-else class="flex flex-wrap gap-2">
            <div
              v-for="node in kgOverviewNodes"
              :key="node.id"
              class="liquid-card px-3 py-2 flex items-center gap-2"
            >
              <GitBranch :size="12" class="text-[var(--color-accent)]" />
              <span class="text-[var(--text-caption)] text-[var(--color-ink)]">{{ node.title }}</span>
              <span class="liquid-tag-blue text-[var(--text-micro)]">{{ node.domain }}</span>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- Upload Dialog -->
    <div
      v-if="showUpload"
      class="fixed inset-0 z-[var(--z-dialog)] flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      @keydown.escape="showUpload = false"
    >
      <div class="absolute inset-0 bg-black/50" @click="showUpload = false" />
      <div class="relative liquid-card p-6 w-[480px]">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-[var(--text-page-title)] font-medium text-[var(--color-ink)]">上传数据集</h2>
          <button class="liquid-btn-ghost p-1" @click="showUpload = false">
            <X :size="18" />
          </button>
        </div>

        <div class="flex flex-col gap-4">
          <div>
            <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">数据集名称</label>
            <input v-model="uploadForm.name" class="liquid-input w-full" placeholder="输入数据集名称" />
          </div>
          <div>
            <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">描述（可选）</label>
            <textarea v-model="uploadForm.description" class="liquid-input w-full resize-none" rows="2" placeholder="输入描述" />
          </div>
          <div>
            <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">标签（可选，多个用逗号分隔）</label>
            <input v-model="uploadForm.tags" class="liquid-input w-full" placeholder="如：汽车维修，数据分析" />
          </div>
          <div>
            <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">选择文件</label>
            <div
              class="border-2 border-dashed border-[var(--color-border)] rounded-lg p-6 text-center cursor-pointer hover:border-[var(--color-accent)] transition-colors"
              :class="{ 'border-[var(--color-accent)]': uploadForm.file }"
              @click="triggerFileInput"
            >
              <FileSpreadsheet :size="24" class="mx-auto mb-2 text-[var(--color-ink-tertiary)]" />
              <p class="text-[var(--text-caption)] text-[var(--color-ink-secondary)]">
                {{ uploadForm.file ? uploadForm.file.name : "点击选择 Excel 文件" }}
              </p>
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-1">支持 .xlsx, .xls, .csv</p>
            </div>
            <input ref="fileInputRef" type="file" accept=".xlsx,.xls,.csv" class="hidden" @change="handleFileChange" />
          </div>
          <div class="flex justify-end gap-2 mt-2">
            <button class="liquid-btn-ghost px-4 py-2" @click="showUpload = false">取消</button>
            <button
              class="liquid-btn-primary px-4 py-2 flex items-center gap-1.5"
              :disabled="!canUpload || uploading"
              @click="doUpload"
            >
              <LoadingSpinner v-if="uploading" :size="14" />
              <Upload v-else :size="14" />
              {{ uploading ? "上传中..." : "上传" }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete dialog -->
    <ConfirmDialog
      v-model:open="showDelete"
      title="删除数据集"
      :message="`确定删除数据集「${selected?.name}」？此操作不可恢复。`"
      @confirm="doDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import {
  Upload, FileSpreadsheet, Trash2, RefreshCw, GitBranch, ChevronRight, X,
  Cpu,
} from "lucide-vue-next";
import type { Component } from "vue";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useToast } from "@/composables/useToast";
import {
  structuredDataApi,
  type DatasetDTO,
  type DatasetRowDTO,
  type KGNode,
} from "@/services/structured-data";
import type { TaskDTO } from "@/services/document";
import {
  DS_TASK_STEPS,
  TASK_STATUS_MAP,
  FILE_STATUS_MAP,
} from "@/constants/pipeline";

const toast = useToast();

// --- State ---
const datasets = ref<DatasetDTO[]>([]);
const selected = ref<DatasetDTO | null>(null);
const tasks = ref<TaskDTO[]>([]);
const rows = ref<DatasetRowDTO[]>([]);
const kgNodes = ref<KGNode[]>([]);
const kgOverviewNodes = ref<KGNode[]>([]);
const kgOverviewEdges = ref<unknown[]>([]);

const loading = ref(true);
const loadingDetail = ref(false);
const loadingTasks = ref(false);
const loadingRows = ref(false);
const loadingKg = ref(false);
const loadingKgOverview = ref(false);

const activeTab = ref("preview");
const showDelete = ref(false);
const showUpload = ref(false);
const showKgOverview = ref(false);

const offset = ref(0);
const pageSize = 50;
const totalRows = computed(() => selected.value?.row_count ?? 0);

const uploadForm = ref({ name: "", description: "", tags: "", file: null as File | null });
const uploading = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);

let pollTimer: ReturnType<typeof setInterval> | null = null;

const tabs = [
  { key: "preview", label: "数据预览" },
  { key: "kg", label: "知识图谱(本表)" },
];

const polling = computed(() => tasks.value.some((t) => t.status === "running" || t.status === "pending"));

const canUpload = computed(() => uploadForm.value.name.trim() && uploadForm.value.file);

const selectedId = computed(() => selected.value?.id ?? null);

// --- Load datasets ---
async function loadDatasets() {
  loading.value = true;
  try {
    const { data } = await structuredDataApi.listDatasets();
    datasets.value = data;
  } catch {
    toast.error("加载数据集列表失败");
  } finally {
    loading.value = false;
  }
}

// --- Select dataset ---
async function selectDataset(ds: DatasetDTO) {
  selected.value = ds;
  offset.value = 0;
  await Promise.all([loadTasks(), loadRows()]);
}

async function loadTasks() {
  if (!selected.value) return;
  loadingTasks.value = true;
  try {
    const { data } = await structuredDataApi.listTasks(selected.value.id);
    tasks.value = data;
  } catch {
    toast.error("加载任务失败");
  } finally {
    loadingTasks.value = false;
  }
}

async function loadRows() {
  if (!selected.value) return;
  loadingRows.value = true;
  try {
    const { data } = await structuredDataApi.listRows(selected.value.id, {
      offset: offset.value,
      limit: pageSize,
    });
    rows.value = data;
  } catch {
    toast.error("加载数据失败");
  } finally {
    loadingRows.value = false;
  }
}

async function loadKg() {
  if (!selected.value) return;
  loadingKg.value = true;
  try {
    const { data } = await structuredDataApi.getKnowledgeGraph();
    kgNodes.value = data.nodes.filter((n) => n.source_dataset_id === selected.value!.id);
  } catch {
    toast.error("加载知识图谱失败");
  } finally {
    loadingKg.value = false;
  }
}

async function loadKgOverview() {
  loadingKgOverview.value = true;
  try {
    const { data } = await structuredDataApi.getKnowledgeGraph();
    kgOverviewNodes.value = data.nodes;
    kgOverviewEdges.value = data.edges;
  } catch {
    toast.error("加载知识图谱总览失败");
  } finally {
    loadingKgOverview.value = false;
  }
}

// --- Pagination ---
function changePage(delta: number) {
  const newOffset = offset.value + delta * pageSize;
  if (newOffset < 0 || newOffset >= totalRows.value) return;
  offset.value = newOffset;
  loadRows();
}

// --- Upload ---
function triggerFileInput() {
  fileInputRef.value?.click();
}

function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files?.length) {
    uploadForm.value.file = input.files[0];
  }
}

async function doUpload() {
  if (!canUpload.value) return;
  uploading.value = true;
  try {
    const formData = new FormData();
    formData.append("file", uploadForm.value.file!);
    formData.append("name", uploadForm.value.name.trim());
    if (uploadForm.value.description.trim()) {
      formData.append("description", uploadForm.value.description.trim());
    }
    if (uploadForm.value.tags.trim()) {
      const tags = uploadForm.value.tags.split(",").map((t) => t.trim()).filter(Boolean);
      tags.forEach((tag) => formData.append("tags", tag));
    }
    await structuredDataApi.uploadDataset(formData);
    toast.success("数据集上传成功");
    showUpload.value = false;
    uploadForm.value = { name: "", description: "", tags: "", file: null };
    await loadDatasets();
  } catch {
    toast.error("上传失败");
  } finally {
    uploading.value = false;
  }
}

// --- Delete ---
async function doDelete() {
  if (!selected.value) return;
  try {
    await structuredDataApi.deleteDataset(selected.value.id);
    toast.success("数据集已删除");
    selected.value = null;
    rows.value = [];
    tasks.value = [];
    await loadDatasets();
  } catch {
    toast.error("删除失败");
  }
}

async function retryTasks() {
  if (!selected.value) return;
  try {
    await structuredDataApi.retryTasks(selected.value.id);
    toast.success("已重新提交任务");
    await loadTasks();
  } catch {
    toast.error("重试失败");
  }
}

// --- KG Overview ---
watch(showKgOverview, (val) => {
  if (val && kgOverviewNodes.value.length === 0) loadKgOverview();
});

// --- Tab data loading ---
watch(activeTab, () => {
  if (activeTab.value === "kg" && kgNodes.value.length === 0) loadKg();
});

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
  FileSpreadsheet, Cpu, GitBranch,
};

function stepIcon(type: string): Component {
  const step = DS_TASK_STEPS.find((s) => s.type === type);
  return stepIconMap[step?.icon ?? ""] ?? FileSpreadsheet;
}

function stepBgClass(type: string) {
  const s = stepStatus(type);
  if (s === "success" || s === "running") return "bg-[var(--color-accent-bg)]";
  if (s === "failed") return "bg-red-50 dark:bg-red-950/20";
  return "";
}

function stepLabelClass(type: string) {
  const color = TASK_STATUS_MAP[stepStatus(type)]?.color ?? "amber";
  return `liquid-tag-${color} text-[var(--text-micro)]`;
}

// --- Status helpers ---
function dsStatusLabel(status: string) {
  return FILE_STATUS_MAP[status]?.label ?? status;
}

function dsStatusTagClass(status: string) {
  const color = FILE_STATUS_MAP[status]?.color ?? "blue";
  return `liquid-tag-${color} text-[var(--text-micro)]`;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 0);
}

// --- Polling ---
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (polling.value) loadTasks();
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
  await loadDatasets();
  startPolling();
});

onUnmounted(() => {
  stopPolling();
});
</script>
