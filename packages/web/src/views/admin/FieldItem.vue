<template>
  <div class="field-cards">
    <!-- Field list (flat with depth indentation) -->
    <template v-for="node in flatNodes" :key="node.id">
      <FieldCard
        :node="node"
        :parent-nodes="modelValue"
        @toggle="toggleExpand"
        @update="onUpdate"
        @remove="emit('remove', $event)"
        @update-field="onUpdateField"
        @change-type="onChangeType"
        @add-child="emit('addChild', $event)"
        @add-column="emit('addColumn', $event)"
        @remove-column="emit('removeColumn', $event, 0)"
      />
    </template>

    <!-- Add root -->
    <div v-if="modelValue.length > 0" class="add-root-wrap">
      <button class="add-root-btn" @click="emit('addRoot')">
        <Plus :size="13" /> 添加字段
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Plus } from 'lucide-vue-next'
import type { Field } from '@/services/template'
import FieldCard from './FieldCard.vue'

const props = defineProps<{
  modelValue: Field[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Field[]]
  'addRoot': []
  'addChild': [parentId: string]
  'addColumn': [parentId: string]
  'remove': [id: string]
  'removeColumn': [parentId: string, colIndex: number]
  'update': []
}>()

// ─── Expand state ─────────────────────────────────────────────────────────────
const expandedIds = ref(new Set<string>())

function toggleExpand(id: string) {
  if (expandedIds.value.has(id)) expandedIds.value.delete(id)
  else expandedIds.value.add(id)
}

// ─── Flatten tree ─────────────────────────────────────────────────────────────
const flatNodes = computed(() => {
  const result: (Field & { id: string; depth: number })[] = []
  function walk(nodes: Field[], depth: number) {
    nodes.forEach(node => {
      const id = node.id ?? crypto.randomUUID()
      result.push({ ...node, id, depth })
      if (node.children?.length) walk(node.children, depth + 1)
      if (node.items?.length) walk(node.items, depth + 1)
    })
  }
  walk(props.modelValue, 0)
  return result
})

// ─── Field update ─────────────────────────────────────────────────────────────
function onUpdateField(id: string, field: 'key' | 'label' | 'description', value: string) {
  const node = findNode(props.modelValue, id)
  if (!node) return
  if (field === 'key') node.key = value
  else if (field === 'label') node.label = value
  else if (field === 'description') node.description = value || undefined
  emitUpdate()
}

function onChangeType(id: string, newType: Field['type']) {
  const node = findNode(props.modelValue, id)
  if (!node) return
  node.type = newType
  if (newType === 'object' && !node.children) node.children = []
  if (newType === 'table' && !node.columns) node.columns = []
  if (newType === 'array' && !node.items) node.items = []
  if (['object', 'table', 'array'].includes(newType)) expandedIds.value.add(id)
  emitUpdate()
}

function onUpdate() {
  emitUpdate()
}

function emitUpdate() {
  emit('update:modelValue', [...props.modelValue])
  emit('update')
}

function findNode(nodes: Field[], id: string): Field | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const list = node.type === 'object' ? node.children : node.type === 'array' ? node.items : null
    if (list?.length) {
      const found = findNode(list, id)
      if (found) return found
    }
  }
  return null
}
</script>

<style scoped>
.field-cards { width: 100%; }

.add-root-wrap { padding: 6px 0; }

.add-root-btn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--color-accent); background: none;
  border: 1px dashed var(--color-accent); cursor: pointer;
  padding: 8px 16px; border-radius: 8px; width: 100%; justify-content: center;
}
.add-root-btn:hover { background: var(--color-accent-bg); }
</style>
