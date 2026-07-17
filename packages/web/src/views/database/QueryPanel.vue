<template>
  <div class="ui-panel p-4 space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-[var(--text-section-title)] font-medium text-[var(--color-ink)]">智能问数</h3>
      <span
        v-if="datasetId"
        class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]"
        data-testid="dataset-id-badge"
      >
        当前数据集: {{ datasetId }}
      </span>
    </div>

    <form @submit.prevent="onAsk" class="space-y-2">
      <div class="flex flex-wrap gap-2">
        <select
          v-model="catalogId"
          class="border border-[var(--color-border)] rounded px-2 py-1 bg-[var(--color-bg)] text-[var(--color-ink)]"
          data-testid="catalog-select"
          :disabled="lockedCatalogId !== null"
        >
          <option
            v-for="c in catalogs"
            :key="c.id"
            :value="c.id"
          >
            {{ c.name }} ({{ c.code }})
          </option>
        </select>
        <select
          v-model="entityType"
          class="border border-[var(--color-border)] rounded px-2 py-1 bg-[var(--color-bg)] text-[var(--color-ink)]"
          data-testid="entity-type-select"
          :disabled="entityTypesLoading || availableEntityTypes.length === 0"
        >
          <option value="" disabled>
            {{ entityTypesLoading
              ? "加载实体类型..."
              : availableEntityTypes.length === 0
                ? (datasetsCount === 0 ? "请先上传数据集" : "请先指定实体类型")
                : "请选择实体类型" }}
          </option>
          <option
            v-for="t in availableEntityTypes"
            :key="t"
            :value="t"
          >
            {{ t }}
          </option>
        </select>
      </div>
      <p
        v-if="!entityTypesLoading && availableEntityTypes.length === 0 && catalogId"
        class="text-[var(--text-micro)] text-amber-600"
        data-testid="entity-type-empty-hint"
      >
        <template v-if="datasetsCount === 0">
          该数据库尚未上传数据集。请前往「数据集」tab 上传 CSV 文件以发现 entity_type。
        </template>
        <template v-else>
          现有 {{ datasetsCount }} 个数据集未指定 entity_type。点击数据集行右侧的「编辑」按钮，设置 entity_type（如 customer / bill / course）。
        </template>
      </p>
      <input
        v-model="question"
        placeholder="输入自然语言问题"
        class="border border-[var(--color-border)] rounded px-2 py-1 w-full bg-[var(--color-bg)] text-[var(--color-ink)]"
        required
      />
      <button
        type="submit"
        :disabled="loading"
        class="ui-btn-primary px-4 py-2 rounded disabled:opacity-50"
      >
        {{ loading ? "查询中..." : "查询" }}
      </button>
    </form>

    <div v-if="result" class="border border-[var(--color-border)] rounded p-4 space-y-2">
      <div v-if="result.ok">
        <p class="font-semibold">{{ result.summary }}</p>
        <p class="text-sm text-[var(--color-ink-tertiary)]">
          共 {{ result.result_count }} 条记录 ({{ result.duration_ms }}ms) ·
          置信度: {{ result.confidence }}
        </p>
        <details>
          <summary class="cursor-pointer">Query Plan</summary>
          <pre class="text-xs bg-[var(--color-bg-hover)] p-2 rounded">{{ JSON.stringify(result.query_plan, null, 2) }}</pre>
        </details>
        <details>
          <summary class="cursor-pointer">结果 ({{ result.result_count }} 行)</summary>
          <table v-if="result.result_rows && result.result_rows.length" class="w-full text-sm">
            <thead>
              <tr>
                <th v-for="col in resultColumns" :key="col">{{ col }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in result.result_rows.slice(0, 20)" :key="i">
                <td v-for="col in resultColumns" :key="col">{{ row[col] }}</td>
              </tr>
            </tbody>
          </table>
        </details>
        <div v-if="result.caveats && result.caveats.length" class="text-sm text-amber-600">
          <p class="font-semibold">注意事项:</p>
          <ul class="list-disc pl-5">
            <li v-for="(c, i) in result.caveats" :key="i">{{ c }}</li>
          </ul>
        </div>
      </div>
      <div v-else class="text-red-600">
        <p class="font-semibold">查询失败</p>
        <ul class="list-disc pl-5">
          <li v-for="(e, i) in result.errors || []" :key="i">{{ e }}</li>
        </ul>
        <p v-if="result.suggestion">建议: {{ result.suggestion }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * REQ-052 Task 6 + REQ-054 Task 8 + review fix + BUG-015: 前端问数面板。
 *
 * - REQ-054 加 数据库 select（catalog store 加载），与 entity_type 联动。
 * - `catalogId` 可由父组件 `preSelectedCatalogId` prop 锁定（来自 CatalogDetailPage）。
 * - 历史写入 Pinia store (`useQueryHistory`)，最多保留 10 条。
 *
 * REQ-054 review fix #5: entity_type 下拉从 datasets 动态聚合。
 * - 切换 catalog 时调 `listDatasets({ catalog_id })` 获取该库数据集，
 *   聚合 DISTINCT entity_type 填充下拉（不再 hardcoded bill/contract/customer）。
 * - 该库无数据集时下拉为空 + 提示「请先上传数据集」。
 *
 * BUG-015: 移除了原 `企业全称（已确认）` 与 `查询背景（≥5 字）` 两个冗余输入框。
 * 改问只用 `question` 一项发送 `AskRequest`，`business_purpose` 改为可选；entity_type
 * 空提示文案增加 "上传 CSV" 的具体指引，告诉用户去「数据集」tab 如何发现 entity_type。
 */
import { ref, computed, watch, onMounted } from "vue";
import { ask, type AskRequest, type AskResponse } from "@/services/data-query";
import { useQueryHistory } from "@/stores/query-history";
import { useCatalogStore } from "@/stores/catalog";
import { structuredDataApi } from "@/services/structured-data";

const props = withDefaults(
  defineProps<{
    datasetId?: string;
    preSelectedCatalogId?: string | null;
  }>(),
  {
    datasetId: "",
    preSelectedCatalogId: null,
  },
);

const catalogStore = useCatalogStore();
const catalogs = computed(() => catalogStore.catalogs);
const lockedCatalogId = computed(() => props.preSelectedCatalogId ?? null);

const catalogId = ref("");
const entityType = ref("");
const question = ref("");
const loading = ref(false);
const result = ref<AskResponse | null>(null);
const history = useQueryHistory();

// REQ-054 review fix #5: entity_type 从该 catalog 的 datasets 动态聚合。
const discoveredEntityTypes = ref<string[]>([]);
const entityTypesLoading = ref(false);
// REQ-054 bugfix: track raw dataset count so the empty hint distinguishes
// "no datasets" (upload first) from "datasets exist but entity_type NULL"
// (assign entity_type in the datasets tab).
const datasetsCount = ref(0);

const availableEntityTypes = computed(() => discoveredEntityTypes.value);

const resultColumns = computed(() => {
  if (!result.value?.result_rows || result.value.result_rows.length === 0) return [];
  return Object.keys(result.value.result_rows[0]);
});

async function loadEntityTypes(catId: string) {
  if (!catId) {
    discoveredEntityTypes.value = [];
    datasetsCount.value = 0;
    return;
  }
  entityTypesLoading.value = true;
  try {
    const res = await structuredDataApi.listDatasets({ catalog_id: catId });
    datasetsCount.value = res.data.length;
    const types = new Set<string>();
    for (const ds of res.data) {
      if (ds.entity_type) types.add(ds.entity_type);
    }
    discoveredEntityTypes.value = Array.from(types).sort();
  } catch {
    discoveredEntityTypes.value = [];
    datasetsCount.value = 0;
  } finally {
    entityTypesLoading.value = false;
  }
}

onMounted(async () => {
  if (catalogs.value.length === 0) {
    try {
      await catalogStore.fetch();
    } catch {
      // toast handled by QueryCache.onError in main.ts
    }
  }
  // Initialize selection: locked > first available
  if (lockedCatalogId.value) {
    catalogId.value = lockedCatalogId.value;
  } else if (catalogs.value.length > 0) {
    catalogId.value = catalogs.value[0].id;
  }
  await loadEntityTypes(catalogId.value);
});

// 切换 catalog 时重新拉取该库的 entity_types。
watch(catalogId, (next) => {
  void loadEntityTypes(next);
});

// entity_types 加载后，若当前选中不在列表内则重置为第一个。
watch(availableEntityTypes, (types) => {
  if (types.length > 0 && !types.includes(entityType.value)) {
    entityType.value = types[0];
  } else if (types.length === 0) {
    entityType.value = "";
  }
});

async function onAsk() {
  if (!catalogId.value) return;
  if (!question.value.trim()) return;
  loading.value = true;
  result.value = null;
  try {
    const req: AskRequest = {
      catalog_id: catalogId.value,
      entity_type: entityType.value,
      question: question.value,
    };
    const res = await ask(req);
    result.value = res;
    history.add(req, res);
  } catch (err: unknown) {
    const responseData = (err as { response?: { data?: unknown } })?.response?.data;
    if (responseData && typeof responseData === "object") {
      result.value = responseData as AskResponse;
    } else {
      const message = err instanceof Error ? err.message : "网络错误，请重试";
      result.value = {
        ok: false,
        errors: [message],
        suggestion: "请检查网络连接或稍后重试",
      } as AskResponse;
    }
  } finally {
    loading.value = false;
  }
}
</script>
