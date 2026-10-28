<template>
  <div
    class="ui-composer"
    :class="{
      'ui-composer-busy': mode === 'busy',
      'ui-composer-readonly': mode === 'readonly',
      'ui-composer-unavailable': mode === 'unavailable',
      'ui-composer-empty': modelValue.length === 0,
    }"
    :aria-busy="mode === 'busy'"
  >
    <div v-if="$slots.attachments" class="ui-composer-attachments">
      <slot name="attachments" />
    </div>

    <label class="ui-composer-label" :for="inputId">{{ inputLabel }}</label>

    <textarea
      :id="inputId"
      ref="inputEl"
      class="ui-input ui-composer-input"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="mode === 'busy' || mode === 'unavailable'"
      :readonly="mode === 'readonly'"
      :aria-describedby="hint ? hintId : undefined"
      rows="1"
      @input="onInput"
      @keydown="onKeydown"
      @compositionstart="onCompositionStart"
      @compositionend="onCompositionEnd"
    />

    <p v-if="hint" :id="hintId" class="ui-composer-hint">{{ hint }}</p>

    <div class="ui-composer-toolbar">
      <div class="ui-composer-tools">
        <slot name="tools" />
      </div>
      <div class="ui-composer-actions">
        <button
          v-if="mode === 'busy' && canStop"
          type="button"
          class="ui-btn ui-btn-ghost ui-composer-stop"
          @click="emit('stop')"
        >
          停止
        </button>
        <button
          type="button"
          class="ui-btn ui-btn-primary ui-composer-submit"
          :disabled="!canSubmitNow"
          @click="submit"
        >
          发送
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * REQ-064 S1b-2：共享 `UiComposer`（design spec §3 / roadmap §4.2 的 G1）。
 *
 * 契约（design spec §3 原文约束）：
 * - 受控 `modelValue`；`mode: 'ready' | 'busy' | 'readonly' | 'unavailable'`；
 *   `canSubmit` / `canStop` / `placeholder` / `hint` / `inputLabel`；
 * - 事件**仅** `update:modelValue` / `submit` / `stop`，附件与工具以具名插槽提供；
 * - 提交必须同时满足 `mode === "ready" && canSubmit && modelValue.trim().length > 0`，
 *   且输入法非 composing；按钮与键盘入口共用这一条件；
 * - `ready + canSubmit=false` 仍可编辑草稿；`readonly` 保留可读取内容但禁止编辑/提交；
 *   `unavailable` 禁用输入并给出原因；`busy` 禁止编辑和再次提交，
 *   仅 `mode === "busy" && canStop` 时显示并允许停止；
 * - **组件不请求 API、不选择模型、不管理 Conversation，也不推断租户权限**——
 *   一切由父级通过 props / 插槽传入。
 */
import { computed, ref, useId } from "vue";

const props = withDefaults(
  defineProps<{
    /** 受控文本值 */
    modelValue?: string;
    /** 交互模式 */
    mode?: "ready" | "busy" | "readonly" | "unavailable";
    /** 父级是否允许提交 */
    canSubmit?: boolean;
    /** 父级是否允许停止（仅 busy 模式有意义） */
    canStop?: boolean;
    placeholder?: string;
    /** 辅助说明 / 不可用原因 */
    hint?: string;
    /** 输入框可访问名称 */
    inputLabel?: string;
  }>(),
  {
    modelValue: "",
    mode: "ready",
    canSubmit: false,
    canStop: false,
    placeholder: "",
    hint: undefined,
    inputLabel: "输入消息",
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
  submit: [];
  stop: [];
}>();

const inputId = useId();
const hintId = useId();
const inputEl = ref<HTMLTextAreaElement | null>(null);
/** 输入法组合中（拼音候选窗未确认）时不得触发提交。 */
const composing = ref(false);

/**
 * 提交门槛（design spec §3）：mode 必须是 ready、父级允许、非空白、
 * 且输入法不在组合中。按钮与键盘入口共用这一条件。
 */
const canSubmitNow = computed(
  () =>
    props.mode === "ready" &&
    props.canSubmit &&
    props.modelValue.trim().length > 0 &&
    !composing.value,
);

function onInput(event: Event): void {
  const target = event.target as HTMLTextAreaElement | null;
  if (!target) return;
  emit("update:modelValue", target.value);
}

function submit(): void {
  if (!canSubmitNow.value) return;
  emit("submit");
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== "Enter" || event.shiftKey) return;
  // 组合输入中的 Enter 属于候选确认，不得提交
  if (composing.value || event.isComposing) return;
  if (!canSubmitNow.value) return;
  event.preventDefault();
  emit("submit");
}

function onCompositionStart(): void {
  composing.value = true;
}

function onCompositionEnd(): void {
  composing.value = false;
}

defineExpose({
  /** 供父级聚焦输入框（不改变既有 props / events 契约）。 */
  focus: () => inputEl.value?.focus(),
});
</script>
