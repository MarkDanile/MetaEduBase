<template>
  <div class="overflow-x-auto">
    <table class="w-full text-[var(--text-caption)]">
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key"
            class="px-3 py-2 text-left text-[var(--color-ink-tertiary)] font-medium bg-[var(--panel-bg)] border-b border-[var(--panel-border)]">
            {{ col.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="i">
          <td v-for="col in columns" :key="col.key"
            class="px-3 py-2 text-[var(--color-ink)] border-b border-[var(--panel-border)]">
            {{ row[col.key] ?? '-' }}
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td :colspan="columns.length" class="px-3 py-4 text-center text-[var(--color-ink-tertiary)]">
            暂无数据
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import type { TableColumn } from '@/services/template'

defineProps<{
  columns: TableColumn[]
  rows: Record<string, unknown>[]
}>()
</script>