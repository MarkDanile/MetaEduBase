<template>
  <div class="ws-shell" data-testid="agent-workspace">
    <!-- 移动端面板切换（<768px 显示；REQ-042 窄屏抽屉/Tab 约定） -->
    <div class="ws-mobile-tabs md:hidden" role="tablist" aria-label="工作区面板">
      <button
        v-for="t in tabs"
        :key="t.key"
        role="tab"
        class="ws-mobile-tab"
        :class="{ active: activePane === t.key }"
        :aria-selected="activePane === t.key"
        :data-testid="`ws-mobile-tab-${t.key}`"
        @click="activePane = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- 三栏 grid（桌面）；移动端单栏 + v-show 切面板（保持挂载不丢状态） -->
    <div class="ws-grid">
      <ConversationListPane
        v-show="!isMobile || activePane === 'conversations'"
        class="ws-col ws-col-list"
      />
      <MessageTimelinePane
        v-show="!isMobile || activePane === 'messages'"
        class="ws-col ws-col-timeline"
        @show-run="onExplicitRun"
      />
      <RunDetailPane
        v-show="!isMobile || activePane === 'run'"
        class="ws-col ws-col-run"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useWorkspaceStore } from "@/stores/workspace";
import ConversationListPane from "./panes/ConversationListPane.vue";
import MessageTimelinePane from "./panes/MessageTimelinePane.vue";
import RunDetailPane from "./panes/RunDetailPane.vue";

const store = useWorkspaceStore();
const route = useRoute();

type PaneKey = "conversations" | "messages" | "run";
const tabs: { key: PaneKey; label: string }[] = [
  { key: "conversations", label: "会话" },
  { key: "messages", label: "消息" },
  { key: "run", label: "运行" },
];

const isMobile = ref(false);
const activePane = ref<PaneKey>("conversations");

// 选中会话经 query `?c=<id>` 承载（可深链/刷新恢复）。watcher immediate 同时覆盖
// 首次挂载与后续 query 变化；LayoutView 以 route.path 作 RouterView key，query 变化不 remount。
watch(
  () => route.query.c,
  (c) => {
    const id = typeof c === "string" && c.length > 0 ? c : null;
    if (id) {
      void store.selectConversation(id);
    } else {
      store.clearSelection();
    }
  },
  { immediate: true },
);

// 移动端：选中会话 -> 切到消息面板；显式点击「运行详情」-> 切到运行面板（桌面端无影响）。
// 默认派生的 run（会话载入时）不触发切换，避免选中会话后被顶到运行页。
watch(
  () => store.selectedId,
  (id) => {
    if (id && isMobile.value) activePane.value = "messages";
  },
);

function onExplicitRun(): void {
  if (isMobile.value) activePane.value = "run";
}

function handleResize(): void {
  isMobile.value = window.innerWidth < 768;
}

onMounted(() => {
  handleResize();
  window.addEventListener("resize", handleResize);
  void store.loadConversations(true);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
});
</script>

<style scoped>
.ws-shell {
  display: flex;
  flex-direction: column;
  /* 填充 page-shell 余下视口：扣除页 padding + breadcrumb（桌面无 topbar）。 */
  height: calc(100dvh - 96px);
  min-height: 480px;
}

.ws-mobile-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
  background: var(--color-bg-base);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: 3px;
}

.ws-mobile-tab {
  flex: 1;
  border: none;
  background: none;
  padding: 6px 0;
  font-size: var(--text-caption);
  color: var(--color-ink-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.ws-mobile-tab.active {
  background: var(--color-bg-elevated);
  color: var(--color-ink);
  font-weight: 500;
  box-shadow: var(--surface-card-shadow);
}

.ws-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr) 340px;
  gap: 12px;
}

/* 中间断点：收窄侧栏避免三栏挤压；center minmax(0,1fr) 保证不横向溢出。 */
@media (max-width: 1279px) {
  .ws-grid {
    grid-template-columns: 240px minmax(0, 1fr) 280px;
    gap: 10px;
  }
}

.ws-col {
  min-width: 0;
  min-height: 0;
}

@media (max-width: 767px) {
  .ws-shell {
    /* 移动端额外扣除固定 topbar(48px) + 面板切换条。 */
    height: calc(100dvh - 168px);
  }
  .ws-grid {
    display: block;
    height: 100%;
  }
  .ws-col {
    height: 100%;
  }
}
</style>
