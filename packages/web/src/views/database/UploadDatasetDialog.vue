<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[var(--z-dialog)] flex items-center justify-center"
    role="dialog"
    aria-modal="true"
    @keydown.escape="emit('update:open', false)"
  >
    <div class="absolute inset-0 bg-black/50" @click="emit('update:open', false)" />
    <div class="relative ui-panel p-6 w-[480px]">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-[var(--text-page-title)] font-medium text-[var(--color-ink)]">上传数据集</h2>
        <button class="ui-btn-ghost p-1" @click="emit('update:open', false)">
          <X :size="18" />
        </button>
      </div>

      <div class="flex flex-col gap-4">
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">数据集名称</label>
          <input
            :value="form.name"
            class="ui-input w-full"
            placeholder="输入数据集名称"
            @input="emit('update:form', { ...form, name: ($event.target as HTMLInputElement).value })"
          />
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">描述（可选）</label>
          <textarea
            :value="form.description"
            class="ui-input w-full resize-none"
            rows="2"
            placeholder="输入描述"
            @input="emit('update:form', { ...form, description: ($event.target as HTMLTextAreaElement).value })"
          />
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">标签（可选，多个用逗号分隔）</label>
          <input
            :value="form.tags"
            class="ui-input w-full"
            placeholder="如：汽车维修，数据分析"
            @input="emit('update:form', { ...form, tags: ($event.target as HTMLInputElement).value })"
          />
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">选择文件</label>
          <div
            class="border-2 border-dashed border-[var(--color-border)] rounded-lg p-6 text-center cursor-pointer hover:border-[var(--color-accent)] transition-colors"
            :class="{ 'border-[var(--color-accent)]': form.file }"
            @click="triggerFileInput"
          >
            <FileSpreadsheet :size="24" class="mx-auto mb-2 text-[var(--color-ink-tertiary)]" />
            <p class="text-[var(--text-caption)] text-[var(--color-ink-secondary)]">
              {{ form.file ? form.file.name : "点击选择 Excel 文件" }}
            </p>
            <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-1">支持 .xlsx, .xls, .csv</p>
          </div>
          <input
            ref="fileInputRef"
            type="file"
            accept=".xlsx,.xls,.csv"
            class="hidden"
            @change="emit('file-change', $event)"
          />
        </div>
        <div class="flex justify-end gap-2 mt-2">
          <button class="ui-btn-ghost px-4 py-2" @click="emit('update:open', false)">取消</button>
          <button
            class="ui-btn-primary px-4 py-2 flex items-center gap-1.5"
            :disabled="!canUpload || uploading"
            @click="emit('upload')"
          >
            <LoadingSpinner v-if="uploading" :size="14" />
            <Upload v-else :size="14" />
            {{ uploading ? "上传中..." : "上传" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { Upload, FileSpreadsheet, X } from "lucide-vue-next";
import LoadingSpinner from "@/components/LoadingSpinner.vue";

export interface UploadForm {
  name: string;
  description: string;
  tags: string;
  file: File | null;
}

const props = defineProps<{
  open: boolean;
  form: UploadForm;
  uploading: boolean;
}>();

const emit = defineEmits<{
  "update:open": [val: boolean];
  "update:form": [form: UploadForm];
  "upload": [];
  "file-change": [e: Event];
}>();

const canUpload = computed(() => props.form.name.trim() && props.form.file);

const fileInputRef = ref<HTMLInputElement | null>(null);
function triggerFileInput() {
  fileInputRef.value?.click();
}
</script>
