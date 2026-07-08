<template>
  <div class="p-6 max-w-[1600px] mx-auto" data-testid="catalog-detail-page">
    <PageHeader
      :title="catalog ? catalog.name : '数据库详情'"
      :subtitle="catalog ? `数据库标识: ${catalog.code}` : ''"
    >
      <template #extra>
        <div class="flex items-center gap-2">
          <span
            v-if="catalog && discoveredEntityTypes.length"
            class="ui-tag"
            data-testid="catalog-info-tags"
          >
            {{ discoveredEntityTypes.join(' / ') }}
          </span>
          <button
            v-if="catalog"
            type="button"
            class="ui-btn-primary px-3 py-1.5 flex items-center gap-1.5"
            data-testid="upload-dataset-btn"
            @click="openUploadDialog"
          >
            <Upload :size="14" /> 上传数据集
          </button>
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
            :datasets="allDatasetsForCatalog"
            :loading="datasetsCatalogLoading"
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
              hint="或点击右上角 [上传数据集] 新增"
            />
          </div>
        </div>
      </section>

      <!-- Tab 2: 语义层 -->
      <section v-show="activeTab === 'semantic'" data-testid="tab-panel-semantic" class="mt-4">
        <div class="ui-panel p-4">
          <h3 class="text-[var(--text-section-title)] font-medium mb-3 text-[var(--color-ink)]">
            语义层（按 catalog_id 隔离）
          </h3>
          <LoadingSpinner v-if="datasetsCatalogLoading" text="加载语义层..." />
          <EmptyState
            v-else-if="!semanticModels.length"
            title="尚未配置语义层"
            hint="上传数据集后可按实体类型自动构建"
            data-testid="semantic-empty"
          />
          <div v-else class="space-y-3">
            <div
              v-for="model in semanticModels"
              :key="model.entity_type"
              class="border border-[var(--color-border)] rounded p-3"
              :data-testid="`semantic-row-${model.entity_type}`"
            >
              <div class="flex items-center justify-between">
                <span class="font-medium">{{ model.entity_type }}</span>
                <span class="ui-tag text-[var(--text-micro)]" :data-testid="`semantic-state-${model.entity_type}`">
                  已就绪 · {{ model.datasetCount }} 个数据集
                </span>
              </div>
              <p
                v-if="model.columns.length"
                class="text-[var(--text-caption)] text-[var(--color-ink-tertiary)] mt-1"
                :data-testid="`semantic-columns-${model.entity_type}`"
              >
                列映射 ({{ model.columns.length }}): {{ model.columns.join(', ') }}
              </p>
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-1">
                (catalog_id, {{ model.entity_type }}) 双键路由的语义模型 · V1 从已上传数据集聚合
              </p>
            </div>
          </div>
        </div>
      </section>

      <!-- Tab 3: 知识图谱 -->
      <section v-show="activeTab === 'kg'" data-testid="tab-panel-kg" class="mt-4">
        <!--
          V1: 复用全局 KG 总览面板（KgOverviewPanel）。
          后端 knowledge-graph 接口暂未支持 catalog_id 过滤，V2 将加过滤参数后
          在 useKgOverviewQuery 内按 catalog_id 拉取。
        -->
        <KgOverviewPanel
          :nodes="kgOverviewNodes"
          :edges="kgOverviewEdges"
          :loading="kgOverviewLoading"
          :rebuilding="kgRebuilding"
          @rebuild="onRebuildKg"
          @node-click="() => {}"
        />
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
      :warning="uploadWarning"
      @update:open="(v: boolean) => (uploadOpen = v)"
      @update:form="onUploadFormChange"
      @file-change="onFileChange"
      @upload="onUploadSubmit"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * REQ-054 Task 8 + review fix: 数据库详情页。
 *
 * 4 tab：
 * - 数据集：复用 DatasetListPanel + DatasetDetailMetaBar + DatasetTabsPanel，
 *   按 catalog_id 过滤当前数据库的数据集。
 * - 语义层：V1 从已上传 datasets 聚合 DISTINCT entity_type，展示每个实体类型
 *   的数据集数量与列映射（复查反馈 #4，替代原占位「未激活」）。
 * - 知识图谱：嵌入 KgOverviewPanel 全局总览（复查反馈 #2，替代原 stub）。
 *   V1 后端 KG 接口未支持 catalog_id 过滤，V2 加过滤。
 * - 问数：嵌入 QueryPanel，传入 preSelectedCatalogId 锁定该库。
 *
 * 复查反馈 #3：「上传数据集」按钮移到 PageHeader #extra，固定右上角不随列表滚动。
 *
 * URL: /database/:catalogCode (注册在 router.ts)
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
import KgOverviewPanel from "@/views/database/KgOverviewPanel.vue";
import QueryPanel from "@/views/database/QueryPanel.vue";
import UploadDatasetDialog from "@/views/database/UploadDatasetDialog.vue";
import { useCatalogStore } from "@/stores/catalog";
import type { CatalogDTO } from "@/services/catalog";
import type { DatasetDTO, DatasetRowDTO } from "@/services/structured-data";
import type { KnowledgeEdgeDTO, KnowledgeNodeDTO } from "@/services/knowledge";
import { structuredDataApi } from "@/services/structured-data";
import {
  datasetKeys,
  useDatasetRowsQuery,
  useDatasetKgQuery,
  useKgOverviewQuery,
  useUploadDatasetMutation,
  useDeleteDatasetMutation,
  useReinitializeMutation,
  useRebuildKgMutation,
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
const allDatasetsForCatalog = ref<DatasetDTO[]>([]);
const datasetsCatalogLoading = ref(false);

async function loadCatalogDatasets() {
  if (!catalog.value) {
    allDatasetsForCatalog.value = [];
    return;
  }
  datasetsCatalogLoading.value = true;
  try {
    const res = await structuredDataApi.listDatasets({ catalog_id: catalog.value.id });
    allDatasetsForCatalog.value = res.data;
  } catch {
    allDatasetsForCatalog.value = [];
  } finally {
    datasetsCatalogLoading.value = false;
  }
}

// REQ-054 review fix #4: 语义层从 datasets 聚合 DISTINCT entity_type。
interface SemanticModelView {
  entity_type: string;
  datasetCount: number;
  columns: string[];
}
const discoveredEntityTypes = computed<string[]>(() => {
  const types = new Set<string>();
  for (const ds of allDatasetsForCatalog.value) {
    if (ds.entity_type) types.add(ds.entity_type);
  }
  return Array.from(types).sort();
});
const semanticModels = computed<SemanticModelView[]>(() => {
  return discoveredEntityTypes.value.map((et) => {
    const datasets = allDatasetsForCatalog.value.filter((d) => d.entity_type === et);
    const columns: string[] = [];
    for (const ds of datasets) {
      if (ds.column_names) {
        for (const col of ds.column_names) {
          if (!columns.includes(col)) columns.push(col);
        }
      }
    }
    return { entity_type: et, datasetCount: datasets.length, columns };
  });
});

// --- Selected dataset detail ---
const selectedDatasetId = ref<string | null>(null);
const selectedDataset = computed<DatasetDTO | null>(() => {
  const id = selectedDatasetId.value;
  if (!id) return null;
  return allDatasetsForCatalog.value.find((d) => d.id === id) ?? null;
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

// --- Catalog-level KG overview (review fix #2: embed KgOverviewPanel) ---
// V1: global KG (no catalog_id filter); V2 will add catalog_id filtering.
const kgOverviewQuery = useKgOverviewQuery(ref(true));
const kgOverviewNodes = computed<KnowledgeNodeDTO[]>(() => kgOverviewQuery.data.value?.nodes ?? []);
const kgOverviewEdges = computed<KnowledgeEdgeDTO[]>(() => kgOverviewQuery.data.value?.edges ?? []);
const kgOverviewLoading = computed(() => kgOverviewQuery.isLoading.value);
const kgRebuilding = ref(false);

const rebuildKgMutation = useRebuildKgMutation(ref(null), () => {
  kgRebuilding.value = false;
  toast.success("知识图谱重建已触发");
});
function onRebuildKg() {
  kgRebuilding.value = true;
  rebuildKgMutation.mutate();
}

// --- Upload dialog ---
const uploadOpen = ref(false);
const uploadInProgress = ref(false);
const uploadWarning = ref<string | null>(null);
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
  uploadWarning.value = null;
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

const uploadMutation = useUploadDatasetMutation((data) => {
  uploadInProgress.value = false;
  // REQ-054 review fix: surface new-entity-type warning.
  if (data.warning) {
    uploadWarning.value = data.warning;
    toast.warning(data.warning);
    // Keep dialog open so the user sees the inline warning.
  } else {
    uploadOpen.value = false;
    toast.success("数据集上传成功");
  }
  void loadCatalogDatasets();
});

async function onUploadSubmit() {
  if (!uploadForm.value.catalog_id || !uploadForm.value.entity_type) {
    toast.error("请选择数据库和实体类型");
    return;
  }
  uploadInProgress.value = true;
  uploadWarning.value = null;
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
});

watch(catalogCode, async (next) => {
  if (next && catalogStore.catalogs.length === 0) {
    await catalogStore.fetch();
  }
  await loadCatalogDatasets();
});

function goBack() {
  router.push("/database");
}
</script>
