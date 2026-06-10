<template>
  <div class="ui-page-shell">
    <PageHeader :title="isNew ? '新建模板' : '编辑模板'" subtitle="配置结构化数据抽取字段">
      <template #extra>
        <button class="ui-btn ui-btn-primary" @click="save" :disabled="saving">
          保存
        </button>
      </template>
    </PageHeader>

    <!-- REQ-002-1: Collapse/expand + search (shown when totalFields > 30) -->
    <div v-if="totalFields > 30" class="ui-panel p-3 mb-4 flex gap-2 items-center">
      <button class="ui-btn-ghost text-[var(--text-small)]" @click="toggleAllCollapse">
        {{ allCollapsed ? '全部展开' : '全部折叠' }}
      </button>
      <input
        v-model="searchQuery"
        class="ui-input flex-1"
        placeholder="按 label / key 搜索字段..."
      />
      <span v-if="searchQuery" class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
        搜索中：{{ searchQuery }}
      </span>
    </div>

    <!-- Undo toast area -->
    <div v-if="deletedStack.length > 0" class="undo-toast">
      <span>已删除字段「{{ deletedStack[0].field.key || deletedStack[0].field.label }}」，5 秒内可撤销</span>
      <button class="undo-toast-btn" @click="undoRemove">撤销</button>
    </div>

    <div v-if="loading" class="flex justify-center py-12">
      <LoadingSpinner text="加载中..." />
    </div>

    <div v-else class="xl:grid xl:grid-cols-[1fr_340px] gap-6">
      <!-- Left: form -->
      <div class="space-y-4">
        <div class="ui-panel p-4 space-y-4">
          <div>
            <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">模板名称</label>
            <input v-model="form.name" class="ui-input w-full" placeholder="如：教案模板" />
          </div>
          <div>
            <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">关联文档类型</label>
            <input v-model="docTypeInput" class="ui-input w-full" placeholder="输入后回车添加，多个用逗号分隔" @keydown.enter.prevent="addDocType" />
            <div class="flex flex-wrap gap-1 mt-2">
              <span v-for="dt in form.doc_types" :key="dt" class="ui-tag-blue flex items-center gap-1">
                {{ dt }}
                <button @click="form.doc_types.splice(form.doc_types.indexOf(dt), 1)"><X :size="10" /></button>
              </span>
            </div>
          </div>
        </div>

        <div class="ui-panel p-4">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">字段定义</h3>
            <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
              {{ totalFields }} 个字段
            </span>
          </div>
          <FieldItem
            v-if="form.fields.length > 0"
            :model-value="form.fields"
            :search-query="searchQuery"
            @update:model-value="onFieldsChange"
            @add-root="addField"
            @add-child="onAddChild"
            @add-column="onAddColumn"
            @remove="onFieldRemove"
            @remove-column="onRemoveColumn"
            @update="syncFields"
          />
          <p v-else class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] text-center py-4">
            暂无字段，点击上方按钮添加
          </p>
        </div>
      </div>

      <!-- Right: AI init -->
      <div class="ui-panel p-4 space-y-4 h-fit">
        <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">AI 初始化</h3>
        <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
          上传样例文档，AI 自动分析结构并生成字段定义
        </p>

        <div>
          <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">
            补充说明（可选）
          </label>
          <textarea
            v-model="form.ai_context"
            class="ui-input w-full resize-none"
            rows="3"
            placeholder="补充说明（可选）——如：课程标准模板需包含前置能力与知识基础"
          />
          <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-1">
            此说明仅供 AI 参考，不会强制要求模型输出
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, X } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import FieldItem from '@/views/admin/FieldItem.vue'
import { templateApi, type Field } from '@/services/template'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const loading = ref(false)
const saving = ref(false)
const docTypeInput = ref('')

const isNew = computed(() => route.params.id === 'new')

const defaultField = (): Field => ({ id: crypto.randomUUID(), key: '', label: '', type: 'text' })

const form = ref({
  name: '',
  doc_types: [] as string[],
  fields: [] as Field[],
  ai_prompt: null as string | null,
  ai_context: null as string | null,
  source_file_id: null as string | null,
})

// ─── REQ-002-1: Undo stack (single undo) ──────────────────────────────────────
interface DeletedField {
  field: Field
  parentKey: string | null  // null = root
  index: number
}
const deletedStack = ref<DeletedField[]>([])
let undoTimer: ReturnType<typeof setTimeout> | null = null

// ─── REQ-002-1: Collapse + search ─────────────────────────────────────────────
const allCollapsed = ref(false)
const searchQuery = ref('')

const totalFields = computed(() => {
  function count(fields: Field[]): number {
    let n = fields.length
    for (const f of fields) {
      if (f.children) n += count(f.children)
      if (f.items) n += count(f.items)
    }
    return n
  }
  return count(form.value.fields)
})

function toggleAllCollapse() {
  allCollapsed.value = !allCollapsed.value
  window.dispatchEvent(new CustomEvent('field-card-toggle-all', { detail: { collapsed: allCollapsed.value } }))
}

// ─── Field operations ─────────────────────────────────────────────────────────
function onFieldsChange(fields: Field[]) {
  form.value.fields = fields
}

function addField() {
  form.value.fields.push(defaultField())
}

function findNode(nodes: Field[], id: string): Field | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const childList = node.type === 'object' ? node.children : node.type === 'array' ? node.items : null
    if (childList?.length) {
      const found = findNode(childList, id)
      if (found) return found
    }
  }
  return null
}

function onAddChild(parentId: string) {
  const parent = findNode(form.value.fields, parentId)
  if (!parent) return
  if (parent.type === 'object') {
    if (!parent.children) parent.children = []
    parent.children.push(defaultField())
  } else if (parent.type === 'array') {
    if (!parent.items) parent.items = []
    parent.items.push(defaultField())
  }
  syncFields()
}

function onAddColumn(parentId: string) {
  const parent = findNode(form.value.fields, parentId)
  if (!parent || parent.type !== 'table') return
  if (!parent.columns) parent.columns = []
  parent.columns.push({ key: '', label: '', type: 'text' })
  syncFields()
}

function onRemoveColumn(parentId: string, colIndex: number) {
  const parent = findNode(form.value.fields, parentId)
  if (!parent?.columns) return
  parent.columns.splice(colIndex, 1)
  syncFields()
}

// ─── REQ-002-1: Remove with undo ─────────────────────────────────────────────
function onFieldRemove(id: string) {
  const result = findAndRemove(form.value.fields, id)
  if (result) {
    // Clear any previous undo timer
    if (undoTimer) clearTimeout(undoTimer)
    deletedStack.value = [result]
    undoTimer = setTimeout(() => {
      deletedStack.value = []
      undoTimer = null
    }, 5000)
    toast.info(`已删除字段「${result.field.key || result.field.label}」，5 秒内可撤销`)
  }
}

function undoRemove() {
  if (undoTimer) clearTimeout(undoTimer)
  undoTimer = null
  const entry = deletedStack.value[0]
  if (!entry) return
  deletedStack.value = []
  if (entry.parentKey === null) {
    form.value.fields.splice(entry.index, 0, entry.field)
  } else {
    const parent = findFieldByKey(form.value.fields, entry.parentKey)
    if (parent?.children) {
      parent.children.splice(entry.index, 0, entry.field)
    } else if (parent?.items) {
      parent.items.splice(entry.index, 0, entry.field)
    }
  }
  toast.success('已撤销删除')
}

function findAndRemove(fields: Field[], id: string): DeletedField | null {
  for (let i = 0; i < fields.length; i++) {
    if (fields[i].id === id || (fields[i] as any).key === id) {
      const f = fields[i]
      fields.splice(i, 1)
      return { field: f, parentKey: null, index: i }
    }
    if (fields[i].children) {
      const result = findAndRemove(fields[i].children!, id)
      if (result) return { ...result, parentKey: fields[i].key ?? null }
    }
    if (fields[i].items) {
      const result = findAndRemove(fields[i].items!, id)
      if (result) return { ...result, parentKey: fields[i].key ?? null }
    }
  }
  return null
}

function findFieldByKey(fields: Field[], key: string): Field | null {
  for (const f of fields) {
    if (f.key === key) return f
    if (f.children) {
      const r = findFieldByKey(f.children, key)
      if (r) return r
    }
    if (f.items) {
      const r = findFieldByKey(f.items, key)
      if (r) return r
    }
  }
  return null
}

function syncFields() {
  form.value.fields = [...form.value.fields]
}

function addDocType() {
  const val = docTypeInput.value.trim()
  if (val && !form.value.doc_types.includes(val)) {
    form.value.doc_types.push(val)
  }
  docTypeInput.value = ''
}

async function load(id: string) {
  loading.value = true
  try {
    const { data } = await templateApi.get(id)
    form.value.name = data.name
    form.value.doc_types = [...data.doc_types]
    form.value.fields = ensureIds(JSON.parse(JSON.stringify(data.fields)))
    form.value.ai_prompt = data.ai_prompt
    form.value.ai_context = data.ai_context
    form.value.source_file_id = data.source_file_id
  } catch {
    toast.error('加载模板失败')
    router.push('/admin/template')
  } finally {
    loading.value = false
  }
}

function ensureIds(fields: Field[]): Field[] {
  return fields.map(f => ({
    ...f,
    id: f.id || crypto.randomUUID(),
    children: f.children ? ensureIds(f.children) : undefined,
    items: f.items ? ensureIds(f.items) : undefined,
  }))
}

async function save() {
  if (!form.value.name.trim()) {
    toast.error('请填写模板名称')
    return
  }
  saving.value = true
  try {
    if (isNew.value) {
      await templateApi.create({
        name: form.value.name,
        doc_types: form.value.doc_types,
        fields: form.value.fields,
        ai_prompt: form.value.ai_prompt,
        ai_context: form.value.ai_context,
        source_file_id: form.value.source_file_id,
      })
      toast.success('创建成功')
    } else {
      await templateApi.update(route.params.id as string, {
        name: form.value.name,
        doc_types: form.value.doc_types,
        fields: form.value.fields,
        ai_prompt: form.value.ai_prompt,
        ai_context: form.value.ai_context,
        source_file_id: form.value.source_file_id,
      })
      toast.success('保存成功')
    }
    router.push('/admin/template')
  } catch {
    toast.error(isNew.value ? '创建失败' : '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  if (!isNew.value) {
    load(route.params.id as string)
  }
})
</script>

<style scoped>
.undo-toast {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  margin-bottom: 12px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: 8px;
  font-size: 13px;
  color: var(--color-ink);
}

.undo-toast-btn {
  background: var(--color-accent);
  color: white;
  border: none;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.undo-toast-btn:hover { opacity: 0.9; }
</style>
