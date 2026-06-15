<template>
  <div class="field-item" :class="'depth-' + depth">
    <!-- Primitive -->
    <div v-if="isPrimitive" class="field-primitive">
      <span v-if="label" class="field-label">{{ label }}</span>
      <span class="field-value">{{ displayValue }}</span>
    </div>

    <!-- Object -->
    <div v-else-if="isObject" class="field-object">
      <div class="field-group-header" @click="expanded = !expanded">
        <span v-if="label" class="field-label">{{ label }}</span>
        <span class="field-toggle">
          <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
          <span class="text-xs" style="color: var(--color-ink-tertiary)">{{ expanded ? '收起' : '展开' }}</span>
        </span>
      </div>
      <div v-if="expanded" class="field-children">
        <FieldValue
          v-for="(childVal, childKey) in objectValue"
          :key="String(childKey)"
          :label="templates
            ? getTemplateFieldLabelByPath(templates, [...(keyPath ?? []), String(childKey)])
            : String(childKey)"
          :key-path="[...(keyPath ?? []), String(childKey)]"
          :templates="templates"
          :value="childVal"
          :depth="depth + 1"
        />
      </div>
    </div>

    <!-- Array -->
    <div v-else-if="isArray" class="field-array">
      <div class="field-group-header" @click="expanded = !expanded">
        <span class="field-label">{{ label }}</span>
        <span class="array-count">{{ arrayValue.length }}项</span>
        <span class="field-toggle">
          <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
          <span class="text-xs" style="color: var(--color-ink-tertiary)">{{ expanded ? '收起' : '展开' }}</span>
        </span>
      </div>
      <div v-if="expanded" class="field-children">
        <div
          v-for="(item, idx) in arrayValue"
          :key="idx"
          class="array-item"
        >
          <span class="array-index">{{ idx + 1 }}</span>
          <div class="array-content">
            <template v-if="isObjectOrArray(item)">
              <!-- BUG-006 #1 round 2: 递归 FieldValue 不再重复显示 idx+1
                (外层 array-index 已经显示), 而是用 array 字段 schema 里
                items[0] 的 label (e.g. "课程"). 视觉上从 "1. 1. 课程: value"
                变成 "1 课程: value".
                keyPath 保持父 array 的 keyPath, 这样 child FieldValue 构造
                [...keyPath, childKey] 路径才能找到 items[0] 的子字段. -->
              <FieldValue
                :label="arrayItemSchema?.label ?? ''"
                :key-path="keyPath ?? []"
                :templates="templates"
                :value="item"
                :depth="depth + 2"
              />
            </template>
            <span v-else class="field-value">{{ formatPrimitive(item) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { ChevronDown, ChevronRight } from 'lucide-vue-next';
import { getTemplateFieldLabelByPath, findFieldNode, type KeyedNode } from '@/utils/templateLabels';
import type { Template } from '@/services/template';

const props = defineProps<{
  label: string;
  value: unknown;
  depth?: number;
  // BUG-006 #1 round 2: nested 字段 label 解析需要完整 keyPath 数组
  // (覆盖 object children / array item / table column)
  keyPath?: string[];
  templates?: ReadonlyArray<Template>;
}>();

const depth = computed(() => props.depth ?? 0);
const expanded = ref(true);

const isPrimitive = computed(() =>
  props.value === null || props.value === undefined ||
  typeof props.value === 'string' ||
  typeof props.value === 'number'
);

const isObject = computed(() =>
  typeof props.value === 'object' &&
  !Array.isArray(props.value) &&
  props.value !== null
);

const isArray = computed(() => Array.isArray(props.value));

const isObjectOrArray = (v: unknown): boolean =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const objectValue = computed(() =>
  isObject.value ? (props.value as Record<string, unknown>) : {}
);

const arrayValue = computed(() =>
  isArray.value ? (props.value as unknown[]) : []
);

const displayValue = computed(() => {
  if (props.value === null || props.value === undefined) return '-';
  if (typeof props.value === 'string') return props.value || '-';
  if (typeof props.value === 'number') return String(props.value);
  return JSON.stringify(props.value);
});

function formatPrimitive(v: unknown): string {
  if (v === null || v === undefined) return '-';
  if (typeof v === 'string') return v || '-';
  if (typeof v === 'number') return String(v);
  return JSON.stringify(v);
}

/**
 * BUG-006 #1 round 2: 解析 array 字段 items[0] 的 schema (key + label),
 * 用来给数组项的递归 FieldValue 提供正确的 label 和 keyPath.
 *
 * 没有 schema 上下文 (templates 未传 / keyPath 为空 / 字段不是 array)
 * 时返回 null, 数组项递归 FieldValue 会回退到空 label + 空 keyPath
 * (外层 array-index span 已经显示了索引, 不需要再重复).
 */
const arrayItemSchema = computed<{ key: string; label: string } | null>(() => {
  if (!props.templates || !props.keyPath || props.keyPath.length === 0) return null;
  const topKey = props.keyPath[props.keyPath.length - 1];
  if (!topKey) return null;
  for (const t of props.templates) {
    const found = findFieldNode(t.fields as ReadonlyArray<KeyedNode>, topKey);
    if (found && Array.isArray(found.items) && found.items.length > 0) {
      const item0 = found.items[0];
      if (item0) return { key: item0.key, label: item0.label };
    }
  }
  return null;
});
</script>

<style scoped>
.field-item {
  padding-left: calc(var(--depth, 0) * 16px);
}

.field-primitive {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.field-object,
.field-array {
  margin: 2px 0;
}

.field-group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 2px 0;
  border-radius: 4px;
}

.field-label {
  font-size: var(--text-small, 12px);
  color: var(--color-ink-tertiary, #6b7280);
  min-width: 80px;
  max-width: 140px;
}

.field-value {
  font-size: var(--text-caption, 13px);
  color: var(--color-ink, #1f2937);
  word-break: break-all;
}

.field-toggle {
  display: flex;
  align-items: center;
  gap: 2px;
  color: var(--color-ink-tertiary, #6b7280);
}

.field-children {
  padding-left: 12px;
  margin-top: 2px;
  border-left: 1px solid var(--color-border, #e5e7eb);
}

.array-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 2px 0;
}

.array-index {
  font-size: var(--text-small, 12px);
  color: var(--color-ink-tertiary, #6b7280);
  min-width: 20px;
}

.array-count {
  font-size: var(--text-small, 12px);
  color: var(--color-ink-tertiary, #6b7280);
}

.array-content {
  flex: 1;
}
</style>
