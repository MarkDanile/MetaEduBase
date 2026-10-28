<template>
  <div ref="composerRoot" class="ai-chat-composer">
    <UiComposer
      :model-value="modelValue"
      :mode="mode"
      :can-submit="canSubmit"
      :can-stop="canStop"
      :hint="hint"
      placeholder="输入你的问题..."
      input-label="AI 问答消息"
      @update:model-value="emit('update:modelValue', $event)"
      @submit="emit('submit')"
      @stop="emit('stop')"
    >
      <template #tools><slot name="tools" /></template>
    </UiComposer>
  </div>
</template>

<script setup lang="ts">
/**
 * REQ-064 S2 / DB-01、DB-02：AI Chat 对共享 UiComposer 的薄适配层。
 * 模式、权限与请求能力全部由父级决定；这里不请求 API、不管理 Conversation。
 */
import { onMounted, ref, watch } from "vue";
import UiComposer from "@/components/UiComposer.vue";

const props = withDefaults(
  defineProps<{
    modelValue: string;
    mode?: "ready" | "busy" | "readonly" | "unavailable";
    canSubmit?: boolean;
    canStop?: boolean;
    hint?: string;
  }>(),
  {
    mode: "ready",
    canSubmit: true,
    canStop: false,
    hint: "Enter 发送，Shift+Enter 换行",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
  stop: [];
}>();

const composerRoot = ref<HTMLElement | null>(null);

function inputElement(): HTMLTextAreaElement | null {
  return composerRoot.value?.querySelector("textarea") ?? null;
}

function autoResize(): void {
  const input = inputElement();
  if (!input) return;
  // DB-02 的 Vue 适配；共享 --size-composer-input-max(160px) 负责封顶。
  input.style.height = "auto";
  input.style.height = `${input.scrollHeight}px`;
}

onMounted(() => {
  // 保留 BUG-003 的既有测试定位点，且仍落在真实 textarea 上。
  inputElement()?.setAttribute("data-testid", "chat-input");
  autoResize();
});

watch(
  () => props.modelValue,
  () => autoResize(),
  { flush: "post" },
);
</script>

<style scoped>
.ai-chat-composer {
  width: 100%;
}

/* DB-01/02：文本区不可手动拖拽，超过共享 160px token 后内部滚动。 */
.ai-chat-composer :deep(.ui-composer-input) {
  resize: none;
  overflow-y: auto;
}

/* spec §2.1：手机主要操作至少 44px 触控区。 */
@media (max-width: 767px) {
  .ai-chat-composer :deep(.ui-composer-submit),
  .ai-chat-composer :deep(.ui-composer-stop) {
    min-height: var(--size-control-touch);
  }
}
</style>
