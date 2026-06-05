<template>
  <div class="space-y-3">
    <div class="grid grid-cols-[1fr_1fr_auto] gap-2 items-start">
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">字段名</label>
        <input v-model="local.key" class="ui-input w-full" placeholder="field_key" />
      </div>
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">中文标签</label>
        <input v-model="local.label" class="ui-input w-full" placeholder="字段标签" />
      </div>
      <div>
        <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">类型</label>
        <select v-model="local.type" class="ui-input w-full">
          <option v-for="ft in FIELD_TYPES" :key="ft.value" :value="ft.value">{{ ft.label }}</option>
        </select>
      </div>
      <button
        class="ui-btn-ghost p-1.5 !rounded-[var(--radius-sm)] mt-5"
        @click="$emit('remove')"
      >
        <X :size="14" class="text-[var(--color-danger)]" />
      </button>
    </div>

    <div>
      <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">说明（可选）</label>
      <input v-model="local.description" class="ui-input w-full" placeholder="字段描述，供 AI 抽取参考" />
    </div>

    <!-- Object: children -->
    <div v-if="local.type === 'object'" class="pl-4 border-l-2 border-[var(--panel-border)]">
      <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">子字段</p>
      <FieldEditor
        v-for="(child, i) in childrenArr"
        :key="i"
        :model-value="childrenArr[i]"
        @update:model-value="(v) => { const arr = [...childrenArr]; arr[i] = v; setChildren(arr); }"
        @remove="setChildren(childrenArr.filter((_, idx) => idx !== i))"
      />
      <button class="ui-btn-ghost text-[var(--text-small)]" @click="setChildren([...childrenArr, { key: '', label: '', type: 'text' }])">
        <Plus :size="12" /> 添加子字段
      </button>
    </div>

    <!-- Table: columns -->
    <div v-if="local.type === 'table'" class="pl-4 border-l-2 border-[var(--panel-border)]">
      <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">列定义</p>
      <div class="space-y-1">
        <div v-for="(col, i) in columnsArr" :key="i" class="grid grid-cols-[1fr_1fr_auto_auto] gap-2 items-center">
          <input v-model="col.key" class="ui-input w-full" placeholder="列键名" />
          <input v-model="col.label" class="ui-input w-full" placeholder="列标签" />
          <select v-model="col.type" class="ui-input w-full">
            <option v-for="ct in COLUMN_TYPES" :key="ct.value" :value="ct.value">{{ ct.label }}</option>
          </select>
          <button class="ui-btn-ghost p-1.5 !rounded-[var(--radius-sm)]" @click="setColumns(columnsArr.filter((_, idx) => idx !== i))">
            <X :size="12" class="text-[var(--color-danger)]" />
          </button>
        </div>
      </div>
      <button class="ui-btn-ghost text-[var(--text-small)] mt-1" @click="setColumns([...columnsArr, { key: '', label: '', type: 'text' }])">
        <Plus :size="12" /> 添加列
      </button>
    </div>

    <!-- Array: items template -->
    <div v-if="local.type === 'array'" class="pl-4 border-l-2 border-[var(--panel-border)]">
      <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-2">数组项模板</p>
      <FieldEditor
        v-if="itemsArr.length > 0"
        :model-value="itemsArr[0]"
        @update:model-value="(v) => setItems([v])"
        @remove="setItems([])"
      />
      <button v-else class="ui-btn-ghost text-[var(--text-small)]" @click="setItems([{ key: '', label: '', type: 'text' }])">
        <Plus :size="12" /> 添加数组项模板
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { Plus, X } from 'lucide-vue-next'
import { FIELD_TYPES, COLUMN_TYPES } from '@/constants/field-types'
import type { Field } from '@/services/template'
import FieldEditor from './FieldEditor.vue'

const props = defineProps<{ modelValue: Field }>()
const emit = defineEmits<{
  'update:modelValue': [value: Field]
  'remove': []
}>()

const local = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// Ensure children, columns, items are always defined arrays
const childrenArr = computed(() => local.value.children ?? [])
const columnsArr = computed(() => local.value.columns ?? [])
const itemsArr = computed(() => local.value.items ?? [])

function setChildren(val: Field[]) {
  local.value = { ...local.value, children: val }
}
function setColumns(val: typeof columnsArr.value) {
  local.value = { ...local.value, columns: val }
}
function setItems(val: Field[]) {
  local.value = { ...local.value, items: val }
}

// Auto-initialize arrays when type changes
watch(() => local.value.type, (type) => {
  if (type === 'object' && !local.value.children) {
    local.value = { ...local.value, children: [] }
  } else if (type === 'table' && !local.value.columns) {
    local.value = { ...local.value, columns: [] }
  } else if (type === 'array' && !local.value.items) {
    local.value = { ...local.value, items: [] }
  }
}, { immediate: true })
</script>