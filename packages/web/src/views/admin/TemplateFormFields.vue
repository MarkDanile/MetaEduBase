<template>
  <div class="space-y-4">
    <!-- 模板名称 -->
    <div>
      <label class="field-label">模板名称 <span class="text-[var(--color-danger)]">*</span></label>
      <input
        :value="form.name"
        class="ui-input w-full"
        placeholder="例如：教案模板"
        maxlength="100"
        @input="emit('update:form', { ...form, name: ($event.target as HTMLInputElement).value })"
      />
    </div>

    <!-- 关联文档类型 -->
    <div>
      <label class="field-label">关联文档类型</label>
      <div class="flex flex-wrap gap-1.5 mb-2">
        <span
          v-for="dt in form.doc_types"
          :key="dt"
          class="ui-tag-blue flex items-center gap-1"
        >
          {{ dt }}
          <button @click="removeDocType(dt)" class="hover:text-[var(--color-danger)]">
            <X :size="10" />
          </button>
        </span>
      </div>
      <div class="relative">
        <input
          :value="docTypeInput"
          class="ui-input w-full pr-20"
          placeholder="输入后回车添加"
          @keydown.enter.prevent="addDocType"
          @input="onDocTypeInput"
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
          @update:model-value="onFieldsChange"
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
</template>

<script setup lang="ts">
import { X, AlertTriangle, CheckCircle, Plus, LayoutGrid } from "lucide-vue-next";
import { templateApi, type Field, type Template } from "@/services/template";
import FieldItem from "./FieldItem.vue";

// --- Form value shape used in both directions across the modal boundary ---
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
  aiGenerated: boolean;
  docTypeInput: string;
  typeWarning: string;
  // The currently edited template, when present, is used to filter out the
  // current template from the cross-template doc-type collision check.
  template?: Template | null;
}>();

const emit = defineEmits<{
  "update:form": [form: TemplateForm];
  "update:docTypeInput": [val: string];
  "update:typeWarning": [val: string];
  "update:aiGenerated": [val: boolean];
}>();

function onFieldsChange(fields: Field[]) {
  emit("update:form", { ...props.form, fields });
}

// --- Field tree helpers (private to this component) ---
function countFields(fields: Field[]): number {
  let count = 0
  for (const f of fields) {
    count++
    if (f.children) count += countFields(f.children)
    if (f.items) count += countFields(f.items)
  }
  return count
}

function findNode(nodes: Field[], id: string): Field | null {
  for (const node of nodes) {
    if (node.id === id) return node
    const childList = node.type === "object" ? node.children : node.type === "array" ? node.items : []
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
      const childList = n.type === "object" ? n.children : n.type === "array" ? n.items : []
      if (childList?.length) {
        if (n.type === "object") return { ...n, children: removeNode(n.children!, id) }
        if (n.type === "array") return { ...n, items: removeNode(n.items!, id) }
      }
      return n
    })
}

// --- Field operations ---
function addRootField() {
  const fields = [...props.form.fields, { id: crypto.randomUUID(), key: "", label: "", type: "text" as const }]
  emit("update:form", { ...props.form, fields })
}

function addChildField(parentId: string) {
  const parent = findNode(props.form.fields, parentId)
  if (!parent) return
  if (parent.type === "object") {
    if (!parent.children) parent.children = []
    parent.children.push({ id: crypto.randomUUID(), key: "", label: "", type: "text" as const })
  } else if (parent.type === "array") {
    if (!parent.items) parent.items = []
    parent.items.push({ id: crypto.randomUUID(), key: "", label: "", type: "text" as const })
  }
  emit("update:form", { ...props.form, fields: [...props.form.fields] })
}

function addColumnField(parentId: string) {
  const parent = findNode(props.form.fields, parentId)
  if (!parent || parent.type !== "table") return
  if (!parent.columns) parent.columns = []
  parent.columns.push({ key: "", label: "", type: "text" as const })
  emit("update:form", { ...props.form, fields: [...props.form.fields] })
}

function removeField(id: string) {
  emit("update:form", { ...props.form, fields: removeNode(props.form.fields, id) })
}

function removeColumnField(parentId: string, colIndex: number) {
  const parent = findNode(props.form.fields, parentId)
  if (!parent?.columns) return
  parent.columns.splice(colIndex, 1)
  emit("update:form", { ...props.form, fields: [...props.form.fields] })
}

function syncFields() {
  emit("update:form", { ...props.form, fields: [...props.form.fields] })
}

// --- Doc-type helpers ---
async function addDocType() {
  const val = props.docTypeInput.trim()
  if (!val) return
  if (props.form.doc_types.includes(val)) {
    emit("update:typeWarning", `文档类型「${val}」已存在于此模板中，每个类型只能添加一次。`)
    return
  }
  // Check other templates
  try {
    const { data } = await templateApi.checkDocType(val)
    if (data.used && !data.templates.find((t: { id: string; name: string }) => t.id === props.template?.id)) {
      emit("update:typeWarning", `文档类型「${val}」已被模板「${data.templates[0]?.name}」使用。上传该类型的文档时将匹配多个模板。`)
    } else {
      emit("update:typeWarning", "")
    }
  } catch {
    // Ignore check errors
  }
  emit("update:form", { ...props.form, doc_types: [...props.form.doc_types, val] })
  emit("update:docTypeInput", "")
}

function removeDocType(dt: string) {
  emit("update:form", { ...props.form, doc_types: props.form.doc_types.filter(d => d !== dt) })
  emit("update:typeWarning", "")
}

function checkDocTypeDuplicate() {
  if (props.typeWarning) {
    emit("update:typeWarning", "")
  }
}

function onDocTypeInput(e: Event) {
  const value = (e.target as HTMLInputElement).value
  emit("update:docTypeInput", value)
  checkDocTypeDuplicate()
}
</script>
