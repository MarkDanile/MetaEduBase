<template>
  <div class="ui-panel p-4 mb-4 flex flex-wrap items-center gap-4">
    <div class="flex items-center gap-2">
      <FileText :size="18" class="text-[var(--color-accent)]" />
      <span class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">{{ file.filename }}</span>
    </div>
    <span class="ui-tag-blue text-[var(--text-micro)]">{{ file.doc_type || file.file_type }}</span>
    <span :class="statusTagClass(file.status)">{{ statusLabel(file.status) }}</span>
    <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatSize(file.file_size) }}</span>
    <div v-if="file.tags?.length" class="flex gap-1">
      <span v-for="tag in file.tags" :key="tag" class="ui-tag-purple text-[var(--text-micro)]">{{ tag }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { FileText } from "lucide-vue-next";
import { FILE_STATUS_MAP } from "@/constants/pipeline";
import type { FileDTO } from "@/services/document";

defineProps<{
  file: FileDTO;
}>();

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
</script>
