<template>
  <section class="ws-pane" aria-label="会话列表">
    <div class="ws-list-head">
      <div class="ws-list-tabs" role="tablist" aria-label="会话状态">
        <button
          role="tab"
          class="ws-tab"
          :class="{ active: store.listState === 'active' }"
          :aria-selected="store.listState === 'active'"
          data-testid="ws-tab-active"
          @click="store.setListState('active')"
        >
          进行中
        </button>
        <button
          role="tab"
          class="ws-tab"
          :class="{ active: store.listState === 'archived' }"
          :aria-selected="store.listState === 'archived'"
          data-testid="ws-tab-archived"
          @click="store.setListState('archived')"
        >
          已归档
        </button>
      </div>
      <button
        class="ui-btn ui-btn-primary ws-new-btn"
        data-testid="ws-new-conversation"
        :disabled="creating"
        @click="onCreate"
      >
        <Plus :size="15" aria-hidden="true" /> {{ creating ? "创建中..." : "新会话" }}
      </button>
    </div>

    <div class="ws-search">
      <Search :size="15" class="ws-search-icon" aria-hidden="true" />
      <input
        v-model="searchInput"
        class="ui-input ws-search-input"
        type="search"
        placeholder="搜索会话标题（≥2 字）"
        aria-label="搜索会话"
        data-testid="ws-search"
        @input="onSearchInput"
      />
    </div>

    <div class="ws-pane-body">
      <LoadingSpinner
        v-if="store.conversationsLoading && store.conversations.length === 0"
        text="加载会话..."
      />
      <div v-else-if="store.conversationsError" class="ws-error" role="alert">
        <p class="ws-error-text">{{ store.conversationsError }}</p>
        <button class="ui-btn ui-btn-ghost" @click="reload">重试</button>
      </div>
      <div v-else-if="store.conversationsEmpty" class="ws-empty-wrap">
        <EmptyState :title="emptyTitle" :hint="emptyHint" />
      </div>
      <ul v-else class="ws-conv-list">
        <li v-for="conv in store.conversations" :key="conv.id">
          <div
            class="ws-conv-item ui-interactive-row"
            :class="{ selected: conv.id === store.selectedId }"
            :data-testid="`ws-conv-${conv.id}`"
          >
            <button class="ws-conv-main" @click="onSelect(conv)">
              <span class="ws-conv-title">
                <Pin
                  v-if="conv.pinned_at"
                  :size="13"
                  class="ws-pin-icon"
                  aria-label="已置顶"
                />
                <span class="ws-conv-title-text">{{ conv.title ?? "未命名会话" }}</span>
              </span>
              <span class="ws-conv-meta">
                <span
                  v-if="conv.state === 'archived'"
                  class="ui-tag"
                  :class="conversationState(conv.state).tag"
                >
                  {{ conversationState(conv.state).label }}
                </span>
                <span class="ws-conv-time">{{ formatTime(conv.last_activity_at) }}</span>
              </span>
            </button>
            <div class="ws-conv-actions">
              <button
                class="ws-icon-btn"
                :aria-label="conv.pinned_at ? '取消置顶' : '置顶'"
                :title="conv.pinned_at ? '取消置顶' : '置顶'"
                @click.stop="onTogglePin(conv)"
              >
                <Pin :size="14" aria-hidden="true" />
              </button>
              <button
                v-if="conv.state === 'archived'"
                class="ws-icon-btn"
                aria-label="恢复会话"
                title="恢复"
                @click.stop="onRestore(conv)"
              >
                <ArchiveRestore :size="14" aria-hidden="true" />
              </button>
            </div>
          </div>
        </li>
      </ul>
      <div v-if="store.conversationsHasMore" class="ws-load-more">
        <button
          class="ui-btn ui-btn-ghost"
          :disabled="store.conversationsLoading"
          data-testid="ws-load-more-conversations"
          @click="store.loadMoreConversations()"
        >
          {{ store.conversationsLoading ? "加载中..." : "加载更多" }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ArchiveRestore, Pin, Plus, Search } from "lucide-vue-next";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { useToast } from "@/composables/useToast";
import { parseApiError, type ConversationDTO } from "@/services/agentWorkspace";
import { useWorkspaceStore } from "@/stores/workspace";
import { conversationState } from "../status";
import { formatTime } from "../time";

const store = useWorkspaceStore();
const router = useRouter();
const toast = useToast();

const creating = ref(false);
const searchInput = ref(store.searchQuery);

const emptyTitle = computed(() => {
  if (store.searchQuery.trim().length >= 2) return "未找到匹配会话";
  return store.listState === "archived" ? "暂无已归档会话" : "暂无会话";
});
const emptyHint = computed(() => {
  if (store.searchQuery.trim().length >= 2) return "换个关键词试试";
  return store.listState === "archived"
    ? "归档的会话会出现在这里"
    : "点击右上角「新会话」开始";
});

// 搜索防抖：提交到 store（重置 keyset cursor 重新拉取）。
let searchTimer: number | undefined;
function onSearchInput(): void {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => {
    void store.setSearch(searchInput.value);
  }, 300);
}
onUnmounted(() => window.clearTimeout(searchTimer));

function onSelect(conv: ConversationDTO): void {
  if (conv.id === store.selectedId) return;
  void router.push({ name: "agent-workspace", query: { c: conv.id } });
}

async function onCreate(): Promise<void> {
  creating.value = true;
  try {
    const conv = await store.createNewConversation();
    toast.success("已创建会话");
    void router.push({ name: "agent-workspace", query: { c: conv.id } });
  } catch (e) {
    toast.error(parseApiError(e, "创建会话失败").message);
  } finally {
    creating.value = false;
  }
}

async function onTogglePin(conv: ConversationDTO): Promise<void> {
  try {
    await store.togglePin(conv);
  } catch (e) {
    toast.error(parseApiError(e, "操作失败").message);
  }
}

async function onRestore(conv: ConversationDTO): Promise<void> {
  try {
    await store.restoreConversationById(conv);
    toast.success("已恢复会话");
  } catch (e) {
    toast.error(parseApiError(e, "恢复失败").message);
  }
}

function reload(): void {
  void store.loadConversations(true);
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

.ws-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.ws-list-tabs {
  display: flex;
  gap: 2px;
  background: var(--color-bg-base);
  border-radius: var(--radius-sm);
  padding: 2px;
}

.ws-tab {
  border: none;
  background: none;
  padding: 4px 10px;
  font-size: var(--text-small);
  color: var(--color-ink-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
}

.ws-tab.active {
  background: var(--color-bg-elevated);
  color: var(--color-ink);
  font-weight: 500;
  box-shadow: var(--surface-card-shadow);
}

.ws-new-btn {
  flex-shrink: 0;
}

.ws-search {
  position: relative;
  padding: 10px 12px 0;
}

.ws-search-icon {
  position: absolute;
  left: 22px;
  top: 50%;
  transform: translateY(calc(-50% + 5px));
  color: var(--color-ink-tertiary);
  pointer-events: none;
}

.ws-search-input {
  width: 100%;
  padding-left: 32px;
}

.ws-pane-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
}

.ws-conv-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ws-conv-item {
  display: flex;
  align-items: center;
  border-radius: var(--radius-sm);
}

.ws-conv-item.selected {
  background: var(--color-accent-bg);
}

.ws-conv-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  border: none;
  background: none;
  text-align: left;
  cursor: pointer;
}

.ws-conv-title {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-caption);
  color: var(--color-ink);
  font-weight: 500;
}

.ws-conv-title-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ws-pin-icon {
  color: var(--color-accent);
  flex-shrink: 0;
}

.ws-conv-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ws-conv-time {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
}

.ws-conv-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  padding-right: 6px;
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.ws-conv-item:hover .ws-conv-actions,
.ws-conv-item.selected .ws-conv-actions {
  opacity: 1;
}

.ws-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  border-radius: var(--radius-sm);
  color: var(--color-ink-tertiary);
  cursor: pointer;
}

.ws-icon-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-ink);
}

.ws-load-more {
  padding: 8px;
  text-align: center;
}

.ws-error {
  padding: 16px;
  text-align: center;
}

.ws-error-text {
  color: var(--color-danger);
  font-size: var(--text-caption);
  margin-bottom: 8px;
}

.ws-empty-wrap {
  padding: 8px;
}

@media (prefers-reduced-motion: reduce) {
  .ws-conv-actions {
    transition: none;
  }
}
</style>
