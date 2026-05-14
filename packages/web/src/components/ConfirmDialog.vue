<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="liquid-dialog-overlay"
      role="alertdialog"
      aria-modal="true"
      :aria-labelledby="titleId"
      :aria-describedby="descId"
      @click.self="cancel"
      @keydown.escape="cancel"
    >
      <div class="liquid-dialog" style="max-width:400px">
        <h3 :id="titleId" class="text-[16px] font-semibold mb-2">{{ title }}</h3>
        <p :id="descId" class="text-[14px] text-[var(--color-ink-secondary)] mb-6">{{ message }}</p>
        <div class="flex gap-2 justify-end">
          <button
            ref="cancelBtn"
            class="liquid-btn liquid-btn-ghost text-[13px]"
            @click="cancel"
          >
            {{ cancelText }}
          </button>
          <button
            class="liquid-btn text-[13px]"
            :class="danger ? 'liquid-btn-danger' : 'liquid-btn-primary'"
            @click="confirm"
          >
            {{ confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted, useId } from "vue";

const props = withDefaults(defineProps<{
  open: boolean;
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}>(), {
  title: "确认操作",
  message: "此操作不可撤销，确定继续吗？",
  confirmText: "确认",
  cancelText: "取消",
  danger: true,
});

const emit = defineEmits<{
  confirm: [];
  cancel: [];
  "update:open": [value: boolean];
}>();

const cancelBtn = ref<HTMLButtonElement | null>(null);
const titleId = useId();
const descId = useId();
let previousFocus: HTMLElement | null = null;

watch(() => props.open, async (val) => {
  if (val) {
    previousFocus = document.activeElement as HTMLElement;
    await nextTick();
    cancelBtn.value?.focus();
  } else if (previousFocus) {
    previousFocus.focus();
    previousFocus = null;
  }
});

function confirm() {
  emit("confirm");
  emit("update:open", false);
}

function cancel() {
  emit("cancel");
  emit("update:open", false);
}
</script>
