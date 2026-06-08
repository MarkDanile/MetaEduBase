<template>
  <div class="w-[260px] shrink-0 flex flex-col gap-2" style="max-height: calc(100vh - 80px)">
    <!-- Dataset list card -->
    <div class="ui-panel flex flex-col overflow-hidden" style="flex: 1; min-height: 0">
      <!-- Card header (always visible) -->
      <div class="flex items-center justify-between flex-shrink-0 px-3 pt-3">
        <div class="flex items-center gap-2" style="font-size: 16px">
          <button
            class="text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-secondary)] transition-colors p-0.5"
            @click="emit('toggle-collapse')"
          >
            <ChevronRight :size="14" class="transition-transform" :class="!collapsed ? 'rotate-90' : ''" />
          </button>
          <span class="text-[var(--color-ink-secondary)] font-medium">数据集</span>
          <span class="text-[var(--color-ink-secondary)]">{{ datasets.length }}</span>
        </div>

        <!-- Sort controls (only when expanded) -->
        <div v-if="!collapsed" class="flex items-center gap-0.5">
          <button
            v-for="opt in sortOptions"
            :key="opt.value"
            class="p-0.5 rounded transition-colors"
            :class="sortBy === opt.value
              ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
              : 'text-[var(--color-ink-secondary)] hover:bg-[var(--color-bg-hover)]'"
            :title="opt.label"
            @click="emit('toggle-sort', opt.value)"
          >
            <component :is="opt.icon" :size="12" />
          </button>
          <button
            class="p-0.5 rounded text-[var(--color-ink-secondary)] hover:bg-[var(--color-bg-hover)] transition-colors"
            :title="sortDir === 'asc' ? '升序' : '降序'"
            @click="emit('toggle-sort-dir')"
          >
            <ArrowUpNarrowWide v-if="sortDir === 'asc'" :size="12" />
            <ArrowDownWideNarrow v-else :size="12" />
          </button>
        </div>
      </div>

      <!-- Content (only when expanded) -->
      <div v-if="!collapsed" class="px-2 pb-2 flex flex-col gap-0.5 flex-1 min-h-0 overflow-hidden">
        <LoadingSpinner v-if="loading" text="加载中..." />

        <template v-else>
          <EmptyState v-if="datasets.length === 0" title="暂无数据集" hint="上传文件" compact />

          <div v-else class="flex flex-col gap-1 overflow-y-auto min-h-0 flex-1" style="max-height: calc(100vh - 240px)">
            <button
              v-for="ds in datasets"
              :key="ds.id"
              class="w-full text-left px-1.5 py-1.5 rounded transition-colors"
              style="font-size: 14px; line-height: 1.4"
              :class="!showKgOverview && selectedId === ds.id
                ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-ink-secondary)]'"
              :style="ds === datasets[0] ? 'margin-top: 4px' : ''"
              @click="emit('select', ds)"
            >
              <div class="flex items-center gap-1">
                <span class="truncate font-medium">{{ ds.name }}</span>
                <span class="text-[var(--color-ink-tertiary)] shrink-0" style="font-size: 12px">
                  {{ ds.row_count }}行 × {{ ds.column_names?.length ?? 0 }}列
                </span>
                <span :class="dsStatusTagClass(ds.status)" style="font-size: 11px" class="ml-auto shrink-0">{{ dsStatusLabel(ds.status) }}</span>
              </div>
            </button>
          </div>
        </template>
      </div>
    </div>

    <!-- KG overview button -->
    <button
      class="ui-panel px-3 py-2.5 flex items-center justify-between hover:bg-[var(--color-bg-hover)] transition-colors cursor-pointer flex-shrink-0"
      style="font-size: 16px"
      :class="{ 'bg-[var(--color-accent-bg)]': showKgOverview }"
      @click="emit('toggle-kg-overview')"
    >
      <div class="flex items-center gap-2">
        <GitBranch :size="15" class="text-[var(--color-accent)]" />
        <span class="text-[var(--color-ink-secondary)]" :class="{ 'text-[var(--color-accent)]': showKgOverview }">知识图谱总览</span>
      </div>
      <ChevronRight :size="15" class="text-[var(--color-ink-tertiary)] transition-transform" :class="{ 'rotate-90': showKgOverview }" />
    </button>
  </div>
</template>

<script setup lang="ts">
import { Clock, Type, Hash, ArrowUpNarrowWide, ArrowDownWideNarrow, GitBranch, ChevronRight } from "lucide-vue-next";
import type { Component } from "vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { FILE_STATUS_MAP } from "@/constants/pipeline";
import type { DatasetDTO } from "@/services/structured-data";

defineProps<{
  datasets: DatasetDTO[];
  loading: boolean;
  selectedId: string | null;
  showKgOverview: boolean;
  sortBy: string;
  sortDir: string;
  collapsed: boolean;
}>();

const emit = defineEmits<{
  "select": [ds: DatasetDTO];
  "toggle-sort": [by: string];
  "toggle-sort-dir": [];
  "toggle-collapse": [];
  "toggle-kg-overview": [];
}>();

const sortOptions: { value: string; label: string; icon: Component }[] = [
  { value: "created_at", label: "按时间", icon: Clock },
  { value: "name", label: "按名称", icon: Type },
  { value: "row_count", label: "按数据量", icon: Hash },
];

// --- Status helpers (private to this component) ---
function dsStatusLabel(status: string) {
  return FILE_STATUS_MAP[status]?.label ?? status;
}

function dsStatusTagClass(status: string) {
  const color = FILE_STATUS_MAP[status]?.color ?? "blue";
  return `ui-tag-${color} text-[var(--text-micro)]`;
}
</script>
