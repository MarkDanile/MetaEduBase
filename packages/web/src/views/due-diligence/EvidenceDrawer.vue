<template>
  <Teleport to="body">
    <div v-if="open" class="drawer-mask" data-testid="evidence-drawer" @click.self="emit('close')">
      <div class="drawer-panel" role="dialog" aria-label="证据来源">
        <div class="drawer-head">
          <span class="drawer-title">证据来源</span>
          <button class="ui-btn ui-btn-ghost" data-testid="drawer-close" @click="emit('close')">关闭</button>
        </div>
        <p class="drawer-hint">
          每条关键事实可回溯到一次外部工具调用（mcp_invocation）或内部问数（data_query）。
          仅展示非敏感摘要与审计 id，不含原始企业事实。
        </p>

        <LoadingSpinner v-if="loading" text="加载证据..." />
        <EmptyState
          v-else-if="items.length === 0"
          title="暂无证据"
          hint="报告生成时未记录可回溯证据"
        />
        <div v-else class="evidence-list">
          <div
            v-for="ev in items"
            :key="ev.id"
            class="evidence-row"
            data-testid="evidence-row"
          >
            <div class="evidence-top">
              <span class="ui-tag" :class="ev.evidence_type === 'data_query' ? 'tag-query' : 'tag-mcp'">
                {{ ev.evidence_type === "data_query" ? "内部问数" : "外部工具" }}
              </span>
              <span v-if="ev.section" class="evidence-section">{{ ev.section }}</span>
            </div>
            <div v-if="ev.summary" class="evidence-summary">{{ ev.summary }}</div>
            <div v-if="ev.ref_id" class="evidence-ref" data-testid="evidence-ref">
              ref {{ ev.ref_id }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import EmptyState from "@/components/EmptyState.vue";
import { useToast } from "@/composables/useToast";
import { listEvidence, type DdEvidence } from "@/services/dueDiligence";

const props = defineProps<{
  open: boolean;
  reportId: string;
}>();
const emit = defineEmits<{ close: [] }>();

const toast = useToast();
const items = ref<DdEvidence[]>([]);
const loading = ref(false);

interface AxiosLikeError {
  response?: { data?: { detail?: string } };
}
function errorDetail(e: unknown, fallback: string): string {
  return (e as AxiosLikeError).response?.data?.detail ?? fallback;
}

async function load() {
  loading.value = true;
  try {
    items.value = await listEvidence(props.reportId);
  } catch (e) {
    toast.error(errorDetail(e, "加载证据失败"));
    items.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.open,
  (val) => {
    if (val) load();
  },
);
</script>

<style scoped>
.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  justify-content: flex-end;
  z-index: 1000;
}
.drawer-panel {
  background: white;
  width: 100%;
  max-width: 440px;
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  box-shadow: -10px 0 40px rgba(0, 0, 0, 0.15);
}
.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.drawer-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-ink);
}
.drawer-hint {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  line-height: 1.5;
  margin-bottom: 14px;
}
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.evidence-row {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
}
.evidence-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.evidence-section {
  font-size: 12px;
  color: var(--color-ink-secondary);
}
.evidence-summary {
  font-size: 13px;
  color: var(--color-ink);
  line-height: 1.5;
  margin-bottom: 6px;
}
.evidence-ref {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  font-family: monospace;
  word-break: break-all;
}
.tag-mcp { background: #eef2ff; color: #4338ca; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.tag-query { background: rgba(34, 197, 94, 0.12); color: #15803d; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
</style>
