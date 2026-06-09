<template>
  <ConfirmDialog
    :open="open"
    title="上传文件"
    :show-cancel="true"
    confirm-text="上传"
    @update:open="emit('update:open', $event)"
    @confirm="emit('confirm')"
  >
    <div class="space-y-3 mt-2">
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">文档类型</label>
        <select
          :value="docType"
          class="ui-input w-full mt-1"
          @change="emit('update:doc-type', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">不选择</option>
          <option v-for="opt in DOC_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">标签（逗号分隔）</label>
        <input
          :value="tags"
          class="ui-input w-full mt-1"
          placeholder="如: 教案, 期末考试"
          @input="emit('update:tags', ($event.target as HTMLInputElement).value)"
        />
      </div>
    </div>
  </ConfirmDialog>
</template>

<script setup lang="ts">
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { DOC_TYPE_OPTIONS } from "@/constants/pipeline";

defineProps<{
  open: boolean;
  docType: string;
  tags: string;
}>();

const emit = defineEmits<{
  "update:open": [val: boolean];
  "update:doc-type": [val: string];
  "update:tags": [val: string];
  "confirm": [];
}>();
</script>
