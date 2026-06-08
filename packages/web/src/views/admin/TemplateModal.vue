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
            <TemplateFormFields
              :form="form"
              :ai-generated="aiGenerated"
              :doc-type-input="docTypeInput"
              :type-warning="typeWarning"
              :template="template ?? null"
              @update:form="(f) => (form = f)"
              @update:doc-type-input="(v) => (docTypeInput = v)"
              @update:type-warning="(v) => (typeWarning = v)"
              @update:ai-generated="(v) => (aiGenerated = v)"
            />
            <TemplateAiPanel
              :form="form"
              :ai-doc-type="aiDocType"
              :is-edit="isEdit"
              :upload-file="uploadFile"
              :uploading="uploading"
              :generating="generating"
              @update:form="(f) => (form = f)"
              @update:ai-doc-type="(v) => (aiDocType = v)"
              @update:upload-file="(v) => (uploadFile = v)"
              @update:uploading="(v) => (uploading = v)"
              @update:generating="(v) => (generating = v)"
              @update:ai-generated="(v) => (aiGenerated = v)"
            />
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button class="ui-btn ui-btn-ghost" @click="handleClose">取消</button>
          <button class="ui-btn ui-btn-primary" @click="handleSave" :disabled="saving">
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
import { X, LayoutGrid, Check } from 'lucide-vue-next'
import { templateApi, type Field, type Template } from '@/services/template'
import { useToast } from '@/composables/useToast'

import TemplateFormFields from './TemplateFormFields.vue'
import TemplateAiPanel from './TemplateAiPanel.vue'

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
