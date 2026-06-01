<template>
  <!-- Render a single field value recursively -->
  <div class="extracted-data-renderer">
    <!-- Primitive: text / number / textarea -->
    <template v-if="fieldType === 'text' || fieldType === 'textarea' || fieldType === 'number'">
      <div class="field-row" :class="`depth-${depth}`">
        <span class="field-label">{{ fieldLabel }}</span>
        <span class="field-value">{{ displayValue }}</span>
      </div>
    </template>

    <!-- Object: recursively render children -->
    <template v-else-if="fieldType === 'object'">
      <div class="field-row field-row--object" :class="`depth-${depth}`">
        <div class="field-group-header">
          <span class="field-label">{{ fieldLabel }}</span>
          <button class="toggle-btn" @click="expanded = !expanded">
            <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
            <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
              {{ expanded ? '收起' : '展开' }}
            </span>
          </button>
        </div>
        <div v-if="expanded && fieldChildren?.length" class="field-children">
          <ExtractedDataRenderer
            v-for="child in fieldChildren"
            :key="child.key"
            :field="child"
            :data="objectValue"
            :depth="depth + 1"
          />
        </div>
        <div v-else-if="expanded && !fieldChildren?.length" class="field-no-children">
          <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">无子字段</span>
        </div>
      </div>
    </template>

    <!-- Array: render each item recursively -->
    <template v-else-if="fieldType === 'array'">
      <div class="field-row field-row--array" :class="`depth-${depth}`">
        <div class="field-group-header">
          <span class="field-label">{{ fieldLabel }}</span>
          <span class="array-count">{{ arrayValue?.length ?? 0 }}项</span>
          <button class="toggle-btn" @click="expanded = !expanded">
            <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
            <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
              {{ expanded ? '收起' : '展开' }}
            </span>
          </button>
        </div>
        <div v-if="expanded" class="field-children">
          <template v-if="arrayValue && arrayValue.length">
            <div
              v-for="(item, idx) in arrayValue"
              :key="idx"
              class="array-item"
              :class="`depth-${depth + 1}`"
            >
              <div class="array-item-index">{{ idx + 1 }}</div>
              <div class="array-item-content">
                <!-- Array item is an object with children fields -->
                <template v-if="fieldItems?.length && isObject(item)">
                  <ExtractedDataRenderer
                    v-for="child in fieldItems"
                    :key="child.key"
                    :field="child"
                    :data="(item as Record<string, unknown>)"
                    :depth="depth + 2"
                  />
                </template>
                <!-- Array item is a primitive -->
                <template v-else>
                  <span class="field-value">{{ formatPrimitive(item) }}</span>
                </template>
              </div>
            </div>
          </template>
          <span v-else class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">暂无数据</span>
        </div>
      </div>
    </template>

    <!-- Table: columns + rows -->
    <template v-else-if="fieldType === 'table'">
      <div class="field-row field-row--table" :class="`depth-${depth}`">
        <div class="field-group-header mb-2">
          <span class="field-label">{{ fieldLabel }}</span>
          <button class="toggle-btn" @click="expanded = !expanded">
            <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
            <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
              {{ expanded ? '收起' : '展开' }}
            </span>
          </button>
        </div>
        <div v-if="expanded">
          <TableRenderer
            :columns="fieldColumns ?? []"
            :rows="tableRows"
          />
        </div>
      </div>
    </template>

    <!-- Fallback: unknown type — show raw value with label -->
    <template v-else>
      <div class="field-row" :class="`depth-${depth}`">
        <span class="field-label">{{ fieldLabel || key }}</span>
        <span class="field-value">{{ displayValue }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronDown, ChevronRight } from 'lucide-vue-next'
import TableRenderer from '@/components/TableRenderer.vue'
import type { Field, TableColumn } from '@/services/template'

const props = defineProps<{
  field: Field
  data: Record<string, unknown>
  depth?: number
}>()

const depth = computed(() => props.depth ?? 0)
const expanded = ref(true)

const key = computed(() => props.field.key)
const fieldLabel = computed(() => props.field.label || props.field.key)
const fieldType = computed(() => props.field.type ?? 'text')

// The value from data, keyed by field.key
const rawValue = computed(() => props.data?.[key.value])

// Children / columns / items from field definition
const fieldChildren = computed(() => props.field.children)
const fieldColumns = computed(() => props.field.columns)
const fieldItems = computed(() => props.field.items)

// Typed values
const objectValue = computed(() =>
  typeof rawValue.value === 'object' && rawValue.value !== null
    ? (rawValue.value as Record<string, unknown>)
    : {}
)

const arrayValue = computed(() =>
  Array.isArray(rawValue.value) ? rawValue.value : []
)

const tableRows = computed(() => {
  const val = rawValue.value
  if (typeof val === 'object' && val !== null && 'rows' in val) {
    return (val as Record<string, unknown>).rows as Record<string, unknown>[]
  }
  // Fallback: treat top-level object keys as row data if columns defined
  if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
    return [val as Record<string, unknown>]
  }
  return []
})

// Display value for primitives
const displayValue = computed(() => {
  const v = rawValue.value
  if (v === null || v === undefined) return '-'
  if (typeof v === 'string') return v || '-'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'boolean') return v ? '是' : '否'
  return JSON.stringify(v)
})

function formatPrimitive(v: unknown): string {
  if (v === null || v === undefined) return '-'
  if (typeof v === 'string') return v || '-'
  if (typeof v === 'number') return String(v)
  if (typeof v === 'boolean') return v ? '是' : '否'
  return JSON.stringify(v)
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}
</script>

<style scoped>
.extracted-data-renderer {
  width: 100%;
}

.field-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid transparent;
}

.field-row.depth-0 {
  padding-top: 8px;
}

.field-row--object,
.field-row--array,
.field-row--table {
  flex-direction: column;
  gap: 2px;
  padding: 6px 0;
}

.field-label {
  font-size: var(--text-small, 12px);
  color: var(--color-ink-tertiary, #6b7280);
  min-width: 80px;
  max-width: 140px;
  flex-shrink: 0;
  padding-top: 2px;
}

.field-value {
  font-size: var(--text-caption, 13px);
  color: var(--color-ink, #374151);
  word-break: break-word;
}

.field-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.toggle-btn {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  border-radius: 4px;
  color: var(--color-ink-tertiary, #6b7280);
  cursor: pointer;
  background: none;
  border: none;
}

.toggle-btn:hover {
  background-color: var(--color-bg-hover, #f3f4f6);
}

.array-count {
  font-size: var(--text-micro, 11px);
  color: var(--color-ink-tertiary, #6b7280);
  background: var(--color-bg, #f9fafb);
  padding: 1px 5px;
  border-radius: 10px;
}

.field-children {
  width: 100%;
  padding-left: 12px;
  border-left: 1px solid var(--color-border, #e5e7eb);
  margin-top: 2px;
}

.array-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px 0;
}

.array-item-index {
  font-size: var(--text-micro, 11px);
  color: var(--color-ink-tertiary, #6b7280);
  min-width: 20px;
  padding-top: 2px;
  flex-shrink: 0;
}

.array-item-content {
  flex: 1;
  min-width: 0;
}

.field-no-children {
  padding-left: 12px;
  padding-bottom: 4px;
}
</style>
