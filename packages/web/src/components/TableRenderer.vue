<template>
  <div class="overflow-x-auto">
    <table class="ui-table">
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key"
            class="ui-table-header-cell">
            {{ col.label }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="i" class="ui-table-row">
          <td v-for="col in columns" :key="col.key"
            class="ui-table-cell"
            :title="cellTitle(row[col.key])">
            {{ row[col.key] ?? '-' }}
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td :colspan="columns.length" class="ui-table-empty-cell">
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

/**
 * 长内容：单元格内省略显示，完整值通过 title 暴露（可悬停 / 读屏获取），
 * 避免长文本撑破表格容器。
 */
function cellTitle(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  const text = String(value);
  return text.length > 0 ? text : undefined;
}
</script>