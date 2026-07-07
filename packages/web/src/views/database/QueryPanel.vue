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
        >
          <option v-if="!availableEntityTypes.length" value="bill">账单 (bill)</option>
          <option
            v-for="t in availableEntityTypes"
            :key="t"
            :value="t"
          >
            {{ entityTypeLabel(t) }}
          </option>
        </select>
      </div>
      <input
        v-model="question"
        placeholder="输入自然语言问题"
        class="border border-[var(--color-border)] rounded px-2 py-1 w-full bg-[var(--color-bg)] text-[var(--color-ink)]"
        required
      />
      <input
        v-model="companyName"
        placeholder="企业全称（已确认）"
        class="border border-[var(--color-border)] rounded px-2 py-1 w-full bg-[var(--color-bg)] text-[var(--color-ink)]"
      />
      <input
        v-model="businessPurpose"
        placeholder="查询背景（必填，≥5 字）"
        class="border border-[var(--color-border)] rounded px-2 py-1 w-full bg-[var(--color-bg)] text-[var(--color-ink)]"
        minlength="5"
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
 * REQ-052 Task 6 + REQ-054 Task 8: 前端问数面板。
 *
 * - REQ-054 加 数据库 select（catalog store 加载），与 entity_type 联动：
 *   切换 catalog 时，entity_type 选项重置为新 catalog 的 entity_types 白名单。
 * - `catalogId` 可由父组件 `preSelectedCatalogId` prop 锁定（来自 CatalogDetailPage）。
 * - `entity_type` / `question` / `business_purpose` 必填，business_purpose 服务端 ≥5 字。
 * - 历史写入 Pinia store (`useQueryHistory`)，最多保留 10 条。
 */
import { ref, computed, watch, onMounted } from "vue";
import { ask, type AskRequest, type AskResponse } from "@/services/data-query";
import { useQueryHistory } from "@/stores/query-history";
import { useCatalogStore } from "@/stores/catalog";

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

const ENTITY_TYPE_LABELS: Record<string, string> = {
  bill: "账单 (bill)",
  contract: "合同 (contract)",
  ticket: "工单 (ticket)",
  invoice: "发票 (invoice)",
  customer: "客户 (customer)",
};

function entityTypeLabel(t: string) {
  return ENTITY_TYPE_LABELS[t] ?? t;
}

const catalogStore = useCatalogStore();
const catalogs = computed(() => catalogStore.catalogs);
const lockedCatalogId = computed(() => props.preSelectedCatalogId ?? null);

const catalogId = ref("");
const entityType = ref("bill");
const question = ref("");
const companyName = ref("");
const businessPurpose = ref("");
const loading = ref(false);
const result = ref<AskResponse | null>(null);
const history = useQueryHistory();

const availableEntityTypes = computed(() => {
  const current = catalogs.value.find((c) => c.id === catalogId.value);
  return current?.entity_types ?? [];
});

const resultColumns = computed(() => {
  if (!result.value?.result_rows || result.value.result_rows.length === 0) return [];
  return Object.keys(result.value.result_rows[0]);
});

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
});

watch(catalogId, () => {
  // Reset entity_type to first available in selected catalog
  const entityTypes = availableEntityTypes.value;
  if (entityTypes.length > 0 && !entityTypes.includes(entityType.value)) {
    entityType.value = entityTypes[0];
  }
});

async function onAsk() {
  if (!catalogId.value) return;
  if (!question.value.trim() || businessPurpose.value.trim().length < 5) return;
  loading.value = true;
  result.value = null;
  try {
    const req: AskRequest = {
      catalog_id: catalogId.value,
      entity_type: entityType.value,
      question: question.value,
      business_purpose: businessPurpose.value,
      ...(companyName.value ? { confirmed_company_name: companyName.value } : {}),
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
