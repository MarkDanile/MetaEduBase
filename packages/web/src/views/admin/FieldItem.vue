<template>
  <div class="field-cards">
    <!-- Root layer: FieldList wraps the recursive draggable + FieldCard tree -->
    <FieldList
      v-if="modelValue.length > 0"
      :fields="modelValue"
      :depth="0"
      :expanded-ids="expandedIds"
      :matched-ids="matchedIds"
      :search-query="searchQuery"
      :field-errors="fieldErrorsById"
      @update="onUpdate"
      @remove="emit('remove', $event)"
      @update-field="onUpdateField"
      @change-type="onChangeType"
      @add-child="emit('addChild', $event)"
      @add-column="emit('addColumn', $event)"
      @remove-column="(parentId: string, ci: number) => emit('removeColumn', parentId, ci)"
      @copy-subtree="onCopySubtree"
      @toggle="toggleExpand"
    />

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
import FieldList from './FieldList.vue'

const props = defineProps<{
  modelValue: Field[]
  searchQuery?: string
  // REQ-002-4: error map (id → message) for per-field key input
  fieldErrorsById?: Record<string, string>
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

/** Collapse or expand all container fields. Called by parent via template ref. */
function collapseAll(collapsed: boolean) {
  if (collapsed) {
    expandedIds.value = new Set<string>()
  } else {
    // Populate with all container field IDs
    const ids = new Set<string>()
    function walkContainers(fields: Field[]) {
      for (const f of fields) {
        if (['object', 'table', 'array'].includes(f.type) && f.id) {
          ids.add(f.id)
        }
        if (f.children?.length) walkContainers(f.children)
        if (f.items?.length) walkContainers(f.items)
      }
    }
    walkContainers(props.modelValue)
    expandedIds.value = ids
  }
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

/** Set of matched field IDs for efficient lookup by FieldList/FieldCard. */
const matchedIds = computed(() => {
  const ids = new Set<string>()
  for (const n of flatNodes.value) {
    if (n.matched) ids.add(n.id)
  }
  return ids
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

/** Find a node and its parent array for copy/insert operations. */
function findNodeAndParent(
  fields: Field[], id: string
): { node: Field; parentArray: Field[]; index: number } | null {
  for (let i = 0; i < fields.length; i++) {
    if (fields[i].id === id) return { node: fields[i], parentArray: fields, index: i }
    const childList = fields[i].type === 'object' ? fields[i].children
                    : fields[i].type === 'array' ? fields[i].items : null
    if (childList?.length) {
      const found = findNodeAndParent(childList, id)
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

function onCopySubtree(id: string) {
  const result = findNodeAndParent(props.modelValue, id)
  if (!result) return
  const { node: original, parentArray, index } = result
  const siblingKeys = parentArray.map(f => f.key ?? '')
  let n = 1
  while (siblingKeys.includes(`${original.key ?? 'field'}_copy_${n}`)) n++
  const suffix = `copy_${n}`
  const copy = deepCopyFieldWithSuffix(original, suffix)
  copy.label = `${original.label} (副本)`
  copy.key = `${original.key ?? 'field'}_copy_${n}`
  // Assign a new UUID to the copy and all its descendants
  copy.id = crypto.randomUUID()
  function reId(f: Field) {
    f.id = crypto.randomUUID()
    if (f.children) f.children.forEach(reId)
    if (f.items) f.items.forEach(reId)
  }
  reId(copy)
  parentArray.splice(index + 1, 0, copy)
  emit('update:modelValue', [...props.modelValue])
  emit('update')
}

// Expose collapseAll for parent template ref access
defineExpose({ collapseAll })
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
