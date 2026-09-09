<template>
  <div class="ws-composer" data-testid="ws-composer">
    <textarea
      v-model="text"
      class="ws-composer-input"
      :placeholder="
        disabled ? '会话已归档，草稿只读' : '输入草稿…（发送将在后续版本开放）'
      "
      :disabled="disabled"
      rows="3"
      aria-label="消息草稿"
      data-testid="ws-composer-input"
      @input="onInput"
    />
    <div class="ws-composer-bar">
      <span class="ws-composer-hint">{{ hintText }}</span>
      <!-- 明确非提交状态：按钮禁用且不绑定任何发送路径，不产生虚假成功反馈。 -->
      <button
        class="ui-btn ui-btn-primary"
        :disabled="true"
        aria-disabled="true"
        title="发送功能将在后续版本开放"
        data-testid="ws-send-btn"
      >
        <SendHorizontal :size="14" aria-hidden="true" /> 发送
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { SendHorizontal } from "lucide-vue-next";
import { useWorkspaceDraftStore } from "@/stores/workspaceDraft";

const props = withDefaults(
  defineProps<{
    conversationId: string;
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const draftStore = useWorkspaceDraftStore();
const text = ref("");

// 切换会话时装载该会话草稿（tenant/owner/conversation 隔离，刷新后可恢复）。
watch(
  () => props.conversationId,
  (id) => {
    text.value = draftStore.getDraft(id);
  },
  { immediate: true },
);

function onInput(): void {
  draftStore.setDraft(props.conversationId, text.value);
}

const hintText = computed(() =>
  props.disabled
    ? "会话已归档，草稿仅保留在本地"
    : "草稿保存在本地浏览器，发送将在后续版本开放",
);
</script>

<style scoped>
.ws-composer {
  border-top: 1px solid var(--color-border-subtle);
  padding: 10px 12px;
  background: var(--color-bg-elevated);
}

.ws-composer-input {
  width: 100%;
  resize: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-base);
  color: var(--color-ink);
  font-size: var(--text-body);
  font-family: var(--font-body);
  padding: 8px 10px;
  outline: none;
  max-height: 120px;
}

.ws-composer-input:focus {
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px var(--color-accent-ring);
}

.ws-composer-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ws-composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
}

.ws-composer-hint {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
}
</style>
