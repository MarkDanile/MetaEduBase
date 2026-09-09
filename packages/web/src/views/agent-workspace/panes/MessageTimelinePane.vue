<template>
  <section class="ws-pane" aria-label="消息时间线">
    <!-- 未选中会话 -->
    <div v-if="!store.selectedId" class="ws-pane-center-empty">
      <EmptyState title="选择一个会话" hint="从左侧列表选择或新建一个会话，查看其消息历史" />
    </div>

    <!-- 会话不可见（404 / 跨 owner / 已删除） -->
    <div v-else-if="store.selectedNotFound" class="ws-pane-center-empty">
      <EmptyState title="会话不可用" hint="该会话不存在、已被删除或你无权访问">
        <template #action>
          <button class="ui-btn ui-btn-ghost" @click="retrySelect">重试</button>
        </template>
      </EmptyState>
    </div>

    <template v-else>
      <!-- 头部：标题 + 生命周期操作 -->
      <header class="ws-timeline-head">
        <div class="ws-timeline-title">
          <template v-if="!renaming">
            <h2 class="ws-conv-heading" data-testid="ws-conv-heading">
              {{ store.selectedConversation?.title ?? "未命名会话" }}
            </h2>
            <span
              v-if="store.selectedConversation"
              class="ui-tag"
              :class="conversationState(store.selectedConversation.state).tag"
              data-testid="ws-conv-state"
            >
              {{ conversationState(store.selectedConversation.state).label }}
            </span>
          </template>
          <input
            v-else
            v-model="renameInput"
            class="ui-input ws-rename-input"
            aria-label="会话标题"
            data-testid="ws-rename-input"
            @keydown.enter="commitRename"
            @keydown.escape="cancelRename"
          />
        </div>
        <div class="ws-timeline-actions">
          <template v-if="!renaming">
            <button class="ui-btn ui-btn-ghost" data-testid="ws-rename-btn" @click="startRename">
              重命名
            </button>
            <button
              v-if="store.selectedConversation?.state === 'active'"
              class="ui-btn ui-btn-ghost"
              data-testid="ws-archive-btn"
              @click="onArchive"
            >
              归档
            </button>
            <button
              v-if="store.selectedConversation?.state === 'archived'"
              class="ui-btn ui-btn-ghost"
              data-testid="ws-restore-btn"
              @click="onRestore"
            >
              恢复
            </button>
            <button
              class="ui-btn ui-btn-ghost ws-danger"
              data-testid="ws-delete-btn"
              @click="askDelete"
            >
              删除
            </button>
          </template>
          <template v-else>
            <button class="ui-btn ui-btn-primary" data-testid="ws-rename-save" @click="commitRename">
              保存
            </button>
            <button class="ui-btn ui-btn-ghost" data-testid="ws-rename-cancel" @click="cancelRename">
              取消
            </button>
          </template>
        </div>
      </header>

      <!-- 消息体（独立滚动；prepend 时锚定视口防跳动） -->
      <div ref="scrollRef" class="ws-messages">
        <div v-if="store.messagesHasMoreOlder" class="ws-load-older">
          <button
            class="ui-btn ui-btn-ghost"
            :disabled="store.messagesLoadingOlder"
            data-testid="ws-load-older"
            @click="onLoadOlder"
          >
            {{ store.messagesLoadingOlder ? "加载中..." : "加载更早消息" }}
          </button>
        </div>

        <LoadingSpinner v-if="store.messagesLoading" text="加载消息..." />
        <div v-else-if="store.messagesError" class="ws-error" role="alert">
          <p class="ws-error-text">{{ store.messagesError }}</p>
          <button class="ui-btn ui-btn-ghost" data-testid="ws-messages-retry" @click="retrySelect">
            重试
          </button>
        </div>
        <div v-else-if="store.messagesEmpty" class="ws-empty-wrap">
          <EmptyState title="暂无消息" hint="该会话还没有消息记录" />
        </div>
        <ol v-else class="ws-msg-list">
          <li
            v-for="m in store.messages"
            :key="m.id"
            class="ws-msg"
            :class="`ws-msg-${authorSide(m)}`"
            :data-testid="`ws-msg-${m.seq}`"
          >
            <div class="ws-msg-bubble" :class="{ muted: m.content_state !== 'visible' }">
              <div class="ws-msg-meta">
                <span class="ui-tag" :class="messageAuthor(m.author_type).tag">
                  {{ messageAuthor(m.author_type).label }}
                </span>
                <span class="ws-msg-kind">{{ messageKind(m.kind).label }}</span>
                <span class="ws-msg-time">{{ formatFullTime(m.created_at) }}</span>
                <span class="ws-msg-seq">#{{ m.seq }}</span>
              </div>

              <div class="ws-msg-content">
                <span v-if="m.content_state === 'redacted'" class="ws-redacted">
                  内容已脱敏
                </span>
                <template v-else>
                  <p v-for="part in textParts(m)" :key="part.id" class="ws-msg-text">
                    {{ part.text }}
                  </p>
                  <div v-for="part in resourceParts(m)" :key="part.id" class="ws-resource-ref">
                    <Paperclip :size="13" aria-hidden="true" />
                    <span class="ws-resource-name">{{ part.display_name ?? part.resource_id }}</span>
                    <span v-if="part.media_type" class="ws-resource-type">{{ part.media_type }}</span>
                  </div>
                </template>
                <span
                  v-if="m.content_state === 'superseded'"
                  class="ui-tag ws-superseded"
                  :class="contentState(m.content_state).tag"
                >
                  {{ contentState(m.content_state).label }}
                </span>
              </div>

              <button
                v-if="runIdOf(m)"
                class="ws-run-link"
                :class="{ active: runIdOf(m) === store.selectedRunId }"
                :data-testid="`ws-run-link-${m.seq}`"
                @click="onShowRun(runIdOf(m)!)"
              >
                <Activity :size="13" aria-hidden="true" /> 运行详情
              </button>
            </div>
          </li>
        </ol>
      </div>

      <!-- 草稿 composer（非提交） -->
      <WorkspaceComposer
        v-if="store.selectedConversation"
        :conversation-id="store.selectedConversation.id"
        :disabled="store.selectedConversation.state !== 'active'"
      />
    </template>

    <ConfirmDialog
      v-model:open="showDelete"
      title="删除会话"
      message="删除后将从列表移除（服务端保留审计记录）。确定删除该会话吗？"
      confirm-text="删除"
      :danger="true"
      @confirm="onDelete"
    />
  </section>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Activity, Paperclip } from "lucide-vue-next";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { useToast } from "@/composables/useToast";
import {
  parseApiError,
  type MessageDTO,
  type MessagePartDTO,
} from "@/services/agentWorkspace";
import { useWorkspaceStore } from "@/stores/workspace";
import WorkspaceComposer from "./WorkspaceComposer.vue";
import { contentState, conversationState, messageAuthor, messageKind } from "../status";
import { formatFullTime } from "../time";

const store = useWorkspaceStore();
const router = useRouter();
const toast = useToast();

// 显式点击「运行详情」时通知 shell（移动端据此切到运行面板；数据仍走 store.selectRun）。
const emit = defineEmits<{ "show-run": [runId: string] }>();

// --- 重命名 ---
const renaming = ref(false);
const renameInput = ref("");

function startRename(): void {
  renameInput.value = store.selectedConversation?.title ?? "";
  renaming.value = true;
}
function cancelRename(): void {
  renaming.value = false;
}
async function commitRename(): Promise<void> {
  const title = renameInput.value.trim();
  renaming.value = false;
  if (!title || title === store.selectedConversation?.title) return;
  try {
    await store.renameSelected(title);
    toast.success("已重命名");
  } catch (e) {
    toast.error(parseApiError(e, "重命名失败").message);
  }
}

// --- 生命周期 ---
const showDelete = ref(false);

async function onArchive(): Promise<void> {
  try {
    await store.archiveSelected();
    toast.success("已归档");
  } catch (e) {
    toast.error(parseApiError(e, "归档失败").message);
  }
}

async function onRestore(): Promise<void> {
  const conv = store.selectedConversation;
  if (!conv) return;
  try {
    await store.restoreConversationById(conv);
    toast.success("已恢复");
  } catch (e) {
    toast.error(parseApiError(e, "恢复失败").message);
  }
}

function askDelete(): void {
  showDelete.value = true;
}

async function onDelete(): Promise<void> {
  try {
    await store.deleteSelected();
    toast.success("已删除会话");
    void router.push({ name: "agent-workspace" });
  } catch (e) {
    toast.error(parseApiError(e, "删除失败").message);
  }
}

// --- 消息渲染辅助 ---
function authorSide(m: MessageDTO): "user" | "other" {
  return m.author_type === "user" ? "user" : "other";
}
function textParts(m: MessageDTO): MessagePartDTO[] {
  return m.parts.filter((p) => p.type === "text" && p.text);
}
function resourceParts(m: MessageDTO): MessagePartDTO[] {
  return m.parts.filter((p) => p.type === "resource_ref");
}
function runIdOf(m: MessageDTO): string | null {
  return m.origin_run_id ?? m.requested_run_id;
}
function onShowRun(runId: string): void {
  void store.selectRun(runId);
  emit("show-run", runId);
}

function retrySelect(): void {
  if (store.selectedId) void store.selectConversation(store.selectedId);
}

// --- 滚动锚定：初次/切换滚到底部；prepend 更早消息时保持视口不跳动 ---
const scrollRef = ref<HTMLElement | null>(null);
let stickToBottom = true;
let prevScrollHeight = 0;

function onLoadOlder(): void {
  const el = scrollRef.value;
  if (el) prevScrollHeight = el.scrollHeight;
  stickToBottom = false;
  void store.loadOlderMessages();
}

watch(
  () => store.selectedId,
  () => {
    stickToBottom = true;
    prevScrollHeight = 0;
  },
);

watch(
  () => store.messages,
  async (newMsgs, oldMsgs) => {
    await nextTick();
    const el = scrollRef.value;
    if (!el) return;
    const isPrepend =
      newMsgs.length > 0 && oldMsgs.length > 0 && newMsgs[0].seq < oldMsgs[0].seq;
    if (isPrepend) {
      el.scrollTop = el.scrollHeight - prevScrollHeight + el.scrollTop;
    } else if (stickToBottom) {
      el.scrollTop = el.scrollHeight;
    }
  },
  { flush: "post" },
);
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

.ws-pane-center-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.ws-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border-subtle);
  flex-wrap: wrap;
}

.ws-timeline-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.ws-conv-heading {
  font-size: var(--text-subtitle);
  font-weight: 600;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0;
}

.ws-rename-input {
  flex: 1;
  min-width: 0;
}

.ws-timeline-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.ws-danger {
  color: var(--color-danger);
}

.ws-messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ws-load-older {
  text-align: center;
}

.ws-msg-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ws-msg {
  display: flex;
}

.ws-msg-user {
  justify-content: flex-end;
}

.ws-msg-other {
  justify-content: flex-start;
}

.ws-msg-bubble {
  max-width: 82%;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-subtle);
}

.ws-msg-user .ws-msg-bubble {
  background: var(--color-accent-bg);
  border-color: var(--color-border-accent);
}

.ws-msg-bubble.muted {
  opacity: 0.75;
}

.ws-msg-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.ws-msg-kind {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
}

.ws-msg-time {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
}

.ws-msg-seq {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
  font-variant-numeric: tabular-nums;
}

.ws-msg-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ws-msg-text {
  font-size: var(--text-body);
  color: var(--color-ink);
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.ws-redacted {
  font-size: var(--text-caption);
  color: var(--color-ink-tertiary);
  font-style: italic;
}

.ws-resource-ref {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-elevated);
  font-size: var(--text-small);
  color: var(--color-ink-secondary);
}

.ws-resource-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ws-resource-type {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
}

.ws-superseded {
  align-self: flex-start;
}

.ws-run-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 3px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: none;
  font-size: var(--text-small);
  color: var(--color-accent);
  cursor: pointer;
}

.ws-run-link:hover {
  background: var(--color-accent-bg);
}

.ws-run-link.active {
  background: var(--color-accent-bg);
  border-color: var(--color-border-accent);
  font-weight: 500;
}

.ws-error {
  text-align: center;
  padding: 16px;
}

.ws-error-text {
  color: var(--color-danger);
  font-size: var(--text-caption);
  margin-bottom: 8px;
}

.ws-empty-wrap {
  padding: 8px;
}
</style>
