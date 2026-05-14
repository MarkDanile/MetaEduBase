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
        <h3 :id="titleId" class="text-[var(--text-subtitle)] font-semibold mb-2">{{ title }}</h3>
        <p :id="descId" class="text-[var(--text-body)] text-[var(--color-ink-secondary)] mb-[var(--spacing-section)]">{{ message }}</p>
        <div class="flex gap-2 justify-end">
          <button
            ref="cancelBtn"
            class="liquid-btn liquid-btn-ghost"
            :disabled="submitting"
            @click="cancel"
          >
            {{ cancelText }}
          </button>
          <button
            class="liquid-btn"
            :class="danger ? 'liquid-btn-danger' : 'liquid-btn-primary'"
            :disabled="submitting"
            @click="confirm"
          >
            {{ submitting ? "处理中..." : confirmText }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, useId } from "vue";

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
const submitting = ref(false);
let previousFocus: HTMLElement | null = null;

watch(() => props.open, async (val) => {
  if (val) {
    previousFocus = document.activeElement as HTMLElement;
    document.body.style.overflow = "hidden";
    submitting.value = false;
    await nextTick();
    cancelBtn.value?.focus();
  } else {
    document.body.style.overflow = "";
    if (previousFocus) {
      previousFocus.focus();
      previousFocus = null;
    }
  }
});

function confirm() {
  if (submitting.value) return;
  submitting.value = true;
  emit("confirm");
  emit("update:open", false);
}

function cancel() {
  emit("cancel");
  emit("update:open", false);
}
</script>
