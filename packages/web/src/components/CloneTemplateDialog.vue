<template>
  <Teleport to="body">
    <div v-if="open" class="modal-overlay" role="dialog" aria-modal="true" @click.self="$emit('update:open', false)" @keydown.escape="$emit('update:open', false)">
      <div class="modal">
        <!-- Header -->
        <div class="modal-header">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-[10px] bg-[var(--color-accent-bg)] flex items-center justify-center">
              <Copy :size="18" class="text-[var(--color-accent)]" />
            </div>
            <div>
              <h2 class="text-[var(--text-section-title)] font-semibold text-[var(--color-ink)]">
                复制模板
              </h2>
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                基于现有模板创建副本
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
              <label class="field-label">新模板名称</label>
              <input v-model="form.name" class="ui-input w-full" :placeholder="`${source.name} - 副本`" />
            </div>
            <div>
              <label class="field-label">文档类型</label>
              <div class="flex flex-wrap gap-1 mb-2">
                <span v-for="dt in form.doc_types" :key="dt" class="ui-tag-blue flex items-center gap-1">
                  {{ dt }}
                  <button class="hover:text-[var(--color-danger)]" @click="removeDocType(dt)">
                    <X :size="10" />
                  </button>
                </span>
              </div>
              <input
                :value="docTypeInput"
                @input="docTypeInput = ($event.target as HTMLInputElement).value"
                @keydown.enter.prevent="addDocType"
                class="ui-input w-full"
                placeholder="输入后回车添加"
              />
            </div>
            <div>
              <label class="field-label">样例文件 ID（可选）</label>
              <input v-model="form.source_file_id" class="ui-input w-full" placeholder="UUID" />
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button class="ui-btn ui-btn-ghost" @click="$emit('update:open', false)">取消</button>
          <button
            class="ui-btn ui-btn-primary"
            :disabled="!form.name.trim() || form.doc_types.length === 0 || submitting"
            @click="onSubmit"
          >
            <Check :size="14" />
            {{ submitting ? '复制中...' : '确认复制' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { X, Copy, Check } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { templateApi, type Template, type CloneTemplateRequest } from '@/services/template'

const props = defineProps<{
  open: boolean
  source: Template
}>()

const emit = defineEmits<{
  'update:open': [val: boolean]
  'cloned': [newId: string]
}>()

const toast = useToast()
const submitting = ref(false)
const docTypeInput = ref('')

const form = reactive<CloneTemplateRequest>({
  name: '',
  doc_types: [],
  source_file_id: null,
})

watch(() => props.open, (val) => {
  if (val) {
    form.name = `${props.source.name} - 副本`
    form.doc_types = [...(props.source.doc_types ?? [])]
    form.source_file_id = null
    docTypeInput.value = ''
  }
})

function addDocType() {
  const v = docTypeInput.value.trim()
  if (v && !form.doc_types.includes(v)) form.doc_types.push(v)
  docTypeInput.value = ''
}

function removeDocType(dt: string) {
  form.doc_types = form.doc_types.filter(d => d !== dt)
}

async function onSubmit() {
  if (submitting.value) return
  submitting.value = true
  try {
    const { data } = await templateApi.clone(props.source.id, form)
    toast.success('复制成功')
    emit('update:open', false)
    emit('cloned', data.id)
  } catch {
    toast.error('复制失败')
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
</style>
