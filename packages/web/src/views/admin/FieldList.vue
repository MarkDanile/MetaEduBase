<template>
  <div class="field-list" :class="{ 'field-list--nested': depth > 0 }">
    <!-- MAX_DEPTH guard -->
    <div v-if="depth >= MAX_DEPTH" class="field-list-depth-guard">
      嵌套层级过深，请简化字段结构
    </div>

    <!-- Draggable field list -->
    <draggable
      v-else
      :list="fields"
      item-key="id"
      handle=".drag-handle"
      :animation="150"
      @end="onDragEnd"
    >
      <template #item="{ element: node }">
        <FieldCard
          :node="node"
          :expanded-ids="expandedIds"
          :matched-ids="matchedIds"
          :search-query="searchQuery"
          :key-error-message="getErrorForFieldId(node.id ?? '')"
          :class="{ 'dimmed': searchQuery && !matchedIds.has(node.id ?? '') }"
          @toggle="emit('toggle', $event)"
          @update="emit('update')"
          @remove="emit('remove', $event)"
          @update-field="(id: string, f: 'key' | 'label' | 'description', v: string) => emit('updateField', id, f, v)"
          @change-type="(id: string, t: Field['type']) => emit('changeType', id, t)"
          @add-child="emit('addChild', $event)"
          @add-column="emit('addColumn', $event)"
          @remove-column="(parentId: string, ci: number) => emit('removeColumn', parentId, ci)"
          @copy-subtree="emit('copySubtree', $event)"
        />
      </template>
    </draggable>
  </div>
</template>

<script setup lang="ts">
import draggable from 'vuedraggable'
import type { Field } from '@/services/template'
import FieldCard from './FieldCard.vue'

defineOptions({ name: 'FieldList' })

const MAX_DEPTH = 5

const props = defineProps<{
  fields: Field[]
  depth: number
  expandedIds: Set<string>
  matchedIds: Set<string>
  searchQuery?: string
  // REQ-002-4: error message map (id → message) from parent
  fieldErrors?: Record<string, string>
}>()

const emit = defineEmits<{
  'update': []
  'remove': [id: string]
  'updateField': [id: string, field: 'key' | 'label' | 'description', value: string]
  'changeType': [id: string, type: Field['type']]
  'addChild': [parentId: string]
  'addColumn': [parentId: string]
  'removeColumn': [parentId: string, colIndex: number]
  'copySubtree': [id: string]
  'toggle': [id: string]
}>()

function getErrorForFieldId(id: string): string {
  if (!id) return ''
  return props.fieldErrors?.[id] ?? ''
}

function onDragEnd() {
  // vuedraggable mutates the array via :list; emit update so parent syncs
  emit('update')
}
</script>

<style scoped>
.field-list {
  width: 100%;
}

.field-list--nested {
  margin-left: 20px;
  border-left: 2px solid var(--panel-border);
  padding-left: 4px;
}

.dimmed {
  opacity: 0.3;
}

.field-list-depth-guard {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  padding: 8px 12px;
  font-style: italic;
  background: rgba(245, 158, 11, 0.06);
  border-radius: 6px;
  margin-bottom: 6px;
}
</style>
