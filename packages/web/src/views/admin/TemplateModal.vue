<template>
  <Teleport to="body">
    <div v-if="open" class="modal-overlay" role="dialog" aria-modal="true" @keydown.escape="handleClose">
      <div class="modal" @click.stop>
        <!-- Header -->
        <div class="modal-header">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-[10px] bg-[var(--color-accent-bg)] flex items-center justify-center">
              <LayoutGrid :size="18" class="text-[var(--color-accent)]" />
            </div>
            <div>
              <h2 class="text-[var(--text-section-title)] font-semibold text-[var(--color-ink)]">
                {{ isEdit ? '编辑模板' : '新建模板' }}
              </h2>
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                {{ isEdit ? '修改模板配置' : '配置文档类型和数据抽取字段' }}
              </p>
            </div>
          </div>
          <button class="modal-close-btn ml-auto" @click="handleClose" aria-label="关闭">
            <X :size="18" />
          </button>
        </div>

        <!-- Body -->
        <div class="modal-body">
          <div class="grid grid-cols-[1fr_280px] gap-6">
            <!-- Left: Form -->
            <div class="space-y-4">
              <!-- 模板名称 -->
              <div>
                <label class="field-label">模板名称 <span class="text-[var(--color-danger)]">*</span></label>
                <input
                  v-model="form.name"
                  class="liquid-input w-full"
                  placeholder="例如：教案模板"
                  maxlength="100"
                />
              </div>

              <!-- 关联文档类型 -->
              <div>
                <label class="field-label">关联文档类型</label>
                <div class="flex flex-wrap gap-1.5 mb-2">
                  <span
                    v-for="dt in form.doc_types"
                    :key="dt"
                    class="liquid-tag-blue flex items-center gap-1"
                  >
                    {{ dt }}
                    <button @click="removeDocType(dt)" class="hover:text-[var(--color-danger)]">
                      <X :size="10" />
                    </button>
                  </span>
                </div>
                <div class="relative">
                  <input
                    v-model="docTypeInput"
                    class="liquid-input w-full pr-20"
                    placeholder="输入后回车添加"
                    @keydown.enter.prevent="addDocType"
                    @input="checkDocTypeDuplicate"
                  />
                  <button
                    class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-small)] text-[var(--color-accent)] hover:underline"
                    @click="addDocType"
                  >
                    添加
                  </button>
                </div>
                <!-- Duplicate warning -->
                <div v-if="typeWarning" class="mt-2 px-3 py-2 rounded-lg bg-[rgba(245,158,11,0.08)] border border-[rgba(245,158,11,0.3)]">
                  <div class="flex gap-2 items-start">
                    <AlertTriangle :size="14" class="text-[#f59e0b] flex-shrink-0 mt-0.5" />
                    <p class="text-[11px] text-[#92400e] leading-relaxed">{{ typeWarning }}</p>
                  </div>
                </div>
              </div>

              <!-- 字段列表 -->
              <div>
                <div class="flex items-center justify-between mb-3">
                  <label class="field-label mb-0">字段列表</label>
                  <span class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                    {{ countFields(form.fields) }} 个字段
                  </span>
                </div>

                <!-- AI Banner + 手动添加 -->
                <div v-if="aiGenerated" class="ai-generated-banner">
                  <div class="flex items-center gap-2">
                    <CheckCircle :size="14" class="text-[#059669] flex-shrink-0" />
                    <span class="text-[12px] text-[#059669]">AI 已生成 {{ countFields(form.fields) }} 个字段，可手动调整或继续添加</span>
                  </div>
                  <button class="manual-add-btn" @click="addRootField">
                    <Plus :size="12" /> 手动添加
                  </button>
                </div>

                <!-- Field tree -->
                <div class="ui-panel p-3">
                  <FieldItem
                    v-if="form.fields.length > 0"
                    :model-value="form.fields"
                    @update:model-value="form.fields = $event"
                    @add-root="addRootField"
                    @add-child="addChildField"
                    @add-column="addColumnField"
                    @remove="removeField"
                    @remove-column="removeColumnField"
                    @update="syncFields"
                  />
                  <!-- Empty state when no fields -->
                  <div v-else class="field-empty-state">
                    <LayoutGrid :size="24" class="text-[var(--color-ink-tertiary)] mx-auto mb-2" />
                    <p class="text-[12px] text-[var(--color-ink-tertiary)] text-center">
                      暂无字段，使用右侧 AI 辅助生成或点击下方添加
                    </p>
                    <button class="empty-add-btn" @click="addRootField">
                      <Plus :size="13" /> 添加字段
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right: AI panel -->
            <div class="ai-panel">
              <div class="ai-panel-accent"></div>
              <div class="flex items-center gap-2 mb-2">
                <Zap :size="16" class="text-[var(--color-accent)]" />
                <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">AI 辅助配置</h3>
              </div>
              <p class="text-[11px] text-[var(--color-ink-tertiary)] mb-4">
                AI 分析职教文档结构，自动生成字段定义
              </p>

              <div class="mb-3">
                <label class="text-[11px] text-[var(--color-ink-tertiary)] mb-1.5 block">文档类型名</label>
                <input v-model="aiDocType" class="liquid-input w-full text-[12px] py-2" placeholder="如：教案" />
              </div>

              <div class="mb-4">
                <label class="text-[11px] text-[var(--color-ink-tertiary)] mb-1.5 block">样例文档（可选）</label>
                <input
                  ref="fileInputRef"
                  type="file"
                  class="hidden"
                  accept=".pdf,.docx,.doc"
                  @change="handleFileSelect"
                />
                <div
                  class="border-2 border-dashed rounded-lg py-3 px-2 text-center cursor-pointer transition-colors"
                  :class="uploadFile ? 'border-[#059669] bg-[rgba(16,185,129,0.05)]' : 'border-[var(--panel-border-strong)] hover:border-[var(--color-accent)]'"
                  @click="fileInputRef?.click()"
                >
                  <div v-if="uploading" class="flex items-center justify-center gap-2 py-1">
                    <div class="w-4 h-4 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin"></div>
                    <p class="text-[11px] text-[var(--color-accent)]">上传中...</p>
                  </div>
                  <div v-else-if="uploadFile" class="flex items-center gap-2">
                    <CheckCircle :size="14" class="text-[#059669] flex-shrink-0" />
                    <p class="text-[11px] text-[#059669] truncate max-w-[180px]">{{ uploadFile.name }}</p>
                    <button
                      class="text-[var(--color-ink-tertiary)] hover:text-[var(--color-danger)] flex-shrink-0"
                      @click.stop="uploadFile = null"
                    >
                      <X :size="12" />
                    </button>
                  </div>
                  <div v-else>
                    <Upload :size="18" class="text-[var(--color-ink-tertiary)] mx-auto mb-1" />
                    <p class="text-[11px] text-[var(--color-ink-tertiary)]">点击上传 PDF/DOCX</p>
                  </div>
                </div>
              </div>

              <div class="mb-4">
                <label class="text-[11px] text-[var(--color-ink-tertiary)] mb-1.5 block">补充说明（可选）</label>
                <textarea
                  v-model="form.ai_context"
                  class="liquid-input w-full resize-none text-[12px]"
                  rows="3"
                  placeholder="补充说明（可选）——如：课程标准模板需包含前置能力与知识基础"
                />
                <p class="text-[10px] text-[var(--color-ink-tertiary)] mt-1">此说明仅供 AI 参考，不会强制要求模型输出</p>
              </div>

              <button
                class="liquid-btn liquid-btn-primary w-full justify-center text-[13px] py-2"
                :disabled="generating"
                @click="regenerateAI"
              >
                <div v-if="generating" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                <Zap v-else :size="13" />
                {{ generating ? 'AI 生成中...' : (isEdit ? '重新生成' : '开始生成') }}
              </button>

              <!-- Overwrite warning for edit -->
              <div v-if="isEdit && form.fields.length > 0" class="mt-3 px-3 py-2 rounded-lg bg-[rgba(245,158,11,0.08)] border border-[rgba(245,158,11,0.3)]">
                <div class="flex gap-2 items-start">
                  <AlertTriangle :size="12" class="text-[#f59e0b] flex-shrink-0 mt-0.5" />
                  <p class="text-[10px] text-[#92400e] leading-relaxed">
                    重新生成将用新结果<span class="font-medium">完全覆盖</span>当前字段
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button class="liquid-btn liquid-btn-ghost" @click="handleClose">取消</button>
          <button class="liquid-btn liquid-btn-primary" @click="handleSave" :disabled="saving">
            <Check :size="14" />
            {{ saving ? '保存中...' : (isEdit ? '保存' : '创建模板') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { X, Zap, Upload, AlertTriangle, Check, CheckCircle, LayoutGrid, Plus } from 'lucide-vue-next'
import { templateApi, type Template, type Field } from '@/services/template'
import { documentApi } from '@/services/document'
import { useToast } from '@/composables/useToast'

import FieldItem from './FieldItem.vue'

const props = defineProps<{
  open: boolean
  template?: Template | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'saved': []
}>()

const toast = useToast()

const isEdit = computed(() => !!props.template)
const saving = ref(false)
const generating = ref(false)
const aiGenerated = ref(false)
const aiDocType = ref('')

// File upload
const fileInputRef = ref<HTMLInputElement | null>(null)
const uploadFile = ref<File | null>(null)
const uploading = ref(false)

const docTypeInput = ref('')
const typeWarning = ref('')

const form = ref({
  name: '',
  doc_types: [] as string[],
  fields: [] as Field[],
  ai_prompt: null as string | null,
  ai_context: null as string | null,
  source_file_id: null as string | null,
})

// Reset form when template changes or modal opens
watch(() => props.open, (val) => {
  if (val) {
    resetForm()
    if (props.template) {
      form.value.name = props.template.name
      form.value.doc_types = [...props.template.doc_types]
      form.value.fields = ensureIds(props.template.fields)
      form.value.ai_prompt = props.template.ai_prompt
      form.value.ai_context = props.template.ai_context ?? null
      form.value.source_file_id = props.template.source_file_id
    }
  }
})

// Auto-fill AI panel when user types template name
watch(() => form.value.name, (val) => {
  if (!val) return
  const base = val.replace(/模板$/, '')
  if (base && aiDocType.value !== base) {
    aiDocType.value = base
  }
})

function ensureIds(fields: Field[]): Field[] {
  return fields.map(f => ({
    ...f,
    id: f.id || crypto.randomUUID(),
    children: f.children ? ensureIds(f.children) : undefined,
    items: f.items ? ensureIds(f.items) : undefined,
  }))
}

function resetForm() {
  form.value = {
    name: '',
    doc_types: [],
    fields: [],
    ai_prompt: null,
    ai_context: null,
    source_file_id: null,
  }
  docTypeInput.value = ''
  typeWarning.value = ''
  aiGenerated.value = false
  uploadFile.value = null
  uploading.value = false
}

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']
  if (!validTypes.includes(file.type)) {
    toast.error('仅支持 PDF 和 DOCX 格式')
    return
  }

  uploadFile.value = file
  uploading.value = true

  try {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await documentApi.uploadFile(formData)
    form.value.source_file_id = data.id
    toast.success('文档上传成功')
  } catch {
    toast.error('文档上传失败')
    uploadFile.value = null
  } finally {
    uploading.value = false
    if (fileInputRef.value) {
      fileInputRef.value.value = ''
    }
  }
}

function countFields(fields: Field[]): number {
  let count = 0
  for (const f of fields) {
    count++
    if (f.children) count += countFields(f.children)
    if (f.items) count += countFields(f.items)
  }
  return count
}

// Field operations
function addRootField() {
  form.value.fields.push({ id: crypto.randomUUID(), key: '', label: '', type: 'text' })
}

function addChildField(parentId: string) {
  const parent = findNode(form.value.fields, parentId)
  if (!parent) return
  if (parent.type === 'object') {
    if (!parent.children) parent.children = []
    parent.children.push({ id: crypto.randomUUID(), key: '', label: '', type: 'text' })
  } else if (parent.type === 'array') {
    if (!parent.items) parent.items = []
    parent.items.push({ id: crypto.randomUUID(), key: '', label: '', type: 'text' })
  }
  form.value.fields = [...form.value.fields]
}

function addColumnField(parentId: string) {
  const parent = findNode(form.value.fields, parentId)
  if (!parent || parent.type !== 'table') return
  if (!parent.columns) parent.columns = []
  parent.columns.push({ key: '', label: '', type: 'text' })
  form.value.fields = [...form.value.fields]
}

function removeField(id: string) {
  form.value.fields = removeNode(form.value.fields, id)
}

function removeColumnField(parentId: string, colIndex: number) {
  const parent = findNode(form.value.fields, parentId)
  if (!parent?.columns) return
  parent.columns.splice(colIndex, 1)
  form.value.fields = [...form.value.fields]
}

function syncFields() {
  form.value.fields = [...form.value.fields]
}

function findNode(nodes: Field[], id: string): Field | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const childList = node.type === 'object' ? node.children : node.type === 'array' ? node.items : []
    if (childList?.length) {
      const found = findNode(childList, id)
      if (found) return found
    }
  }
  return null
}

function removeNode(nodes: Field[], id: string): Field[] {
  return nodes
    .filter(n => n.id !== id)
    .map(n => {
      const childList = n.type === 'object' ? n.children : n.type === 'array' ? n.items : []
      if (childList?.length) {
        if (n.type === 'object') return { ...n, children: removeNode(n.children!, id) }
        if (n.type === 'array') return { ...n, items: removeNode(n.items!, id) }
      }
      return n
    })
}

async function addDocType() {
  const val = docTypeInput.value.trim()
  if (!val) return

  if (form.value.doc_types.includes(val)) {
    typeWarning.value = `文档类型「${val}」已存在于此模板中，每个类型只能添加一次。`
    return
  }

  // Check other templates
  try {
    const { data } = await templateApi.checkDocType(val)
    if (data.used && !data.templates.find((t: { id: string; name: string }) => t.id === props.template?.id)) {
      typeWarning.value = `文档类型「${val}」已被模板「${data.templates[0]?.name}」使用。上传该类型的文档时将匹配多个模板。`
    } else {
      typeWarning.value = ''
    }
  } catch {
    // Ignore check errors
  }

  form.value.doc_types.push(val)
  docTypeInput.value = ''
}

function removeDocType(dt: string) {
  form.value.doc_types = form.value.doc_types.filter(d => d !== dt)
  typeWarning.value = ''
}

function checkDocTypeDuplicate() {
  // Clear warning when user starts typing
  if (typeWarning.value) {
    typeWarning.value = ''
  }
}

async function regenerateAI() {
  if (!aiDocType.value.trim()) {
    toast.error('请输入文档类型名')
    return
  }
  if (generating.value) return
  generating.value = true
  try {
    const { data } = await templateApi.initByAI(aiDocType.value, form.value.source_file_id || undefined, form.value.ai_context || undefined)
    if (data.fields && data.fields.length > 0) {
      form.value.fields = ensureIds(data.fields)
      aiGenerated.value = true
      toast.success(`AI 已生成 ${data.fields.length} 个字段`)
    } else {
      toast.error('AI 未返回有效字段，请手动添加')
    }
  } catch (error: unknown) {
    const message = typeof error === 'object' && error && 'code' in error
      ? String((error as { code?: unknown }).code)
      : ''
    if (message === 'ECONNABORTED') {
      toast.error('AI 生成超时，请稍后重试，或上传样例文档以提高生成速度')
    } else {
      toast.error('AI 生成失败，请稍后重试')
    }
  } finally {
    generating.value = false
  }
}

function handleClose() {
  emit('update:open', false)
}

async function handleSave() {
  if (!form.value.name.trim()) {
    toast.error('请填写模板名称')
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      doc_types: form.value.doc_types,
      fields: form.value.fields,
      ai_prompt: form.value.ai_prompt,
      ai_context: form.value.ai_context,
      source_file_id: form.value.source_file_id,
    }

    if (isEdit.value && props.template) {
      await templateApi.update(props.template.id, payload)
      toast.success('保存成功')
    } else {
      await templateApi.create(payload)
      toast.success('创建成功')
    }

    emit('saved')
    handleClose()
  } catch {
    toast.error(isEdit.value ? '保存失败' : '创建失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-dialog);
  backdrop-filter: blur(2px);
}

.modal {
  background: white;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  width: 95vw;
  max-width: 900px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--panel-border);
  display: flex;
  align-items: center;
  gap: 12px;
}

.modal-close-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  color: var(--color-ink-tertiary);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close-btn:hover {
  background: var(--interactive-hover-bg);
  color: var(--color-ink);
}

.modal-body {
  padding: 20px 24px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--panel-border);
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.field-label {
  display: block;
  font-size: var(--text-small);
  color: var(--color-ink-tertiary);
  margin-bottom: 6px;
  font-weight: 500;
}

.ai-panel {
  background: var(--panel-bg-muted);
  border-radius: 12px;
  padding: 16px;
  border: 1.5px solid rgba(99, 102, 241, 0.25);
  position: relative;
  overflow: hidden;
  height: fit-content;
}

.ai-generated-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.2);
  margin-bottom: 10px;
}

.manual-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--color-accent);
  background: none;
  border: 1px dashed var(--color-accent);
  cursor: pointer;
  padding: 3px 8px;
  border-radius: 6px;
}
.manual-add-btn:hover { background: var(--color-accent-bg); }

.field-empty-state {
  padding: 28px 16px;
  text-align: center;
}

.empty-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  font-size: 13px;
  color: var(--color-accent);
  background: none;
  border: 1px dashed var(--color-accent);
  cursor: pointer;
  padding: 7px 14px;
  border-radius: 8px;
}
.empty-add-btn:hover { background: var(--color-accent-bg); }

.ai-panel-accent {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
}
</style>
