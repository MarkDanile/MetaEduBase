<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader title="数据库" subtitle="数据集管理与知识图谱构建">
      <template #extra>
        <button class="liquid-btn-primary px-3 py-1.5 flex items-center gap-1.5" @click="showUpload = true">
          <Upload :size="14" /> 上传数据集
        </button>
      </template>
    </PageHeader>

    <div class="flex gap-4" style="align-items: flex-start">
      <!-- Left panel: dataset list -->
      <div class="w-[260px] shrink-0 flex flex-col gap-2" style="max-height: calc(100vh - 80px)">
        <!-- Dataset list card -->
        <div class="ui-panel flex flex-col overflow-hidden" style="flex: 1; min-height: 0">
          <!-- Card header (always visible) -->
          <div class="flex items-center justify-between flex-shrink-0 px-3 pt-3">
            <div class="flex items-center gap-2" style="font-size: 16px">
              <button
                class="text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)] transition-colors p-0.5"
                @click="datasetListCollapsed = !datasetListCollapsed"
              >
                <ChevronRight :size="14" class="transition-transform" :class="datasetListCollapsed ? '' : 'rotate-90'" />
              </button>
              <span class="text-[var(--color-ink-secondary)] font-medium">数据集</span>
              <span class="text-[var(--color-ink-secondary)]">{{ datasets.length }}</span>
            </div>

            <!-- Sort controls (only when expanded) -->
            <div v-if="!datasetListCollapsed" class="flex items-center gap-0.5">
              <button
                v-for="opt in sortOptions"
                :key="opt.value"
                class="p-0.5 rounded transition-colors"
                :class="sortBy === opt.value
                  ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                  : 'text-[var(--color-ink-secondary)] hover:bg-[var(--color-bg-hover)]'"
                :title="opt.label"
                @click="sortBy = opt.value; datasetsQuery.refetch()"
              >
                <component :is="opt.icon" :size="12" />
              </button>
              <button
                class="p-0.5 rounded text-[var(--color-ink-secondary)] hover:bg-[var(--color-bg-hover)] transition-colors"
                :title="sortDir === 'asc' ? '升序' : '降序'"
                @click="sortDir = sortDir === 'asc' ? 'desc' : 'asc'; datasetsQuery.refetch()"
              >
                <ArrowUpNarrowWide v-if="sortDir === 'asc'" :size="12" />
                <ArrowDownWideNarrow v-else :size="12" />
              </button>
            </div>
          </div>

          <!-- Content (only when expanded) -->
          <div v-if="!datasetListCollapsed" class="px-2 pb-2 flex flex-col gap-0.5 flex-1 min-h-0 overflow-hidden">
            <LoadingSpinner v-if="loading" text="加载中..." />

            <template v-else>
              <EmptyState v-if="datasets.length === 0" title="暂无数据集" hint="上传文件" compact />

              <div v-else class="flex flex-col gap-1 overflow-y-auto min-h-0 flex-1" style="max-height: calc(100vh - 240px)">
                <button
                  v-for="ds in datasets"
                  :key="ds.id"
                  class="w-full text-left px-1.5 py-1.5 rounded transition-colors"
                  style="font-size: 14px; line-height: 1.4"
                  :class="!showKgOverview && selectedId === ds.id
                    ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                    : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-ink-secondary)]'"
                  :style="ds === datasets[0] ? 'margin-top: 4px' : ''"
                  @click="selectDataset(ds)"
                >
                  <div class="flex items-center gap-1">
                    <span class="truncate font-medium">{{ ds.name }}</span>
                    <span class="text-[var(--color-ink-tertiary)] shrink-0" style="font-size: 12px">
                      {{ ds.row_count }}行 × {{ ds.column_names?.length ?? 0 }}列
                    </span>
                    <span :class="dsStatusTagClass(ds.status)" style="font-size: 11px" class="ml-auto shrink-0">{{ dsStatusLabel(ds.status) }}</span>
                  </div>
                </button>
              </div>
            </template>
          </div>
        </div>

        <!-- KG overview button -->
        <button
          class="ui-panel px-3 py-2.5 flex items-center justify-between hover:bg-[var(--color-bg-hover)] transition-colors cursor-pointer flex-shrink-0"
          style="font-size: 16px"
          :class="{ 'bg-[var(--color-accent-bg)]': showKgOverview }"
          @click="toggleKgOverview"
        >
          <div class="flex items-center gap-2">
            <GitBranch :size="15" class="text-[var(--color-accent)]" />
            <span class="text-[var(--color-ink-secondary)]" :class="{ 'text-[var(--color-accent)]': showKgOverview }">知识图谱总览</span>
          </div>
          <ChevronRight :size="15" class="text-[var(--color-ink-tertiary)] transition-transform" :class="{ 'rotate-90': showKgOverview }" />
        </button>
      </div>

      <!-- Right panel: dataset detail or KG overview -->
      <div class="flex-1 min-w-0">
        <!-- KG Overview mode -->
        <template v-if="showKgOverview">
          <div class="ui-panel p-4">
            <div class="flex items-center justify-between mb-3">
              <div class="flex items-center gap-2">
                <GitBranch :size="18" class="text-[var(--color-accent)]" />
                <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">知识图谱总览</h3>
                <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
                  {{ kgOverviewNodes.length }} 节点 · {{ kgOverviewEdges.length }} 关系
                </span>
              </div>
              <button
                class="liquid-btn-ghost px-3 py-1.5 flex items-center gap-1.5"
                :disabled="rebuildingKg"
                @click="showKgRebuildConfirm = true"
              >
                <RefreshCw :size="14" :class="{ 'animate-spin': rebuildingKg }" />
                <span>{{ rebuildingKg ? '重建中...' : '重新生成' }}</span>
              </button>
            </div>

            <LoadingSpinner v-if="loadingKgOverview" text="加载知识图谱..." />
            <EmptyState v-else-if="kgOverviewNodes.length === 0" title="暂无知识图谱" hint="从数据集构建" />
            <div v-else class="relative">
              <KGGraph
                :nodes="kgOverviewNodes"
                :edges="kgOverviewEdges"
                :height="560"
                @node-click="selectedOverviewKgNode = $event"
              />
            </div>
          </div>
        </template>

        <!-- Dataset detail mode -->
        <template v-else>
          <LoadingSpinner v-if="loadingDetail" text="加载数据集..." />

          <template v-else-if="selected">
            <div class="ui-panel p-4 mb-4 flex flex-wrap items-center gap-4">
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
              <button
                class="liquid-btn-ghost px-3 py-1.5 flex items-center gap-1.5"
                @click="reinitialize"
              >
                <RefreshCw :size="14" /> 重新初始化
              </button>
            </div>

            <!-- Pipeline status -->
            <div class="ui-panel p-4 mb-4">
              <div class="flex items-center justify-between mb-3">
                <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">处理流水线</h3>
                <div class="flex items-center gap-2">
                  <span v-if="polling" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">自动刷新中...</span>
                  <button class="liquid-btn-ghost px-2 py-1" @click="tasksQuery.refetch()">
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
                <div v-else class="relative">
                  <KGGraph
                    :nodes="kgNodes"
                    :edges="kgEdges"
                    :height="420"
                    @node-click="selectedKgNode = $event"
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

          <EmptyState v-else title="请选择数据集" hint="从左侧列表选择数据集查看详情" />
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
      <div class="relative ui-panel p-6 w-[480px]">
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

    <!-- KG Rebuild Confirm -->
    <ConfirmDialog
      v-model:open="showKgRebuildConfirm"
      title="重新生成整个知识图谱"
      message="将清除所有数据集的知识图谱数据并重新构建，包括跨数据集关系。此操作可能需要较长时间，确定继续吗？"
      @confirm="doRebuildKg"
    />

    <!-- KG node detail panel (per-dataset) -->
    <KGDetailPanel
      :node="selectedKgNode"
      :edges="kgEdges"
      :nodes="kgNodes"
      @close="selectedKgNode = null"
    />

    <!-- KG Overview node detail panel -->
    <KGDetailPanel
      :node="selectedOverviewKgNode"
      :edges="kgOverviewEdges"
      :nodes="kgOverviewNodes"
      @close="selectedOverviewKgNode = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import {
  Upload, FileSpreadsheet, Trash2, RefreshCw, GitBranch, ChevronRight,
  Cpu, Clock, Type, Hash, ArrowUpNarrowWide, ArrowDownWideNarrow,
} from "lucide-vue-next";
import type { Component } from "vue";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import KGGraph from "@/components/KGGraph.vue";
import KGDetailPanel from "@/components/KGDetailPanel.vue";
import { useToast } from "@/composables/useToast";
import type { DatasetDTO } from "@/services/structured-data";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";
import type { TaskDTO } from "@/services/document";
import {
  DS_TASK_STEPS,
  TASK_STATUS_MAP,
  FILE_STATUS_MAP,
} from "@/constants/pipeline";
import {
  useDatasetsQuery,
  useDatasetTasksQuery,
  useDatasetRowsQuery,
  useDatasetKgQuery,
  useKgOverviewQuery,
  useUploadDatasetMutation,
  useDeleteDatasetMutation,
  useRetryTasksMutation,
  useReinitializeMutation,
  useRebuildKgMutation,
} from "@/views/database/queries";

const toast = useToast();

// --- State ---
const selected = ref<DatasetDTO | null>(null);
const selectedKgNode = ref<KnowledgeNodeDTO | null>(null);
const selectedOverviewKgNode = ref<KnowledgeNodeDTO | null>(null);

// Kept for template compatibility (was a dead loading flag in the previous
// implementation — always false). Vue Query owns actual data loading state.
const loadingDetail = ref(false);

const activeTab = ref("preview");
const showDelete = ref(false);
const showUpload = ref(false);
const showKgOverview = ref(false);
const showKgRebuildConfirm = ref(false);
const datasetListCollapsed = ref(false);

const offset = ref(0);
const pageSize = 50;
const totalRows = computed(() => selected.value?.row_count ?? 0);
const sortBy = ref("created_at");
const sortDir = ref("desc");
const sortOptions = [
  { value: "created_at", label: "按时间", icon: Clock },
  { value: "name", label: "按名称", icon: Type },
  { value: "row_count", label: "按数据量", icon: Hash },
];

const uploadForm = ref({ name: "", description: "", tags: "", file: null as File | null });
const fileInputRef = ref<HTMLInputElement | null>(null);

const tabs = [
  { key: "preview", label: "数据预览" },
  { key: "kg", label: "知识图谱(本表)" },
];

const selectedId = computed(() => selected.value?.id ?? null);

// --- Queries (Vue Query) ---
const datasetsQuery = useDatasetsQuery(
  computed(() => ({ sort_by: sortBy.value, sort_dir: sortDir.value })),
);
const datasets = computed<DatasetDTO[]>(() => datasetsQuery.data.value ?? []);
const loading = computed(() => datasetsQuery.isLoading.value);

const tasksQuery = useDatasetTasksQuery(selectedId);
const tasks = computed<TaskDTO[]>(() => tasksQuery.data.value ?? []);
const loadingTasks = computed(() => tasksQuery.isFetching.value);
const polling = computed(() =>
  tasks.value.some((t) => t.status === "running" || t.status === "pending"),
);

const rowsQuery = useDatasetRowsQuery(
  selectedId,
  computed(() => ({ offset: offset.value, limit: pageSize })),
);
const rows = computed(() => rowsQuery.data.value ?? []);
const loadingRows = computed(() => rowsQuery.isFetching.value);

const kgQuery = useDatasetKgQuery(selectedId);
const kgNodes = computed<KnowledgeNodeDTO[]>(() => kgQuery.data.value?.nodes ?? []);
const kgEdges = computed<KnowledgeEdgeDTO[]>(() => kgQuery.data.value?.edges ?? []);
const loadingKg = computed(() => kgQuery.isFetching.value);

const kgOverviewQuery = useKgOverviewQuery(
  // TD-015 fix: only fetch the overview payload when the user has
  // expanded the panel.
  computed(() => showKgOverview.value),
);
const kgOverviewNodes = computed<KnowledgeNodeDTO[]>(
  () => kgOverviewQuery.data.value?.nodes ?? [],
);
const kgOverviewEdges = computed<KnowledgeEdgeDTO[]>(
  () => kgOverviewQuery.data.value?.edges ?? [],
);
const loadingKgOverview = computed(() => kgOverviewQuery.isFetching.value);

const canUpload = computed(() => uploadForm.value.name.trim() && uploadForm.value.file);

// --- Select dataset ---
function selectDataset(ds: DatasetDTO) {
  showKgOverview.value = false;
  selected.value = ds;
  offset.value = 0;
}

// --- Mutations (Vue Query) ---
const uploadMutation = useUploadDatasetMutation(() => {
  toast.success("数据集上传成功");
  showUpload.value = false;
  uploadForm.value = { name: "", description: "", tags: "", file: null };
});
const uploading = computed(() => uploadMutation.isPending.value);

const deleteMutation = useDeleteDatasetMutation(selectedId, () => {
  toast.success("数据集已删除");
  selected.value = null;
});

const retryMutation = useRetryTasksMutation(selectedId, () => {
  toast.success("已重新提交任务");
});

const reinitializeMutation = useReinitializeMutation(selectedId, () => {
  toast.success("已开始重新初始化");
});

const rebuildKgMutation = useRebuildKgMutation(selectedId, () => {
  toast.success("知识图谱重建已启动");
  selectedOverviewKgNode.value = null;
});
const rebuildingKg = computed(() => rebuildKgMutation.isPending.value);

// --- Pagination ---
function changePage(delta: number) {
  const newOffset = offset.value + delta * pageSize;
  if (newOffset < 0 || newOffset >= totalRows.value) return;
  offset.value = newOffset;
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

function doUpload() {
  if (!canUpload.value) return;
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
  // TD-015 fix: forward the user-supplied dataset name; the backend
  // reads it as a query parameter.
  uploadMutation.mutate({ formData, name: uploadForm.value.name.trim() });
}

function doDelete() {
  if (!selectedId.value) return;
  deleteMutation.mutate(undefined);
}

function retryTasks() {
  if (!selectedId.value) return;
  retryMutation.mutate(undefined);
}

function reinitialize() {
  if (!selectedId.value) return;
  reinitializeMutation.mutate(undefined);
}

function doRebuildKg() {
  rebuildKgMutation.mutate(undefined);
}

// --- KG Overview ---
function toggleKgOverview() {
  showKgOverview.value = !showKgOverview.value;
}

// --- Tab data loading ---
// When switching to the kg tab, ensure the kg query is enabled by selecting
// the dataset first; Vue Query will then refetch automatically.

// --- Auto-reload when pipeline tasks complete ---
watch(
  () => tasks.value.find((t) => t.task_type === "ds_parse")?.status,
  (status, prevStatus) => {
    if (status === "success" && prevStatus !== "success") {
      // Row count updates from 0 to actual; refresh both list and rows.
      void datasetsQuery.refetch();
      void rowsQuery.refetch();
    }
  },
);

watch(
  () => tasks.value.find((t) => t.task_type === "ds_extract_kg")?.status,
  (status, prevStatus) => {
    if (status === "success" && prevStatus !== "success") {
      // Reload KG so it's ready on tab switch
      void kgQuery.refetch();
      void datasetsQuery.refetch();
    }
  },
);

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

// --- Init ---
// Queries auto-fetch on first read (via useQuery); no explicit onMounted trigger
// is required. Polling is handled by useDatasetTasksQuery.refetchInterval.

</script>
