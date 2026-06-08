<template>
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
      <input
        :value="aiDocType"
        class="ui-input w-full text-[12px] py-2"
        placeholder="如：教案"
        @input="emit('update:aiDocType', ($event.target as HTMLInputElement).value)"
      />
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
            @click.stop="clearFile"
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
        :value="form.ai_context ?? ''"
        class="ui-input w-full resize-none text-[12px]"
        rows="3"
        placeholder="补充说明（可选）——如：课程标准模板需包含前置能力与知识基础"
        @input="emit('update:form', { ...form, ai_context: ($event.target as HTMLTextAreaElement).value })"
      />
      <p class="text-[10px] text-[var(--color-ink-tertiary)] mt-1">此说明仅供 AI 参考，不会强制要求模型输出</p>
    </div>

    <button
      class="ui-btn ui-btn-primary w-full justify-center text-[13px] py-2"
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
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Zap, Upload, AlertTriangle, CheckCircle, X } from "lucide-vue-next";
import { documentApi } from "@/services/document";
import { templateApi, type Field } from "@/services/template";
import { useToast } from "@/composables/useToast";

export interface TemplateForm {
  name: string;
  doc_types: string[];
  fields: Field[];
  ai_prompt: string | null;
  ai_context: string | null;
  source_file_id: string | null;
}

const props = defineProps<{
  form: TemplateForm;
  aiDocType: string;
  isEdit: boolean;
  uploadFile: File | null;
  uploading: boolean;
  generating: boolean;
}>();

const emit = defineEmits<{
  "update:form": [form: TemplateForm];
  "update:aiDocType": [val: string];
  "update:uploadFile": [val: File | null];
  "update:uploading": [val: boolean];
  "update:generating": [val: boolean];
  "update:aiGenerated": [val: boolean];
}>();

const toast = useToast();

// File input ref (private)
const fileInputRef = ref<HTMLInputElement | null>(null);

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/msword']
  if (!validTypes.includes(file.type)) {
    toast.error('仅支持 PDF 和 DOCX 格式')
    return
  }

  emit("update:uploadFile", file)
  emit("update:uploading", true)

  try {
    const formData = new FormData()
    formData.append('file', file)
    const { data } = await documentApi.uploadFile(formData)
    emit("update:form", { ...props.form, source_file_id: data.id })
    toast.success('文档上传成功')
  } catch {
    toast.error('文档上传失败')
    emit("update:uploadFile", null)
  } finally {
    emit("update:uploading", false)
    if (fileInputRef.value) {
      fileInputRef.value.value = ''
    }
  }
}

function clearFile() {
  emit("update:uploadFile", null)
}

function ensureIds(fields: Field[]): Field[] {
  return fields.map(f => ({
    ...f,
    id: f.id || crypto.randomUUID(),
    children: f.children ? ensureIds(f.children) : undefined,
    items: f.items ? ensureIds(f.items) : undefined,
  }))
}

async function regenerateAI() {
  if (!props.aiDocType.trim()) {
    toast.error('请输入文档类型名')
    return
  }
  if (props.generating) return
  emit("update:generating", true)
  try {
    const { data } = await templateApi.initByAI(
      props.aiDocType,
      props.form.source_file_id || undefined,
      props.form.ai_context || undefined,
    )
    if (data.fields && data.fields.length > 0) {
      emit("update:form", { ...props.form, fields: ensureIds(data.fields) })
      emit("update:aiGenerated", true)
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
    emit("update:generating", false)
  }
}
</script>
