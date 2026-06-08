<template>
  <div class="ui-panel p-4 mb-4 flex flex-wrap items-center gap-4">
    <div class="flex items-center gap-2">
      <FileSpreadsheet :size="18" class="text-[var(--color-accent)]" />
      <span class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">{{ selected.name }}</span>
    </div>
    <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
      {{ selected.row_count }} 行 × {{ selected.column_names?.length ?? 0 }} 列
    </span>
    <div v-if="selected.tags?.length" class="flex gap-1">
      <span v-for="tag in selected.tags" :key="tag" class="ui-tag-purple text-[var(--text-micro)]">{{ tag }}</span>
    </div>
    <button
      class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5 text-red-500 ml-auto"
      @click="emit('delete')"
    >
      <Trash2 :size="14" /> 删除
    </button>
    <button
      class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5"
      @click="emit('reinitialize')"
    >
      <RefreshCw :size="14" /> 重新初始化
    </button>
  </div>
</template>

<script setup lang="ts">
import { FileSpreadsheet, Trash2, RefreshCw } from "lucide-vue-next";
import type { DatasetDTO } from "@/services/structured-data";

defineProps<{
  selected: DatasetDTO;
}>();

const emit = defineEmits<{
  "delete": [];
  "reinitialize": [];
}>();
</script>
