<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader title="数据库" subtitle="数据集管理与知识图谱构建">
      <template #extra>
        <button class="ui-btn-primary px-3 py-1.5 flex items-center gap-1.5" @click="showUpload = true">
          <Upload :size="14" /> 上传数据集
        </button>
      </template>
    </PageHeader>

    <div class="flex gap-4" style="align-items: flex-start">
      <DatasetListPanel
        :datasets="datasets"
        :loading="loading"
        :selected-id="selectedId"
        :show-kg-overview="showKgOverview"
        :sort-by="sortBy"
        :sort-dir="sortDir"
        :collapsed="datasetListCollapsed"
        @select="selectDataset"
        @toggle-sort="onToggleSort"
        @toggle-sort-dir="toggleSortDir"
        @toggle-collapse="datasetListCollapsed = !datasetListCollapsed"
        @toggle-kg-overview="toggleKgOverview"
      />

      <div class="flex-1 min-w-0">
        <KgOverviewPanel
          v-if="showKgOverview"
          :nodes="kgOverviewNodes"
          :edges="kgOverviewEdges"
          :loading="loadingKgOverview"
          :rebuilding="rebuildingKg"
          @rebuild="showKgRebuildConfirm = true"
          @node-click="selectedOverviewKgNode = $event"
        />

        <template v-else>
          <LoadingSpinner v-if="loadingDetail" text="加载数据集..." />

          <template v-else-if="selected">
            <DatasetDetailMetaBar
              :selected="selected"
              @delete="showDelete = true"
              @reinitialize="reinitialize"
            />

            <PipelineStatusPanel
              :tasks="tasks"
              :polling="polling"
              :loading="loadingTasks"
              @retry="retryTasks"
              @refresh="tasksQuery.refetch()"
            />

            <DatasetTabsPanel
              :selected="selected"
              :rows="rows"
              :kg-nodes="kgNodes"
              :kg-edges="kgEdges"
              :total-rows="totalRows"
              :offset="offset"
              :page-size="pageSize"
              :loading-rows="loadingRows"
              :loading-kg="loadingKg"
              :active-tab="activeTab"
              @update:active-tab="(k) => (activeTab = k)"
              @change-page="changePage"
              @node-click="selectedKgNode = $event"
            />

            <QueryPanel v-if="selectedId" :dataset-id="selectedId" />
          </template>

          <EmptyState v-else title="请选择数据集" hint="从左侧列表选择数据集查看详情" />
        </template>
      </div>
    </div>

    <UploadDatasetDialog
      :open="showUpload"
      :form="uploadForm"
      :uploading="uploading"
      @update:open="(v) => (showUpload = v)"
      @update:form="(f) => (uploadForm = f)"
      @upload="doUpload"
      @file-change="handleFileChange"
    />

    <ConfirmDialog
      v-model:open="showDelete"
      title="删除数据集"
      :message="`确定删除数据集「${selected?.name}」？此操作不可恢复。`"
      @confirm="doDelete"
    />

    <ConfirmDialog
      v-model:open="showKgRebuildConfirm"
      title="重新生成整个知识图谱"
      message="将清除所有数据集的知识图谱数据并重新构建，包括跨数据集关系。此操作可能需要较长时间，确定继续吗？"
      @confirm="doRebuildKg"
    />

    <KGDetailPanel
      :node="selectedKgNode"
      :edges="kgEdges"
      :nodes="kgNodes"
      @close="selectedKgNode = null"
    />

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
import { Upload } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import KGDetailPanel from "@/components/KGDetailPanel.vue";
import { useToast } from "@/composables/useToast";
import type { DatasetDTO } from "@/services/structured-data";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";
import type { TaskDTO } from "@/services/document";
import { useDatasetsQuery, useDatasetTasksQuery, useDatasetRowsQuery, useDatasetKgQuery, useKgOverviewQuery, useUploadDatasetMutation, useDeleteDatasetMutation, useRetryTasksMutation, useReinitializeMutation, useRebuildKgMutation } from "@/views/database/queries";
import DatasetListPanel from "@/views/database/DatasetListPanel.vue";
import KgOverviewPanel from "@/views/database/KgOverviewPanel.vue";
import DatasetDetailMetaBar from "@/views/database/DatasetDetailMetaBar.vue";
import PipelineStatusPanel from "@/views/database/PipelineStatusPanel.vue";
import DatasetTabsPanel from "@/views/database/DatasetTabsPanel.vue";
import QueryPanel from "@/views/database/QueryPanel.vue";
import UploadDatasetDialog, { type UploadForm } from "@/views/database/UploadDatasetDialog.vue";

const toast = useToast();

// --- State ---
const selected = ref<DatasetDTO | null>(null);
const selectedKgNode = ref<KnowledgeNodeDTO | null>(null);
const selectedOverviewKgNode = ref<KnowledgeNodeDTO | null>(null);

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

const uploadForm = ref<UploadForm>({ name: "", description: "", tags: "", file: null });

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

function toggleSortDir() {
  sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  datasetsQuery.refetch();
}

function onToggleSort(by: string) {
  sortBy.value = by;
  datasetsQuery.refetch();
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
function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files?.length) {
    uploadForm.value = { ...uploadForm.value, file: input.files[0] };
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

// --- Auto-reload when pipeline tasks complete ---
watch(
  () => tasks.value.find((t) => t.task_type === "ds_parse")?.status,
  (status, prevStatus) => {
    if (status === "success" && prevStatus !== "success") {
      void datasetsQuery.refetch();
      void rowsQuery.refetch();
    }
  },
);

watch(
  () => tasks.value.find((t) => t.task_type === "ds_extract_kg")?.status,
  (status, prevStatus) => {
    if (status === "success" && prevStatus !== "success") {
      void kgQuery.refetch();
      void datasetsQuery.refetch();
    }
  },
);
</script>
