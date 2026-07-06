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
      <select
        v-model="entityType"
        class="border border-[var(--color-border)] rounded px-2 py-1 bg-[var(--color-bg)] text-[var(--color-ink)]"
      >
        <option value="bill">账单 (bill)</option>
        <option value="contract">合同 (contract)</option>
        <option value="ticket">工单 (ticket)</option>
      </select>
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
 * REQ-052 Task 6: 前端问数面板。
 *
 * - entity_type / question / business_purpose 必填，business_purpose 服务端 ≥5 字 + UI 双重 enforce。
 * - `datasetId` 是 informational prop，不影响请求体；用户选择 entity_type 决定查询范围。
 * - 历史写入 Pinia store (`useQueryHistory`)，最多保留 10 条。
 */
import { ref, computed } from "vue";
import { ask, type AskRequest, type AskResponse } from "@/services/data-query";
import { useQueryHistory } from "@/stores/query-history";

withDefaults(
  defineProps<{
    datasetId?: string;
  }>(),
  {
    datasetId: "",
  },
);

const entityType = ref("bill");
const question = ref("");
const companyName = ref("");
const businessPurpose = ref("");
const loading = ref(false);
const result = ref<AskResponse | null>(null);
const history = useQueryHistory();

const resultColumns = computed(() => {
  if (!result.value?.result_rows || result.value.result_rows.length === 0) return [];
  return Object.keys(result.value.result_rows[0]);
});

async function onAsk() {
  // 客户端二次校验：question 必填 + business_purpose ≥5 字（与后端 pydantic 双重 enforce）。
  if (!question.value.trim() || businessPurpose.value.trim().length < 5) return;
  loading.value = true;
  result.value = null;
  try {
    const req: AskRequest = {
      entity_type: entityType.value,
      question: question.value,
      business_purpose: businessPurpose.value,
      ...(companyName.value ? { confirmed_company_name: companyName.value } : {}),
    };
    const res = await ask(req);
    result.value = res;
    history.add(req, res);
  } finally {
    loading.value = false;
  }
}
</script>