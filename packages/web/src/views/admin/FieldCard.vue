<template>
  <div class="field-card" :class="{ 'is-container': isContainer }">
    <!-- Card header -->
    <div class="card-header" :style="{ paddingLeft: `${depth * 20 + 12}px` }">
      <!-- Drag handle -->
      <button class="drag-handle" title="拖拽排序" aria-label="拖拽排序">
        <GripVertical :size="14" class="text-[var(--color-ink-tertiary)]" />
      </button>

      <!-- Label + key -->
      <div class="card-title" @click="isContainer && toggleExpand()">
        <span class="card-label">{{ node.label || '未命名字段' }}</span>
        <span class="card-key">{{ node.key || '—' }}</span>
      </div>

      <!-- Type badge -->
      <span class="type-badge" :class="`type-badge--${node.type}`">
        {{ typeLabel }}
      </span>

      <!-- Expand chevron -->
      <button v-if="isContainer" class="expand-btn" @click.stop="toggleExpand()">
        <ChevronDown :size="14" class="text-[var(--color-ink-tertiary)]" />
      </button>

      <!-- Copy subtree -->
      <button class="action-btn" @click.stop="emit('copySubtree', node.id)" title="复制子树" aria-label="复制子树">
        <Copy :size="14" />
      </button>

      <!-- Delete -->
      <button class="delete-btn" @click.stop="emit('remove', node.id)" title="删除字段">
        <Trash2 :size="13" />
      </button>
    </div>

    <!-- Expanded detail -->
    <div v-if="expanded" class="card-detail">
      <div class="detail-fields" :style="{ paddingLeft: `${depth * 20 + 12}px` }">
        <div class="detail-row">
          <label class="detail-label">标签</label>
          <input
            :value="node.label"
            class="detail-input"
            placeholder="字段中文标签"
            @input="emit('updateField', node.id, 'label', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div class="detail-row">
          <label class="detail-label">键名</label>
          <input
            :value="node.key"
            class="detail-input detail-input--mono"
            placeholder="snake_case"
            @input="emit('updateField', node.id, 'key', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div class="detail-row">
          <label class="detail-label">说明</label>
          <input
            :value="node.description || ''"
            class="detail-input"
            placeholder="字段说明（可选）"
            @input="emit('updateField', node.id, 'description', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div class="detail-row">
          <label class="detail-label">类型</label>
          <select
            :value="node.type"
            class="detail-select"
            @change="emit('changeType', node.id, ($event.target as HTMLSelectElement).value as Field['type'])"
          >
            <option v-for="ft in FIELD_TYPES" :key="ft.value" :value="ft.value">
              {{ ft.label }}
            </option>
          </select>
        </div>
      </div>

      <!-- Table columns -->
      <div v-if="node.type === 'table'" class="sub-section" :style="{ paddingLeft: `${depth * 20 + 12}px` }">
        <div class="sub-header">
          <span class="sub-title">列定义</span>
          <button class="sub-add-btn" @click="emit('addColumn', node.id)">
            <Plus :size="11" /> 添加列
          </button>
        </div>
        <div v-for="(col, ci) in node.columns" :key="`col-${ci}`" class="column-row">
          <input v-model="col.label" class="col-input" placeholder="列标签" @blur="emit('update')" />
          <input v-model="col.key" class="col-input col-key" placeholder="列键名" @blur="emit('update')" />
          <select v-model="col.type" class="col-select" @change="emit('update')">
            <option v-for="ct in COLUMN_TYPES" :key="ct.value" :value="ct.value">
              {{ ct.label }}
            </option>
          </select>
          <button class="col-del-btn" @click="emit('removeColumn', node.id, ci)">
            <X :size="12" />
          </button>
        </div>
        <div v-if="!node.columns?.length" class="sub-empty">
          暂无列，点击上方添加
        </div>
      </div>

      <!-- Object children -->
      <div v-if="node.type === 'object'" class="sub-section" :style="{ paddingLeft: `${depth * 20 + 12}px` }">
        <div class="sub-header">
          <span class="sub-title">子字段</span>
          <button class="sub-add-btn" @click="emit('addChild', node.id)">
            <Plus :size="11" /> 添加子字段
          </button>
        </div>
        <div v-if="!node.children?.length" class="sub-empty">
          暂无子字段，点击上方添加
        </div>
      </div>

      <!-- Array items -->
      <div v-if="node.type === 'array'" class="sub-section" :style="{ paddingLeft: `${depth * 20 + 12}px` }">
        <div class="sub-header">
          <span class="sub-title">数组成员模板</span>
          <button class="sub-add-btn" @click="emit('addChild', node.id)">
            <Plus :size="11" /> 添加字段
          </button>
        </div>
        <div v-if="!node.items?.length" class="sub-empty">
          暂无成员，点击上方添加
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ChevronDown, GripVertical, Trash2, Plus, Copy, X } from 'lucide-vue-next'
import { FIELD_TYPES, COLUMN_TYPES } from '@/constants/field-types'
import type { Field } from '@/services/template'

interface FieldNode extends Field {
  id: string
  depth: number
}

const props = defineProps<{
  node: FieldNode
}>()

const emit = defineEmits<{
  'toggle': [id: string]
  'update': []
  'remove': [id: string]
  'updateField': [id: string, field: 'key' | 'label' | 'description', value: string]
  'changeType': [id: string, type: Field['type']]
  'addChild': [parentId: string]
  'addColumn': [parentId: string]
  'removeColumn': [parentId: string, colIndex: number]
  'copySubtree': [id: string]
}>()

const depth = computed(() => props.node.depth ?? 0)

const isContainer = computed(() =>
  ['object', 'table', 'array'].includes(props.node.type)
)

const expanded = ref(!isContainer.value)

function toggleExpand() {
  expanded.value = !expanded.value
  emit('toggle', props.node.id)
}

watch(isContainer, (value) => {
  if (!value) {
    expanded.value = true
  }
}, { immediate: true })

const typeLabel = computed(() =>
  FIELD_TYPES.find(f => f.value === props.node.type)?.label ?? props.node.type
)
</script>

<style scoped>
.field-card {
  border: 1.5px solid var(--panel-border);
  border-radius: 10px;
  margin-bottom: 6px;
  background: white;
  transition: border-color 0.15s, box-shadow 0.15s;
  overflow: hidden;
}
.field-card:hover { border-color: rgba(99,102,241,0.4); box-shadow: 0 2px 8px rgba(99,102,241,0.06); }
.field-card.is-container { border-left: 3px solid var(--color-accent); }

/* ── Header ── */
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: default;
  min-height: 48px;
}

.drag-handle {
  cursor: grab;
  padding: 2px;
  border-radius: 4px;
  flex-shrink: 0;
  background: none;
  border: none;
  display: inline-flex;
  align-items: center;
}
.drag-handle:active { cursor: grabbing; }
.drag-handle:hover { background: var(--interactive-hover-bg); }

.card-title {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  cursor: pointer;
}

.card-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-key {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  font-family: monospace;
}

/* ── Type badges ── */
.type-badge {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
  flex-shrink: 0;
}
.type-badge--text     { background: rgba(99,102,241,0.12); color: #6366f1; }
.type-badge--textarea { background: rgba(14,165,233,0.12); color: #0ea5e9; }
.type-badge--number  { background: rgba(168,85,247,0.12); color: #a855f7; }
.type-badge--object  { background: rgba(249,115,22,0.12); color: #f97316; }
.type-badge--table   { background: rgba(16,185,129,0.12); color: #059669; }
.type-badge--array   { background: rgba(245,158,11,0.12); color: #d97706; }

.expand-btn {
  background: none; border: none; cursor: pointer; padding: 2px;
  display: flex; align-items: center; border-radius: 4px; flex-shrink: 0;
}
.expand-btn:hover { background: var(--interactive-hover-bg); }

.delete-btn {
  background: none; border: none; cursor: pointer; padding: 4px;
  display: flex; align-items: center; color: var(--color-ink-tertiary);
  border-radius: 4px; flex-shrink: 0;
}
.delete-btn:hover { color: var(--color-danger); background: rgba(239,68,68,0.08); }

.action-btn {
  background: none; border: none; cursor: pointer; padding: 4px;
  display: flex; align-items: center; color: var(--color-ink-tertiary);
  border-radius: 4px; flex-shrink: 0;
}
.action-btn:hover { color: var(--color-accent); background: var(--color-accent-bg); }

/* ── Detail ── */
.card-detail {
  border-top: 1px solid var(--panel-border);
  background: rgba(99,102,241,0.02);
  padding: 4px 0 12px;
}

.detail-fields {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 12px;
}

.detail-row {
  display: grid;
  grid-template-columns: 44px 1fr;
  align-items: center;
  gap: 8px;
}

.detail-label {
  font-size: 11px;
  color: var(--color-ink-tertiary);
  text-align: right;
}

.detail-input {
  padding: 4px 8px;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  font-size: 12px;
  background: white;
  color: var(--color-ink);
}
.detail-input:focus { outline: none; border-color: var(--color-accent); }
.detail-input--mono { font-family: monospace; }

.detail-select {
  padding: 4px 8px;
  border: 1px solid var(--panel-border);
  border-radius: 6px;
  font-size: 12px;
  background: white;
  color: var(--color-ink);
  cursor: pointer;
}
.detail-select:focus { outline: none; border-color: var(--color-accent); }

/* ── Sub sections ── */
.sub-section { padding-right: 12px; margin-top: 8px; }

.sub-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.sub-title { font-size: 11px; color: var(--color-ink-tertiary); font-weight: 500; }

.sub-add-btn {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 11px; color: var(--color-accent); background: none;
  border: 1px dashed var(--color-accent); cursor: pointer;
  padding: 2px 6px; border-radius: 4px;
}
.sub-add-btn:hover { background: var(--color-accent-bg); }

.sub-empty { font-size: 11px; color: var(--color-ink-tertiary); padding: 4px 0 8px; font-style: italic; }

/* ── Column row ── */
.column-row {
  display: grid;
  grid-template-columns: 1fr 1fr auto auto;
  gap: 6px;
  align-items: center;
  margin-bottom: 4px;
}

.col-input {
  padding: 3px 6px;
  border: 1px solid var(--panel-border);
  border-radius: 5px;
  font-size: 11px;
  background: white;
  color: var(--color-ink);
}
.col-input:focus { outline: none; border-color: var(--color-accent); }
.col-key { font-family: monospace; }

.col-select {
  padding: 3px 4px;
  border: 1px solid var(--panel-border);
  border-radius: 5px;
  font-size: 11px;
  background: white;
  cursor: pointer;
}

.col-del-btn {
  background: none; border: none; cursor: pointer; padding: 2px;
  color: var(--color-ink-tertiary); border-radius: 4px; display: flex; align-items: center;
}
.col-del-btn:hover { color: var(--color-danger); }
</style>
