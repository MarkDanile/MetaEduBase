<template>
  <section class="ws-pane" aria-label="运行详情">
    <div class="ws-run-head">
      <h2 class="ws-run-title">运行详情</h2>
    </div>

    <div class="ws-pane-body">
      <LoadingSpinner v-if="store.runLoading" text="加载运行详情..." />

      <div v-else-if="store.runUnavailable" class="ws-empty-wrap">
        <EmptyState title="运行不可用" hint="该运行不存在、已被清理或你无权查看" />
      </div>

      <div v-else-if="store.runError" class="ws-error" role="alert">
        <p class="ws-error-text">{{ store.runError }}</p>
        <button class="ui-btn ui-btn-ghost" @click="retry">重试</button>
      </div>

      <div v-else-if="!store.run" class="ws-empty-wrap">
        <EmptyState
          title="暂无运行"
          hint="该会话尚无关联运行。运行将在提交功能开放后产生"
        />
      </div>

      <div v-else class="ws-run-detail" data-testid="ws-run-detail">
        <div class="ws-run-status-row">
          <span
            class="ui-tag"
            :class="runStatus(store.run.status).tag"
            data-testid="ws-run-status"
          >
            {{ runStatus(store.run.status).label }}
          </span>
          <span v-if="isTerminal(store.run.status)" class="ui-tag ui-tag-green">终态</span>
          <span v-else class="ui-tag ui-tag-blue">进行中</span>
        </div>

        <dl class="ws-run-fields">
          <div class="ws-field">
            <dt>运行 ID</dt>
            <dd class="ws-mono" data-testid="ws-run-id">{{ store.run.id }}</dd>
          </div>
          <div class="ws-field">
            <dt>队列序号</dt>
            <dd data-testid="ws-run-queue-seq">{{ store.run.queue_seq }}</dd>
          </div>
          <div class="ws-field">
            <dt>事件序号窗口</dt>
            <dd data-testid="ws-run-event-window">
              {{ store.run.first_available_event_seq }} – {{ store.run.last_event_seq }}
            </dd>
          </div>
          <div class="ws-field">
            <dt>事件日志完整性</dt>
            <dd>{{ store.run.event_log_complete ? "完整" : "不完整" }}</dd>
          </div>
          <div class="ws-field">
            <dt>输出发布状态</dt>
            <dd>
              <span class="ui-tag" :class="outputPublishState(store.run.output_publish_state).tag">
                {{ outputPublishState(store.run.output_publish_state).label }}
              </span>
            </dd>
          </div>
          <div v-if="store.run.terminal_code" class="ws-field">
            <dt>终态码</dt>
            <dd class="ws-mono">{{ store.run.terminal_code }}</dd>
          </div>
          <div v-if="store.run.terminal_reason" class="ws-field">
            <dt>终态原因</dt>
            <dd>{{ store.run.terminal_reason }}</dd>
          </div>
          <div class="ws-field">
            <dt>入队时间</dt>
            <dd>{{ formatFullTime(store.run.queued_at) }}</dd>
          </div>
          <div v-if="store.run.started_at" class="ws-field">
            <dt>开始时间</dt>
            <dd>{{ formatFullTime(store.run.started_at) }}</dd>
          </div>
          <div v-if="store.run.ended_at" class="ws-field">
            <dt>结束时间</dt>
            <dd>{{ formatFullTime(store.run.ended_at) }}</dd>
          </div>
        </dl>

        <div v-if="usageEntries.length" class="ws-usage">
          <h3 class="ws-usage-title">用量</h3>
          <dl class="ws-run-fields">
            <div v-for="[key, value] in usageEntries" :key="key" class="ws-field">
              <dt class="ws-mono">{{ key }}</dt>
              <dd>{{ value }}</dd>
            </div>
          </dl>
        </div>

        <p class="ws-run-note">只读视图。事件流、取消、审批等能力将在后续迭代开放。</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from "vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { TERMINAL_RUN_STATUSES } from "@/services/agentWorkspace";
import { useWorkspaceStore } from "@/stores/workspace";
import { outputPublishState, runStatus } from "../status";
import { formatFullTime } from "../time";

const store = useWorkspaceStore();

function isTerminal(status: string): boolean {
  return TERMINAL_RUN_STATUSES.has(status);
}

const usageEntries = computed(() => Object.entries(store.run?.usage ?? {}));

function retry(): void {
  if (store.selectedRunId) void store.selectRun(store.selectedRunId);
}
</script>

<style scoped>
.ws-pane {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.ws-run-head {
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.ws-run-title {
  font-size: var(--text-subtitle);
  font-weight: 600;
  color: var(--color-ink);
  margin: 0;
}

.ws-pane-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
}

.ws-run-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ws-run-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ws-run-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
}

.ws-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ws-field dt {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
  text-transform: none;
}

.ws-field dd {
  font-size: var(--text-caption);
  color: var(--color-ink);
  margin: 0;
  word-break: break-all;
}

.ws-mono {
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: var(--text-small);
}

.ws-usage-title {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--color-ink);
  margin: 0 0 6px;
}

.ws-run-note {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
  border-top: 1px solid var(--color-border-subtle);
  padding-top: 10px;
  margin: 0;
}

.ws-error {
  text-align: center;
  padding: 16px 0;
}

.ws-error-text {
  color: var(--color-danger);
  font-size: var(--text-caption);
  margin-bottom: 8px;
}

.ws-empty-wrap {
  padding: 8px 0;
}
</style>
