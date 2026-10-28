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
            <span class="ui-table-cell-text">{{ cellText(row[col.key]) }}</span>
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
 * 单元格文本的**唯一**格式化入口：显示与 title 共用，保证截断时 title 里的
 * 完整值与可见值一致。
 *
 * 对象 / 数组走 JSON 序列化（而不是 String(value)），避免出现
 * `[object Object]` 或逗号拼接这类与显示不符的结果。
 */
function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

/** 单元格可见文本。 */
function cellText(value: unknown): string {
  return formatCell(value);
}

/**
 * 长内容：单元格内省略显示，完整值通过 title 暴露（可悬停 / 读屏获取）。
 * 与 cellText 共用同一格式化函数。
 */
function cellTitle(value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined;
  const text = formatCell(value);
  return text.length > 0 ? text : undefined;
}
</script>