<template>
  <div class="p-6">
    <PageHeader title="背调任务" :subtitle="task?.title ?? ''">
      <template #extra>
        <button class="ui-btn ui-btn-ghost" data-testid="back-btn" @click="goBack">
          <ArrowLeft :size="16" /> 返回列表
        </button>
      </template>
    </PageHeader>

    <LoadingSpinner v-if="loading" text="加载任务..." />
    <EmptyState v-else-if="!task" title="任务不存在" hint="该任务可能已被删除或不属于当前租户" />

    <div v-else class="mt-4 space-y-4">
      <!-- 状态时间线 -->
      <div class="panel" data-testid="status-panel">
        <div class="panel-head">
          <span class="panel-title">进度</span>
          <span class="ui-tag" :class="taskStatus(task.status).tag" data-testid="status-tag">
            {{ taskStatus(task.status).label }}
          </span>
        </div>
        <div class="timeline" data-testid="status-timeline">
          <div
            v-for="step in timeline"
            :key="step.key"
            class="tl-step"
            :class="{ 'is-done': step.done, 'is-current': step.current }"
            :data-testid="`tl-${step.key}`"
          >
            <span class="tl-dot" />
            <span class="tl-label">{{ step.label }}</span>
          </div>
        </div>
        <div v-if="task.status === 'failed'" class="tl-failed" data-testid="tl-failed">
          背调执行失败，可修正主体后重试。
        </div>
      </div>

      <!-- 主体确认卡 -->
      <div class="panel" data-testid="subject-panel">
        <div class="panel-head">
          <span class="panel-title">企业主体</span>
        </div>

        <!-- 已确认 -->
        <div v-if="task.confirmed_subject" class="subject-confirmed" data-testid="subject-confirmed">
          <Building2 :size="18" class="text-[var(--color-ink-tertiary)]" />
          <div>
            <div class="subject-name">{{ task.confirmed_subject.company_name }}</div>
            <div v-if="task.confirmed_subject.credit_code" class="subject-code">
              统一社会信用代码：{{ task.confirmed_subject.credit_code }}
            </div>
          </div>
        </div>

        <!-- 未确认：锚定 + 候选 -->
        <div v-else>
          <div class="subject-query">
            <span class="form-label">主体查询</span>
            <span class="subject-query-text" data-testid="subject-query">{{ task.subject_query }}</span>
            <button
              class="ui-btn ui-btn-primary"
              data-testid="resolve-btn"
              :disabled="resolving"
              @click="doResolve"
            >
              {{ resolving ? "锚定中..." : "锚定主体" }}
            </button>
          </div>

          <div v-if="candidates.length > 0" class="candidates" data-testid="candidates">
            <div class="form-label mb-2">选择要确认的主体（外部工商核验候选）</div>
            <label
              v-for="(c, i) in candidates"
              :key="i"
              class="candidate-row"
              :class="{ 'is-selected': selectedIndex === i }"
              :data-testid="`candidate-${i}`"
            >
              <input
                type="radio"
                name="candidate"
                class="candidate-radio"
                :checked="selectedIndex === i"
                @change="selectedIndex = i"
              />
              <span class="candidate-name">{{ c.company_name }}</span>
              <span v-if="c.credit_code" class="candidate-code">{{ c.credit_code }}</span>
            </label>
            <div class="flex justify-end mt-3">
              <button
                class="ui-btn ui-btn-primary"
                data-testid="confirm-subject-btn"
                :disabled="confirming || selectedIndex < 0"
                @click="doConfirmSubject"
              >
                {{ confirming ? "确认中..." : "确认主体" }}
              </button>
            </div>
          </div>
          <p v-else-if="resolvedOnce" class="no-candidate" data-testid="no-candidate">
            未找到候选主体，请检查主体查询关键词。
          </p>
        </div>
      </div>

      <!-- 运行背调 -->
      <div class="panel" data-testid="run-panel">
        <div class="panel-head">
          <span class="panel-title">运行背调</span>
        </div>
        <p class="run-hint">
          将编排外部（企查查）+ 内部客户 + 内部问数三类数据，生成企业画像报告草案与证据账本。
        </p>
        <button
          class="ui-btn ui-btn-primary"
          data-testid="run-btn"
          :disabled="!canRun || running"
          @click="doRun"
        >
          {{ running ? "背调中..." : "开始背调" }}
        </button>
        <p v-if="!canRun && task.status !== 'failed'" class="run-block" data-testid="run-blocked">
          需先确认企业主体后才能运行背调（AC-1）。
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Building2 } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { useToast } from "@/composables/useToast";
import {
  getTask,
  resolveSubject,
  confirmSubject,
  runTask,
  type DdTask,
  type SubjectCandidate,
} from "@/services/dueDiligence";
import { taskStatus } from "./status";

const route = useRoute();
const router = useRouter();
const toast = useToast();

const taskId = String(route.params.id ?? "");

const task = ref<DdTask | null>(null);
const loading = ref(false);

const candidates = ref<SubjectCandidate[]>([]);
const selectedIndex = ref(-1);
const resolving = ref(false);
const confirming = ref(false);
const resolvedOnce = ref(false);
const running = ref(false);

const canRun = computed(() => task.value?.status === "subject_confirmed" || task.value?.status === "failed");

const timeline = computed(() => {
  const s = task.value?.status ?? "";
  const reached = (key: string) => {
    const idx: Record<string, number> = {
      create: 0,
      resolve: 0,
      confirm: s === "subject_pending" ? -1 : 1,
      run: ["running", "review", "archived"].includes(s) ? 3 : s === "subject_confirmed" ? 2 : -1,
      review: ["review", "archived"].includes(s) ? 4 : -1,
    };
    return idx[key] >= 0;
  };
  const currentKey =
    s === "subject_pending" ? "confirm"
    : s === "subject_confirmed" ? "run"
    : s === "running" ? "run"
    : s === "review" ? "review"
    : s === "archived" ? "review"
    : "create";
  return [
    { key: "create", label: "创建", done: true, current: false },
    { key: "resolve", label: "锚定主体", done: reached("resolve"), current: false },
    { key: "confirm", label: "确认主体", done: reached("confirm"), current: currentKey === "confirm" },
    { key: "run", label: "运行背调", done: reached("run"), current: currentKey === "run" },
    { key: "review", label: "人工复核", done: reached("review"), current: currentKey === "review" },
  ];
});

interface AxiosLikeError {
  response?: { status?: number; data?: { detail?: string } };
}
function errorStatus(e: unknown): number | undefined {
  return (e as AxiosLikeError).response?.status;
}
function errorDetail(e: unknown, fallback: string): string {
  return (e as AxiosLikeError).response?.data?.detail ?? fallback;
}

function goBack() {
  router.push({ name: "AppEnterprise360Dd" });
}

async function doResolve() {
  resolving.value = true;
  resolvedOnce.value = false;
  try {
    candidates.value = await resolveSubject(taskId);
    selectedIndex.value = candidates.value.length > 0 ? 0 : -1;
    resolvedOnce.value = true;
    if (candidates.value.length === 0) toast.warning("未找到候选主体");
  } catch (e) {
    toast.error(errorDetail(e, "主体锚定失败"));
    candidates.value = [];
  } finally {
    resolving.value = false;
  }
}

async function doConfirmSubject() {
  const c = candidates.value[selectedIndex.value];
  if (!c) {
    toast.error("请先选择一个候选主体");
    return;
  }
  confirming.value = true;
  try {
    task.value = await confirmSubject(taskId, {
      company_name: c.company_name,
      credit_code: c.credit_code ?? null,
    });
    candidates.value = [];
    toast.success("主体已确认");
  } catch (e) {
    toast.error(errorDetail(e, "确认主体失败"));
  } finally {
    confirming.value = false;
  }
}

async function doRun() {
  running.value = true;
  try {
    const report = await runTask(taskId);
    toast.success("背调完成，已生成报告草案");
    router.push({ name: "AppEnterprise360DdReport", params: { reportId: report.id } });
  } catch (e) {
    const status = errorStatus(e);
    if (status === 422) toast.error(errorDetail(e, "任务未确认主体或不可运行"));
    else if (status === 502) toast.error(errorDetail(e, "背调执行失败（工具或模型错误）"));
    else toast.error(errorDetail(e, "背调执行失败"));
    await load();
  } finally {
    running.value = false;
  }
}

async function load() {
  loading.value = true;
  try {
    task.value = await getTask(taskId);
  } catch (e) {
    toast.error(errorDetail(e, "加载任务失败"));
    task.value = null;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.panel {
  background: #ffffff;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ink);
}

.timeline {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.tl-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--color-ink-tertiary);
}
.tl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d1d5db;
}
.tl-step.is-done {
  color: #15803d;
}
.tl-step.is-done .tl-dot {
  background: #22c55e;
}
.tl-step.is-current {
  color: #4338ca;
  font-weight: 600;
}
.tl-step.is-current .tl-dot {
  background: #6366f1;
  animation: tl-pulse 1.6s infinite;
}
@keyframes tl-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.tl-failed {
  margin-top: 10px;
  font-size: 12px;
  color: #b91c1c;
}

.subject-confirmed {
  display: flex;
  align-items: center;
  gap: 10px;
}
.subject-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-ink);
}
.subject-code {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  font-family: monospace;
}

.subject-query {
  display: flex;
  align-items: center;
  gap: 12px;
}
.subject-query-text {
  font-size: 14px;
  color: var(--color-ink);
  flex: 1;
}

.candidates {
  margin-top: 14px;
  border-top: 1px dashed #e5e7eb;
  padding-top: 12px;
}
.candidate-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
}
.candidate-row.is-selected {
  border-color: #6366f1;
  background: #eef2ff;
}
.candidate-radio {
  accent-color: #6366f1;
}
.candidate-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
}
.candidate-code {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  font-family: monospace;
}
.no-candidate {
  margin-top: 12px;
  font-size: 12px;
  color: #b45309;
}

.run-hint {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  margin-bottom: 12px;
  line-height: 1.5;
}
.run-block {
  margin-top: 10px;
  font-size: 12px;
  color: #b45309;
}

.form-label {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  font-weight: 500;
}

.ui-tag-blue { background: #eef2ff; color: #4338ca; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.ui-tag-amber { background: rgba(245, 158, 11, 0.12); color: #b45309; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.ui-tag-green { background: rgba(34, 197, 94, 0.12); color: #15803d; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.ui-tag-red { background: rgba(239, 68, 68, 0.1); color: #b91c1c; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.ui-tag-grey { background: #e5e7eb; color: #6b7280; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
</style>
