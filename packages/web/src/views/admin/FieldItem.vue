<template>
  <div class="field-cards">
    <!-- Root layer: vuedraggable wraps FieldCard list -->
    <draggable
      :list="modelValue"
      item-key="key"
      handle=".drag-handle"
      :animation="150"
      @end="onRootDragEnd"
    >
      <template #item="{ element: node, index: i }">
        <FieldCard
          :node="{ ...node, id: node.id ?? crypto.randomUUID(), depth: 0 }"
          :parent-nodes="modelValue"
          :class="{ 'dimmed': searchQuery && !isNodeMatched(node) }"
          @toggle="toggleExpand"
          @update="onUpdate"
          @remove="emit('remove', $event)"
          @update-field="onUpdateField"
          @change-type="onChangeType"
          @add-child="emit('addChild', $event)"
          @add-column="emit('addColumn', $event)"
          @remove-column="emit('removeColumn', $event, 0)"
          @copy-subtree="onCopySubtree(i)"
        />
      </template>
    </draggable>

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
// @ts-expect-error vuedraggable lacks strict Vue 3 type declarations
import draggable from 'vuedraggable'
import { Plus } from 'lucide-vue-next'
import type { Field } from '@/services/template'
import FieldCard from './FieldCard.vue'

const props = defineProps<{
  modelValue: Field[]
  searchQuery?: string
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

// ─── Flatten tree (used for search matching) ──────────────────────────────────
const flatNodes = computed(() => {
  const result: (Field & { id: string; depth: number; matched: boolean })[] = []
  const q = (props.searchQuery ?? '').toLowerCase().trim()

  function walk(nodes: Field[], depth: number, parentMatched: boolean) {
    nodes.forEach(node => {
      const id = node.id ?? crypto.randomUUID()
      const matched = !q || parentMatched ||
        (node.key ?? '').toLowerCase().includes(q) ||
        (node.label ?? '').toLowerCase().includes(q)
      result.push({ ...node, id, depth, matched })
      if (node.children?.length) walk(node.children, depth + 1, matched)
      if (node.items?.length) walk(node.items, depth + 1, matched)
    })
  }
  walk(props.modelValue, 0, false)
  return result
})

/** Check if a node (or any descendant) matches the search query. */
function isNodeMatched(node: Field): boolean {
  const found = flatNodes.value.find(n => n.id === (node.id ?? ''))
  return found?.matched ?? false
}

// ─── Drag end handlers ────────────────────────────────────────────────────────
function onRootDragEnd() {
  // vuedraggable mutates the array via :list; emit update so parent syncs
  emit('update:modelValue', [...props.modelValue])
  emit('update')
}

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

// ─── Subtree copy (deep clone + key suffix) ───────────────────────────────────
function deepCopyFieldWithSuffix(f: Field, parentSuffix: string): Field {
  const suffixKey = `${f.key ?? 'field'}_${parentSuffix}`
  const copy: Field = {
    key: suffixKey,
    label: f.label,
    type: f.type,
    description: f.description,
  }
  if (f.children) copy.children = f.children.map(c => deepCopyFieldWithSuffix(c, parentSuffix))
  if (f.columns) copy.columns = f.columns.map(c => ({ ...c, key: `${c.key}_${parentSuffix}` }))
  if (f.items) copy.items = f.items.map(c => deepCopyFieldWithSuffix(c, parentSuffix))
  return copy
}

function onCopySubtree(index: number) {
  const original = props.modelValue[index]
  if (!original) return
  const suffix = `copy_${Date.now()}_${index}`
  const copy = deepCopyFieldWithSuffix(original, suffix)
  copy.label = `${original.label} (副本)`
  // Use nextCopySuffix for top-level key to avoid sibling collision
  const siblingKeys = props.modelValue.map(f => f.key ?? '')
  let n = 1
  while (siblingKeys.includes(`${original.key ?? 'field'}_copy_${n}`)) n++
  copy.key = `${original.key ?? 'field'}_copy_${n}`
  props.modelValue.splice(index + 1, 0, copy)
  emit('update:modelValue', [...props.modelValue])
  emit('update')
}
</script>

<style scoped>
.field-cards { width: 100%; }

.dimmed { opacity: 0.3; }

.add-root-wrap { padding: 6px 0; }

.add-root-btn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 13px; color: var(--color-accent); background: none;
  border: 1px dashed var(--color-accent); cursor: pointer;
  padding: 8px 16px; border-radius: 8px; width: 100%; justify-content: center;
}
.add-root-btn:hover { background: var(--color-accent-bg); }
</style>
