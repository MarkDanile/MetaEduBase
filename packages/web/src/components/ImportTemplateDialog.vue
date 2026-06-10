<template>
  <Teleport to="body">
    <div v-if="open" class="modal-overlay" role="dialog" aria-modal="true" @click.self="$emit('update:open', false)" @keydown.escape="$emit('update:open', false)">
      <div class="modal">
        <!-- Header -->
        <div class="modal-header">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-[10px] bg-[var(--color-accent-bg)] flex items-center justify-center">
              <Upload :size="18" class="text-[var(--color-accent)]" />
            </div>
            <div>
              <h2 class="text-[var(--text-section-title)] font-semibold text-[var(--color-ink)]">
                导入模板
              </h2>
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                从 JSON 文件导入模板配置
              </p>
            </div>
          </div>
          <button class="modal-close-btn ml-auto" @click="$emit('update:open', false)" aria-label="关闭">
            <X :size="18" />
          </button>
        </div>

        <!-- Body -->
        <div class="modal-body">
          <div class="space-y-4">
            <div>
              <label class="field-label">选择 JSON 文件</label>
              <input
                ref="fileInput"
                type="file"
                accept=".json"
                @change="onFileSelect"
                class="ui-input w-full"
              />
            </div>
            <div v-if="preview" class="preview-box">
              <p class="text-[var(--text-small)] text-[var(--color-ink)]">
                <strong>{{ preview.name }}</strong>
                <span class="text-[var(--color-ink-tertiary)]"> · {{ preview.doc_types?.join(', ') || '无文档类型' }}</span>
              </p>
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                {{ preview.fields?.length || 0 }} 个字段
              </p>
            </div>
            <div v-if="error" class="error-box">
              {{ error }}
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button class="ui-btn ui-btn-ghost" @click="$emit('update:open', false)">取消</button>
          <button
            class="ui-btn ui-btn-primary"
            :disabled="!payload || submitting"
            @click="onSubmit"
          >
            <Check :size="14" />
            {{ submitting ? '导入中...' : '确认导入' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { X, Upload, Check } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { templateApi } from '@/services/template'

defineProps<{ open: boolean }>()
const emit = defineEmits<{
  'update:open': [val: boolean]
  'imported': [newId: string]
}>()

const toast = useToast()
const payload = ref<Record<string, unknown> | null>(null)
const preview = ref<{ name: string; doc_types?: string[]; fields?: unknown[] } | null>(null)
const error = ref('')
const submitting = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function reset() {
  payload.value = null
  preview.value = null
  error.value = ''
  submitting.value = false
}

async function onFileSelect(e: Event) {
  error.value = ''
  payload.value = null
  preview.value = null
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    const parsed = JSON.parse(text)
    if (parsed.format !== 'metaedu-template-v1') {
      error.value = '不支持的格式：' + (parsed.format || '未知')
      return
    }
    payload.value = parsed.template as Record<string, unknown>
    preview.value = {
      name: (parsed.template as Record<string, unknown>).name as string,
      doc_types: (parsed.template as Record<string, unknown>).doc_types as string[],
      fields: (parsed.template as Record<string, unknown>).fields as unknown[],
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    error.value = 'JSON 解析失败：' + msg
  }
}

async function onSubmit() {
  if (!payload.value || submitting.value) return
  submitting.value = true
  try {
    const { data } = await templateApi.import({ template: payload.value })
    toast.success('导入成功')
    emit('update:open', false)
    emit('imported', data.id)
    reset()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    const detail = err.response?.data?.detail || err.message || '未知错误'
    error.value = '导入失败：' + detail
  } finally {
    submitting.value = false
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
  max-width: 520px;
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

.preview-box {
  padding: 12px;
  border-radius: 8px;
  background: var(--color-accent-bg);
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.error-box {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: var(--color-danger);
  font-size: var(--text-small);
}
</style>
