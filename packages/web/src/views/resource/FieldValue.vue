<template>
  <div class="field-item" :class="'depth-' + depth">
    <!-- Primitive -->
    <div v-if="isPrimitive" class="field-primitive">
      <span class="field-label">{{ label }}</span>
      <span class="field-value">{{ displayValue }}</span>
    </div>

    <!-- Object -->
    <div v-else-if="isObject" class="field-object">
      <div class="field-group-header" @click="expanded = !expanded">
        <span class="field-label">{{ label }}</span>
        <span class="field-toggle">
          <component :is="expanded ? ChevronDown : ChevronRight" :size="12" />
          <span class="text-xs" style="color: var(--color-ink-tertiary)">{{ expanded ? '收起' : '展开' }}</span>
        </span>
      </div>
      <div v-if="expanded" class="field-children">
        <FieldValue
          v-for="(childVal, childKey) in objectValue"
          :key="String(childKey)"
          :label="templates && fieldKey
            ? getTemplateFieldLabel(templates, String(childKey), fieldKey)
            : String(childKey)"
          :field-key="fieldKey ? `${fieldKey}.${String(childKey)}` : String(childKey)"
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
              <FieldValue
                :label="String(idx + 1)"
                :field-key="fieldKey"
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
import { getTemplateFieldLabel } from '@/utils/templateLabels';
import type { Template } from '@/services/template';

const props = defineProps<{
  label: string;
  value: unknown;
  depth?: number;
  // BUG-006 #1: nested 字段 label 解析需要 父字段 key (构建 dot-path)
  // + 当前 templates 列表 (查 children.label)
  fieldKey?: string;
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
