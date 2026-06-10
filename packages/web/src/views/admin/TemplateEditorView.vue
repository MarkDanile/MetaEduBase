<template>
  <div class="ui-page-shell">
    <PageHeader :title="isNew ? '新建模板' : '编辑模板'" subtitle="配置结构化数据抽取字段">
      <template #extra>
        <!-- REQ-002-2: Version history + export (edit mode only) -->
        <button v-if="!isNew" class="ui-btn ui-btn-ghost" @click="showVersionHistory = !showVersionHistory">
          <History :size="14" /> 版本历史
        </button>
        <button v-if="!isNew" class="ui-btn ui-btn-ghost" @click="onExport">
          <Download :size="14" /> 导出 JSON
        </button>
        <!-- REQ-002-4: schema_version display + restore button (edit mode) -->
        <span v-if="!isNew && form.schema_version" class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] flex items-center px-2">
          schema_version: {{ form.schema_version }}
        </span>
        <button
          v-if="!isNew && form.is_deprecated"
          class="ui-btn ui-btn-ghost"
          @click="onUndeprecate"
          :disabled="undeprecating"
        >
          <RotateCcw :size="14" /> 恢复使用
        </button>
        <button
          v-else-if="!isNew && !form.is_deprecated"
          class="ui-btn ui-btn-ghost"
          @click="onDeprecateFromEditor"
        >
          <ArchiveX :size="14" /> 弃用
        </button>
        <button class="ui-btn ui-btn-primary" @click="save" :disabled="saving || hasValidationErrors">
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

    <!-- REQ-002-2: Version history panel -->
    <VersionHistoryPanel
      v-if="showVersionHistory && !isNew"
      :template-id="route.params.id as string"
      @rolled-back="onRolledBack"
    />

    <!-- REQ-002-4: destructive type change confirmation -->
    <Teleport to="body">
      <div v-if="pendingTypeChange" class="modal-mask" @click.self="onCancelChangeType">
        <div class="modal-panel">
          <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] mb-2">
            破坏性变更确认
          </h3>
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-4">
            此操作将把字段类型从
            <span class="font-medium text-[var(--color-ink)]">{{ pendingTypeChange.oldType }}</span>
            改为
            <span class="font-medium text-[var(--color-ink)]">{{ pendingTypeChange.newType }}</span>。
            已有抽取结果中该字段会失配，且会触发 schema_version 自增。是否继续？
          </p>
          <div class="flex justify-end gap-2">
            <button class="ui-btn ui-btn-ghost" @click="onCancelChangeType">取消</button>
            <button class="ui-btn ui-btn-primary" @click="onConfirmChangeType">确认继续</button>
          </div>
        </div>
      </div>

      <!-- REQ-002-4: field delete confirmation -->
      <div v-if="pendingRemove" class="modal-mask" @click.self="onCancelRemoveField">
        <div class="modal-panel">
          <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] mb-2">
            破坏性变更确认
          </h3>
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-4">
            删除字段后，已有抽取结果中该字段会被裁剪，且会触发 schema_version 自增。是否继续？
          </p>
          <div class="flex justify-end gap-2">
            <button class="ui-btn ui-btn-ghost" @click="onCancelRemoveField">取消</button>
            <button class="ui-btn ui-btn-primary" @click="onConfirmRemoveField">确认删除</button>
          </div>
        </div>
      </div>

      <!-- REQ-002-4: deprecate from editor dialog -->
      <div v-if="pendingDeprecate" class="modal-mask" @click.self="onCancelDeprecate">
        <div class="modal-panel">
          <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] mb-2">
            弃用模板
          </h3>
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-3">
            弃用后该模板将不再被新文档自动匹配。
          </p>
          <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">
            弃用原因 <span class="text-[var(--color-danger)]">*</span>
          </label>
          <textarea
            v-model="deprecateReasonInput"
            class="ui-input w-full resize-none"
            rows="3"
            placeholder="如：使用率低，已被新模板替代"
          />
          <div class="flex justify-end gap-2 mt-4">
            <button class="ui-btn ui-btn-ghost" @click="onCancelDeprecate">取消</button>
            <button
              class="ui-btn ui-btn-primary"
              :disabled="!deprecateReasonInput.trim() || deprecating"
              @click="onConfirmDeprecate"
            >
              确认弃用
            </button>
          </div>
        </div>
      </div>
    </Teleport>

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
            ref="fieldItemRef"
            :model-value="form.fields"
            :search-query="searchQuery"
            :field-errors-by-id="fieldErrorMap"
            @update:model-value="onFieldsChange"
            @add-root="addField"
            @add-child="onAddChild"
            @add-column="onAddColumn"
            @remove="onRequestRemoveField"
            @remove-column="onRemoveColumn"
            @update="syncFields"
            @change-type="onRequestChangeType"
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
import { X, History, Download, ArchiveX, RotateCcw } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import FieldItem from '@/views/admin/FieldItem.vue'
import VersionHistoryPanel from '@/components/VersionHistoryPanel.vue'
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
  // REQ-002-4
  schema_version: 1,
  is_deprecated: false,
  deprecated_at: null as string | null,
  deprecated_reason: null as string | null,
})

// REQ-002-4: state for confirm-on-destructive-change dialog
interface PendingTypeChange {
  id: string
  oldType: Field['type']
  newType: Field['type']
}
const pendingTypeChange = ref<PendingTypeChange | null>(null)

interface PendingRemove {
  id: string
}
const pendingRemove = ref<PendingRemove | null>(null)

interface PendingDeprecate {
  reason: string
}
const pendingDeprecate = ref<PendingDeprecate | null>(null)
const deprecateReasonInput = ref('')
const deprecating = ref(false)
const undeprecating = ref(false)

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
const fieldItemRef = ref<InstanceType<typeof FieldItem> | null>(null)

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
  fieldItemRef.value?.collapseAll(allCollapsed.value)
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

// REQ-002-4: Remove with destructive-change confirmation
function onRequestRemoveField(id: string) {
  pendingRemove.value = { id }
}

// REQ-002-4: commit / cancel pending destructive type change
function onRequestChangeType(id: string, newType: Field['type']) {
  const node = findNode(form.value.fields, id)
  if (!node) return
  const oldType = node.type
  if (oldType === newType) return
  const isContainerMutual = (
    ['object', 'table', 'array'].includes(oldType) &&
    ['object', 'table', 'array'].includes(newType)
  )
  const isContainerFromLeaf = (
    !['object', 'table', 'array'].includes(oldType) &&
    ['object', 'table', 'array'].includes(newType)
  )
  const isLeafFromContainer = (
    ['object', 'table', 'array'].includes(oldType) &&
    !['object', 'table', 'array'].includes(newType)
  )
  // Container ⇄ container OR container ⇄ leaf → destructive
  if (isContainerMutual || isContainerFromLeaf || isLeafFromContainer) {
    // Apply the change in the form so the UI updates, then prompt the user
    // (REQ-002-1 / spec risk #1: confirm MUST be shown after a visible
    // change so the user understands what's at stake).
    node.type = newType
    syncFields()
    pendingTypeChange.value = { id, oldType, newType }
  } else {
    // leaf ⇄ leaf (text ⇄ textarea ⇄ number): no confirmation needed
    node.type = newType
    syncFields()
  }
}

function onConfirmChangeType() {
  // Already applied in onRequestChangeType; just mark force_schema_bump
  // so the next save bumps schema_version (AC-17).
  forceSchemaBump.value = true
  pendingTypeChange.value = null
}

function onCancelChangeType() {
  if (!pendingTypeChange.value) return
  const node = findNode(form.value.fields, pendingTypeChange.value.id)
  if (node) {
    node.type = pendingTypeChange.value.oldType
    syncFields()
  }
  pendingTypeChange.value = null
  toast.info('已取消类型变更')
}

function onConfirmRemoveField() {
  if (!pendingRemove.value) return
  const id = pendingRemove.value.id
  pendingRemove.value = null
  forceSchemaBump.value = true
  onFieldRemove(id)
}

function onCancelRemoveField() {
  pendingRemove.value = null
  toast.info('已取消删除')
}

// REQ-002-4: deprecate / undeprecate from editor
function onDeprecateFromEditor() {
  deprecateReasonInput.value = ''
  pendingDeprecate.value = { reason: '' }
}

async function onConfirmDeprecate() {
  const reason = deprecateReasonInput.value.trim()
  if (!reason) {
    toast.error('请填写弃用原因')
    return
  }
  deprecating.value = true
  try {
    const { data } = await templateApi.deprecate(route.params.id as string, { reason })
    form.value.is_deprecated = data.is_deprecated
    form.value.deprecated_at = data.deprecated_at
    form.value.deprecated_reason = data.deprecated_reason
    pendingDeprecate.value = null
    toast.success('已弃用')
  } catch {
    toast.error('弃用失败')
  } finally {
    deprecating.value = false
  }
}

function onCancelDeprecate() {
  pendingDeprecate.value = null
}

async function onUndeprecate() {
  undeprecating.value = true
  try {
    const { data } = await templateApi.undeprecate(route.params.id as string)
    form.value.is_deprecated = data.is_deprecated
    form.value.deprecated_at = data.deprecated_at
    form.value.deprecated_reason = data.deprecated_reason
    toast.success('已恢复使用')
  } catch {
    toast.error('恢复失败')
  } finally {
    undeprecating.value = false
  }
}

// REQ-002-4: force schema_version bump on next save
const forceSchemaBump = ref(false)

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
    if (fields[i].id === id || fields[i].key === id) {
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

// ─── REQ-002-2: Version history + export ────────────────────────────────────
const showVersionHistory = ref(false)

async function onExport() {
  try {
    const { data } = await templateApi.export(route.params.id as string)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.template.name}_${new Date().toISOString().replace(/[-:T]/g, '').slice(0, 12)}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('导出成功')
  } catch {
    toast.error('导出失败')
  }
}

function onRolledBack() {
  showVersionHistory.value = false
  load(route.params.id as string)
  toast.info('已回滚，页面已刷新')
}

function syncFields() {
  form.value.fields = [...form.value.fields]
}

// REQ-002-4: field naming validation (recursive)
const _RESERVED_META_KEYS = new Set([
  'id', 'version', 'layer', 'matched_type', 'confidence', 'reason',
])
const _FIELD_KEY_RE = /^[a-z][a-z0-9_]*$/

interface FieldKeyError {
  path: string  // e.g. "fields[0].key" or "fields[0].children[1].key"
  message: string
}

function validateFields(fields: Field[], parentPath = 'fields'): FieldKeyError[] {
  const errors: FieldKeyError[] = []
  const seen: Set<string> = new Set()
  for (let i = 0; i < fields.length; i++) {
    const f = fields[i]
    const path = `${parentPath}[${i}].key`
    if (f.key) {
      if (_RESERVED_META_KEYS.has(f.key)) {
        errors.push({ path, message: `「${f.key}」是保留字段名` })
      } else if (!_FIELD_KEY_RE.test(f.key)) {
        errors.push({ path, message: 'key 必须以小写字母开头，仅含小写字母、数字、下划线' })
      }
      if (seen.has(f.key)) {
        errors.push({ path, message: `同层 key 重复：${f.key}` })
      }
      seen.add(f.key)
    }
    if (f.children) {
      errors.push(...validateFields(f.children, `${parentPath}[${i}].children`))
    }
    if (f.items) {
      errors.push(...validateFields(f.items, `${parentPath}[${i}].items`))
    }
  }
  return errors
}

const fieldKeyErrors = computed<FieldKeyError[]>(() =>
  validateFields(form.value.fields)
)
const hasValidationErrors = computed(() => fieldKeyErrors.value.length > 0)

const fieldErrorMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  function walk(fields: Field[], parentPath: string) {
    for (let i = 0; i < fields.length; i++) {
      const f = fields[i]
      if (f.id) {
        const path = `${parentPath}[${i}].key`
        const err = fieldKeyErrors.value.find(e => e.path === path)
        if (err) map[f.id] = err.message
      }
      if (f.children) walk(f.children, `${parentPath}[${i}].children`)
      if (f.items) walk(f.items, `${parentPath}[${i}].items`)
    }
  }
  walk(form.value.fields, 'fields')
  return map
})

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
    // REQ-002-4
    form.value.schema_version = data.schema_version ?? 1
    form.value.is_deprecated = data.is_deprecated ?? false
    form.value.deprecated_at = data.deprecated_at ?? null
    form.value.deprecated_reason = data.deprecated_reason ?? null
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
  if (hasValidationErrors.value) {
    toast.error('字段命名校验未通过，请修正后保存')
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
      const payload: Record<string, unknown> = {
        name: form.value.name,
        doc_types: form.value.doc_types,
        fields: form.value.fields,
        ai_prompt: form.value.ai_prompt,
        ai_context: form.value.ai_context,
        source_file_id: form.value.source_file_id,
      }
      // REQ-002-4: if the user confirmed a destructive type change or
      // a field removal, send force_schema_bump=true so the server
      // bumps schema_version (AC-8 / AC-17 / AC-18).
      if (forceSchemaBump.value) {
        payload.force_schema_bump = true
        forceSchemaBump.value = false
      }
      await templateApi.update(route.params.id as string, payload as never)
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

/* REQ-002-4: shared modal styles */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-panel {
  background: white;
  border-radius: 12px;
  padding: 20px 24px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
}
</style>
