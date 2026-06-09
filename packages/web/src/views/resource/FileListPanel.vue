<template>
  <div class="flex-1 ui-panel p-4 flex flex-col gap-3">
    <!-- Upload area -->
    <div
      class="border-2 border-dashed border-[var(--color-border)] rounded-xl p-4 text-center transition-colors cursor-pointer"
      :class="isDragging ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)]' : 'hover:border-[var(--color-ink-tertiary)]'"
      @dragover.prevent="emit('set-dragging', true)"
      @dragleave="emit('set-dragging', false)"
      @drop.prevent="onDrop"
      @click="onTriggerUpload"
    >
      <Upload :size="20" class="mx-auto mb-1 text-[var(--color-ink-tertiary)]" />
      <p class="text-[var(--text-caption)] text-[var(--color-ink-secondary)]">
        拖拽文件到此处上传，或点击选择文件
      </p>
    </div>
    <input
      ref="fileInput"
      type="file"
      class="hidden"
      multiple
      @change="onFileChange"
    />

    <!-- Filter bar -->
    <div class="flex items-center gap-2 flex-wrap">
      <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">筛选:</span>
      <select
        :value="filterStatus"
        class="ui-input text-[var(--text-small)] py-1 px-2 rounded"
        @change="emit('update:filter-status', ($event.target as HTMLSelectElement).value)"
      >
        <option value="">全部状态</option>
        <option value="uploaded">已上传</option>
        <option value="processing">处理中</option>
        <option value="processed">已完成</option>
        <option value="failed">失败</option>
      </select>
      <button
        class="ui-btn-ghost text-[var(--text-small)] px-2 py-1"
        @click="emit('refresh')"
      >
        <RefreshCw :size="14" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <!-- File table -->
    <LoadingSpinner v-if="loading" text="加载文件..." />
    <EmptyState v-else-if="files.length === 0" title="暂无文件" hint="上传文档开始处理" />
    <div v-else class="overflow-auto flex-1">
      <table class="w-full text-[var(--text-caption)]">
        <thead>
          <tr class="border-b border-[var(--color-border)] text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
            <th class="text-left py-2 px-2 font-medium w-10">序号</th>
            <th class="text-left py-2 px-2 font-medium">文件名</th>
            <th class="text-left py-2 px-2 font-medium">类型</th>
            <th class="text-left py-2 px-2 font-medium">状态</th>
            <th class="text-left py-2 px-2 font-medium">上传人</th>
            <th class="text-left py-2 px-2 font-medium">大小</th>
            <th class="text-left py-2 px-2 font-medium">上传时间</th>
            <th class="text-right py-2 px-2 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(file, idx) in files"
            :key="file.id"
            class="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-hover)] cursor-pointer transition-colors"
            @click="emit('go-to-detail', file.id)"
          >
            <td class="py-2.5 px-2 text-[var(--color-ink-tertiary)]">{{ idx + 1 }}</td>
            <td class="py-2.5 px-2">
              <div class="flex items-center gap-2">
                <FileText :size="14" class="text-[var(--color-ink-tertiary)] flex-shrink-0" />
                <span class="truncate max-w-[200px]">{{ file.filename }}</span>
              </div>
            </td>
            <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ file.doc_type || file.file_type }}</td>
            <td class="py-2.5 px-2">
              <span :class="statusTagClass(file.status)">{{ statusLabel(file.status) }}</span>
            </td>
            <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ file.uploaded_by_name || file.uploaded_by || '-' }}</td>
            <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ formatSize(file.file_size) }}</td>
            <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ formatDate(file.created_at) }}</td>
            <td class="py-2.5 px-2 text-right" @click.stop>
              <button class="ui-btn-ghost px-2 py-1" @click="emit('go-to-detail', file.id)">
                <Eye :size="14" />
              </button>
              <button class="ui-btn-ghost px-2 py-1 text-red-500" @click="emit('confirm-delete', file)">
                <Trash2 :size="14" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Upload, FileText, Eye, Trash2, RefreshCw } from "lucide-vue-next";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { FILE_STATUS_MAP } from "@/constants/pipeline";
import type { FileDTO } from "@/services/document";

defineProps<{
  files: FileDTO[];
  loading: boolean;
  isDragging: boolean;
  filterStatus: string;
}>();

const emit = defineEmits<{
  "set-dragging": [val: boolean];
  "trigger-upload": [];
  "file-change": [e: Event];
  "drop": [e: DragEvent];
  "update:filter-status": [val: string];
  "refresh": [];
  "go-to-detail": [id: string];
  "confirm-delete": [file: FileDTO];
}>();

const fileInput = ref<HTMLInputElement | null>(null);

function onTriggerUpload() {
  fileInput.value?.click();
}

function onFileChange(e: Event) {
  emit("file-change", e);
}

function onDrop(e: DragEvent) {
  emit("drop", e);
}

// --- Helpers (private to this component) ---
function statusLabel(status: string) {
  return FILE_STATUS_MAP[status]?.label ?? status;
}

function statusTagClass(status: string) {
  const color = FILE_STATUS_MAP[status]?.color ?? "blue";
  return `ui-tag-${color} text-[var(--text-micro)]`;
}

function formatSize(bytes: number | null) {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
</script>
