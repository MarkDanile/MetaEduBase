<template>
  <div class="p-6">
    <PageHeader title="背调报告" :subtitle="report ? `版本 v${report.version}` : ''">
      <template #extra>
        <div class="flex items-center gap-2">
          <button class="ui-btn ui-btn-ghost" data-testid="back-task-btn" @click="goTask">
            <ArrowLeft :size="16" /> 返回任务
          </button>
          <button
            v-if="report"
            class="ui-btn ui-btn-ghost"
            data-testid="evidence-btn"
            @click="showEvidence = true"
          >
            <FileSearch :size="16" /> 证据来源
          </button>
          <button
            v-if="report && report.status === 'draft'"
            class="ui-btn ui-btn-primary"
            data-testid="confirm-report-btn"
            :disabled="acting"
            @click="doConfirm"
          >
            确认锁版
          </button>
          <button
            v-if="report && report.status !== 'archived'"
            class="ui-btn ui-btn-ghost"
            data-testid="archive-report-btn"
            :disabled="acting"
            @click="showArchive = true"
          >
            归档
          </button>
        </div>
      </template>
    </PageHeader>

    <LoadingSpinner v-if="loading" text="加载报告..." />
    <EmptyState v-else-if="!report" title="报告不存在" hint="该报告可能已被删除或不属于当前租户" />

    <div v-else class="mt-4 space-y-4">
      <div class="report-meta" data-testid="report-meta">
        <span class="ui-tag" :class="reportStatus(report.status).tag" data-testid="report-status">
          {{ reportStatus(report.status).label }}
        </span>
        <span v-if="report.confirmed_by" class="meta-item" data-testid="confirmed-by">
          已确认 · {{ formatDate(report.confirmed_at) }}
        </span>
        <span v-if="report.skill_execution_audit_id" class="meta-item meta-mono">
          审计 {{ report.skill_execution_audit_id.slice(0, 8) }}
        </span>
      </div>

      <!-- 结构化企业画像（§4.6 七键） -->
      <div class="report-grid" data-testid="report-grid">
        <ReportSection title="摘要" :items="report.report_json.summary" testid="sec-summary" />
        <ReportSection title="外部事实（企查查）" :items="report.report_json.external_facts" testid="sec-external" />
        <ReportSection title="内部事实（园区）" :items="report.report_json.internal_facts" testid="sec-internal" />
        <ReportSection title="风险关注点" :items="report.report_json.risk_watch_items" testid="sec-risk" tone="risk" />
        <ReportSection title="待人工确认项" :items="report.report_json.human_review_items" testid="sec-review" tone="review" />

        <div v-if="report.report_json.report_sections?.length" class="panel" data-testid="sec-sections">
          <div class="panel-title">报告正文</div>
          <div
            v-for="(sec, i) in report.report_json.report_sections"
            :key="i"
            class="body-section"
          >
            <div class="body-section-title">{{ sec.title }}</div>
            <pre class="body-section-content">{{ sec.content }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 归档确认 -->
    <ConfirmDialog
      v-model:open="showArchive"
      title="归档报告"
      message="归档后报告进入只读存档，确定归档吗？"
      confirm-text="归档"
      danger
      @confirm="doArchive"
    />

    <!-- 证据来源抽屉 -->
    <EvidenceDrawer
      v-if="report"
      :open="showEvidence"
      :report-id="report.id"
      @close="showEvidence = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, FileSearch } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useToast } from "@/composables/useToast";
import {
  getReport,
  confirmReport,
  archiveReport,
  type DdReport,
} from "@/services/dueDiligence";
import ReportSection from "./ReportSection.vue";
import EvidenceDrawer from "./EvidenceDrawer.vue";
import { reportStatus } from "./status";

const route = useRoute();
const router = useRouter();
const toast = useToast();

const reportId = String(route.params.reportId ?? "");

const report = ref<DdReport | null>(null);
const loading = ref(false);
const acting = ref(false);
const showArchive = ref(false);
const showEvidence = ref(false);

interface AxiosLikeError {
  response?: { status?: number; data?: { detail?: string } };
}
function errorDetail(e: unknown, fallback: string): string {
  return (e as AxiosLikeError).response?.data?.detail ?? fallback;
}

function goTask() {
  if (report.value) {
    router.push({ name: "AppEnterprise360DdDetail", params: { id: report.value.task_id } });
  } else {
    router.push({ name: "AppEnterprise360Dd" });
  }
}

function formatDate(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

async function doConfirm() {
  acting.value = true;
  try {
    report.value = await confirmReport(reportId);
    toast.success("报告已确认锁版");
  } catch (e) {
    toast.error(errorDetail(e, "确认失败"));
  } finally {
    acting.value = false;
  }
}

async function doArchive() {
  acting.value = true;
  try {
    report.value = await archiveReport(reportId);
    toast.success("报告已归档");
  } catch (e) {
    toast.error(errorDetail(e, "归档失败"));
  } finally {
    acting.value = false;
  }
}

async function load() {
  loading.value = true;
  try {
    report.value = await getReport(reportId);
  } catch (e) {
    toast.error(errorDetail(e, "加载报告失败"));
    report.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.report-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}
.meta-item {
  font-size: 12px;
  color: var(--color-ink-tertiary);
}
.meta-mono {
  font-family: monospace;
}

.report-grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel {
  background: #ffffff;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
  margin-bottom: 10px;
}
.body-section {
  margin-bottom: 12px;
  border-left: 3px solid #6366f1;
  padding-left: 12px;
}
.body-section:last-child {
  margin-bottom: 0;
}
.body-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #4338ca;
  margin-bottom: 4px;
}
.body-section-content {
  font-size: 13px;
  color: var(--color-ink);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: var(--font-body);
  line-height: 1.6;
}

.ui-tag-amber { background: rgba(245, 158, 11, 0.12); color: #b45309; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.ui-tag-green { background: rgba(34, 197, 94, 0.12); color: #15803d; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.ui-tag-grey { background: #e5e7eb; color: #6b7280; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
</style>
