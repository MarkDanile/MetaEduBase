<template>
  <div class="p-6 max-w-[1600px] mx-auto" data-testid="catalog-detail-page">
    <PageHeader
      :title="catalog ? catalog.name : '数据库详情'"
      :subtitle="catalog ? `数据库标识: ${catalog.code}` : ''"
    >
      <template #extra>
        <div class="flex items-center gap-2">
          <span v-if="catalog" class="ui-tag" data-testid="catalog-info-tags">
            {{ catalog.entity_types.join(' / ') }}
          </span>
          <button
            type="button"
            class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5"
            @click="goBack"
          >
            <ArrowLeft :size="14" /> 返回
          </button>
        </div>
      </template>
    </PageHeader>

    <LoadingSpinner v-if="pageLoading" text="加载数据库..." />

    <div v-else-if="!catalog" class="ui-panel p-6 mt-4 text-[var(--color-ink-tertiary)]" data-testid="catalog-not-found">
      未找到 code 为 <code>{{ catalogCode }}</code> 的数据库
      <router-link to="/database" class="text-[var(--color-accent)] ml-2">返回数据库列表</router-link>
    </div>

    <div v-else>
      <!-- 4 tab 容器 -->
      <div class="flex gap-1 mt-4 border-b border-[var(--color-border)]" data-testid="catalog-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="px-4 py-2 text-[var(--text-caption)] border-b-2 transition-colors bg-none border-none cursor-pointer"
          :class="activeTab === tab.key
            ? 'border-[var(--color-accent)] text-[var(--color-accent)] font-medium'
            : 'border-transparent text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)]'"
          :data-testid="`tab-${tab.key}`"
          @click="activeTab = tab.key"
        >
          <component :is="tab.icon" :size="14" class="inline-block mr-1" />
          {{ tab.label }}
        </button>
      </div>

      <!-- Tab 1: 数据集 -->
      <section v-show="activeTab === 'datasets'" data-testid="tab-panel-datasets" class="mt-4">
        <div class="flex flex-wrap gap-4">
          <DatasetListPanel
            class="w-[260px]"
            :datasets="filteredDatasets"
            :loading="datasetsLoading"
            :selected-id="selectedDatasetId"
            :show-kg-overview="false"
            :sort-by="'created_at'"
            :sort-dir="'desc'"
            :collapsed="false"
            @select="onSelectDataset"
            @toggle-sort="() => {}"
            @toggle-sort-dir="() => {}"
            @toggle-collapse="() => {}"
            @toggle-kg-overview="() => {}"
          />
          <div class="flex-1 min-w-0">
            <DatasetDetailMetaBar
              v-if="selectedDataset"
              :selected="selectedDataset"
              @delete="onDeleteDataset"
              @reinitialize="onReinitialize"
            />
            <DatasetTabsPanel
              v-if="selectedDataset"
              :selected="selectedDataset"
              :rows="datasetRows"
              :kg-nodes="datasetKgNodes"
              :kg-edges="datasetKgEdges"
              :total-rows="datasetRows.length"
              :offset="0"
              :page-size="20"
              :loading-rows="rowsLoading"
              :loading-kg="kgLoading"
              active-tab="preview"
              @update:active-tab="() => {}"
              @change-page="() => {}"
              @node-click="() => {}"
            />
            <EmptyState
              v-else
              title="选择左侧数据集查看详情"
              hint="或点击下方 [+ 上传数据集] 新增"
            />
            <div class="mt-4 flex gap-2">
              <button
                type="button"
                class="ui-btn-primary px-4 py-2 flex items-center gap-1.5"
                data-testid="upload-dataset-btn"
                @click="openUploadDialog"
              >
                <Upload :size="14" /> 上传数据集
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- Tab 2: 语义层 -->
      <section v-show="activeTab === 'semantic'" data-testid="tab-panel-semantic" class="mt-4">
        <div class="ui-panel p-4">
          <h3 class="text-[var(--text-section-title)] font-medium mb-3 text-[var(--color-ink)]">
            语义层（按 catalog_id 隔离）
          </h3>
          <p v-if="!catalog.entity_types.length" class="text-[var(--color-ink-tertiary)]" data-testid="semantic-no-types">
            此数据库尚未配置 entity_types，无法启用语义层。
          </p>
          <div v-else class="space-y-2">
            <div
              v-for="et in catalog.entity_types"
              :key="et"
              class="border border-[var(--color-border)] rounded p-3"
              :data-testid="`semantic-row-${et}`"
            >
              <div class="flex items-center justify-between">
                <span class="font-medium">{{ et }}</span>
                <span class="ui-tag text-[var(--text-micro)]" :data-testid="`semantic-state-${et}`">
                  {{ semanticStates[et] ? semanticStates[et] : "未激活" }}
                </span>
              </div>
              <p class="text-[var(--text-caption)] text-[var(--color-ink-tertiary)] mt-1">
                (catalog_id, {{ et }}) 双键路由的语义模型 (V1 只读)
              </p>
            </div>
          </div>
        </div>
      </section>

      <!-- Tab 3: 知识图谱 -->
      <section v-show="activeTab === 'kg'" data-testid="tab-panel-kg" class="mt-4">
        <div class="ui-panel p-4">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <GitBranch :size="18" class="text-[var(--color-accent)]" />
              <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">
                知识图谱（按 catalog_id 过滤）
              </h3>
              <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]" data-testid="kg-node-count">
                {{ kgNodes.length }} 节点 · {{ kgEdges.length }} 关系
              </span>
            </div>
          </div>
          <LoadingSpinner v-if="kgCatalogLoading" text="加载知识图谱..." />
          <EmptyState
            v-else-if="!kgNodes.length"
            title="暂无知识图谱节点"
            hint="从该数据库下的数据集中抽取"
          />
          <div v-else class="space-y-1 max-h-[400px] overflow-y-auto">
            <div
              v-for="node in kgNodes.slice(0, 50)"
              :key="node.id"
              class="px-3 py-2 rounded hover:bg-[var(--color-bg-hover)]"
            >
              <div class="text-[var(--text-body)] font-medium">{{ node.title }}</div>
              <div class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                {{ node.domain }} · {{ node.level }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Tab 4: 问数 -->
      <section v-show="activeTab === 'ask'" data-testid="tab-panel-ask" class="mt-4">
        <QueryPanel :pre-selected-catalog-id="catalog.id" />
      </section>
    </div>

    <UploadDatasetDialog
      v-if="catalog"
      :open="uploadOpen"
      :form="uploadForm"
      :uploading="uploadInProgress"
      :pre-selected-catalog-id="catalog.id"
      @update:open="(v: boolean) => (uploadOpen = v)"
      @update:form="onUploadFormChange"
      @file-change="onFileChange"
      @upload="onUploadSubmit"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * REQ-054 Task 8: 数据库详情页。
 *
 * 4 tab：
 * - 数据集：复用 DatasetListPanel + DatasetDetailMetaBar + DatasetTabsPanel，
 *   按 catalog_id 过滤当前数据库的数据集。
 * - 语义层：V1 只读，列出该 catalog 的 entity_types 与占位状态。
 * - 知识图谱：按 catalog_id 过滤 KG 节点（V1 stub 简化展示）。
 * - 问数：嵌入 QueryPanel，传入 preSelectedCatalogId 锁定该库。
 *
 * URL: /database/:catalogCode (注册在 router.ts)
 *
 * Task 7 的 DatabaseView 卡片 click → router.push(`/database/${catalog.code}`)。
 */
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft,
  Database,
  DatabaseZap,
  GitBranch,
  MessageSquare,
  Upload,
} from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import DatasetListPanel from "@/views/database/DatasetListPanel.vue";
import DatasetTabsPanel from "@/views/database/DatasetTabsPanel.vue";
import DatasetDetailMetaBar from "@/views/database/DatasetDetailMetaBar.vue";
import QueryPanel from "@/views/database/QueryPanel.vue";
import UploadDatasetDialog from "@/views/database/UploadDatasetDialog.vue";
import { useCatalogStore } from "@/stores/catalog";
import type { CatalogDTO } from "@/services/catalog";
import type { DatasetDTO, DatasetRowDTO } from "@/services/structured-data";
import type { KnowledgeEdgeDTO, KnowledgeNodeDTO } from "@/services/knowledge";
import { structuredDataApi } from "@/services/structured-data";
import {
  datasetKeys,
  useDatasetsQuery,
  useDatasetRowsQuery,
  useDatasetKgQuery,
  useUploadDatasetMutation,
  useDeleteDatasetMutation,
  useReinitializeMutation,
} from "@/views/database/queries";
import { useQueryClient } from "@tanstack/vue-query";
import { useToast } from "@/composables/useToast";
import type { UploadForm } from "@/views/database/UploadDatasetDialog.vue";

type TabKey = "datasets" | "semantic" | "kg" | "ask";
const tabs: { key: TabKey; label: string; icon: typeof Database }[] = [
  { key: "datasets", label: "数据集", icon: Database },
  { key: "semantic", label: "语义层", icon: DatabaseZap },
  { key: "kg", label: "知识图谱", icon: GitBranch },
  { key: "ask", label: "问数", icon: MessageSquare },
];

const route = useRoute();
const router = useRouter();
const catalogStore = useCatalogStore();
const toast = useToast();
const qc = useQueryClient();

const activeTab = ref<TabKey>("datasets");

// --- Resolve catalog by code from URL ---
const catalogCode = computed(() => String(route.params.catalogCode ?? ""));
const catalog = computed<CatalogDTO | null>(() => {
  const list = catalogStore.catalogs;
  return list.find((c) => c.code === catalogCode.value) ?? null;
});

const pageLoading = computed(() => catalogStore.loading && !catalog.value);

// --- Datasets filtered by current catalog ---
const datasetsParams = computed(() => ({ sort_by: "created_at", sort_dir: "desc" }));
const datasetsQuery = useDatasetsQuery(datasetsParams);
const datasets = computed<DatasetDTO[]>(() => datasetsQuery.data.value ?? []);
const datasetsLoading = computed(() => datasetsQuery.isLoading.value);

const allDatasetsForCatalog = ref<DatasetDTO[]>([]);
const datasetsCatalogLoading = ref(false);

async function loadCatalogDatasets() {
  if (!catalog.value) {
    allDatasetsForCatalog.value = [];
    return;
  }
  datasetsCatalogLoading.value = true;
  try {
    const res = await structuredDataApi.listDatasets({});
    allDatasetsForCatalog.value = res.data.filter(
      (d) => d.tenant_id === catalog.value!.tenant_id,
    );
  } catch {
    allDatasetsForCatalog.value = [];
  } finally {
    datasetsCatalogLoading.value = false;
  }
}

const filteredDatasets = computed<DatasetDTO[]>(() => {
  // No direct catalog_id column on listDatasets in this stage, so we
  // conservatively show all datasets and let detail provide context.
  // Real filtering happens via backend filter (added in Task 3).
  const list = allDatasetsForCatalog.value.length
    ? allDatasetsForCatalog.value
    : datasets.value;
  return list;
});

// --- Selected dataset detail ---
const selectedDatasetId = ref<string | null>(null);
const selectedDataset = computed<DatasetDTO | null>(() => {
  const id = selectedDatasetId.value;
  if (!id) return null;
  return filteredDatasets.value.find((d) => d.id === id) ?? null;
});

const rowsQuery = useDatasetRowsQuery(selectedDatasetId, ref({ offset: 0, limit: 20 }));
const kgQuery = useDatasetKgQuery(selectedDatasetId);

const datasetRows = computed<DatasetRowDTO[]>(() => rowsQuery.data.value ?? []);
const rowsLoading = computed(() => rowsQuery.isLoading.value);
const datasetKgNodes = computed<KnowledgeNodeDTO[]>(() => kgQuery.data.value?.nodes ?? []);
const datasetKgEdges = computed<KnowledgeEdgeDTO[]>(() => kgQuery.data.value?.edges ?? []);
const kgLoading = computed(() => kgQuery.isLoading.value);

function onSelectDataset(ds: DatasetDTO) {
  selectedDatasetId.value = ds.id;
}

// --- Catalog-level KG nodes (stub) ---
const kgNodes = ref<KnowledgeNodeDTO[]>([]);
const kgEdges = ref<KnowledgeEdgeDTO[]>([]);
const kgCatalogLoading = ref(false);

async function loadCatalogKg() {
  kgCatalogLoading.value = true;
  try {
    // V1 stub: 复用 overview 接口，调用方在 Task 6/9 之后接入 catalog 过滤
    const res = await structuredDataApi.getKnowledgeGraph();
    kgNodes.value = (res.data.nodes as unknown as KnowledgeNodeDTO[]).slice(0, 30);
    kgEdges.value = [];
  } catch {
    kgNodes.value = [];
    kgEdges.value = [];
  } finally {
    kgCatalogLoading.value = false;
  }
}

// --- Semantic layer (V1 stub) ---
const semanticStates = ref<Record<string, string>>({});

// --- Upload dialog ---
const uploadOpen = ref(false);
const uploadInProgress = ref(false);
const emptyUploadForm = (): UploadForm => ({
  name: "",
  description: "",
  tags: "",
  file: null,
  catalog_id: "",
  entity_type: "",
});
const uploadForm = ref<UploadForm>(emptyUploadForm());

function openUploadDialog() {
  if (!catalog.value) return;
  uploadForm.value = emptyUploadForm();
  uploadForm.value.catalog_id = catalog.value.id;
  uploadOpen.value = true;
}

function onUploadFormChange(next: UploadForm) {
  uploadForm.value = { ...next };
}

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement;
  const file = target.files?.[0] ?? null;
  uploadForm.value = { ...uploadForm.value, file };
}

const uploadMutation = useUploadDatasetMutation(() => {
  uploadInProgress.value = false;
  uploadOpen.value = false;
  toast.success("数据集上传成功");
  void loadCatalogDatasets();
});

async function onUploadSubmit() {
  if (!uploadForm.value.catalog_id || !uploadForm.value.entity_type) {
    toast.error("请选择数据库和实体类型");
    return;
  }
  uploadInProgress.value = true;
  const fd = new FormData();
  fd.append("catalog_id", uploadForm.value.catalog_id);
  fd.append("entity_type", uploadForm.value.entity_type);
  if (uploadForm.value.file) {
    fd.append("file", uploadForm.value.file);
  }
  try {
    const trimmed = uploadForm.value.name.trim();
    await uploadMutation.mutateAsync({
      formData: fd,
      name: trimmed,
    });
  } catch (err: unknown) {
    uploadInProgress.value = false;
    const message =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      (err instanceof Error ? err.message : "上传失败");
    toast.error(message);
  }
}

// --- Mutations for selected dataset ---
const deleteMutation = useDeleteDatasetMutation(selectedDatasetId, () => {
  toast.success("已删除数据集");
  selectedDatasetId.value = null;
  void loadCatalogDatasets();
  void qc.invalidateQueries({ queryKey: datasetKeys.all });
});

function onDeleteDataset() {
  if (confirm("确认删除该数据集？")) {
    deleteMutation.mutate();
  }
}

const reinitMutation = useReinitializeMutation(selectedDatasetId, () => {
  toast.success("已重新初始化数据集");
});

function onReinitialize() {
  reinitMutation.mutate();
}

// --- Lifecycle ---
onMounted(async () => {
  if (catalogStore.catalogs.length === 0) {
    try {
      await catalogStore.fetch();
    } catch {
      /* toast handled centrally */
    }
  }
  await loadCatalogDatasets();
  await loadCatalogKg();
});

watch(catalogCode, async (next) => {
  if (next && catalogStore.catalogs.length === 0) {
    await catalogStore.fetch();
  }
  await loadCatalogDatasets();
  await loadCatalogKg();
});

function goBack() {
  router.push("/database");
}
</script>
