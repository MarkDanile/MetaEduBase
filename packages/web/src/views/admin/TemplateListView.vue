<template>
  <div class="p-6">
    <PageHeader title="数据要素模板" subtitle="配置各类文档的结构化抽取模板">
      <template #extra>
        <button class="ui-btn ui-btn-ghost" @click="showImport = true">
          <Upload :size="14" /> 导入模板
        </button>
        <button class="ui-btn ui-btn-primary" @click="openCreateModal">
          <Plus :size="16" /> 新建模板
        </button>
      </template>
    </PageHeader>

    <div class="mt-4">
      <LoadingSpinner v-if="loading" text="加载模板..." />
      <EmptyState
        v-else-if="templates.length === 0"
        title="暂无模板"
        hint="点击右上角「新建模板」创建第一个数据要素模板"
      />
      <div v-else class="template-container">
        <!-- Header -->
        <div class="list-header">
          <div class="col-num">序号</div>
          <div class="col-name">模板名称</div>
          <div class="col-types">文档类型</div>
          <div class="col-fields">字段数</div>
          <div class="col-date">更新时间</div>
          <div class="col-ops">操作</div>
        </div>

        <!-- Rows -->
        <div
          v-for="(t, i) in templates"
          :key="t.id"
          class="list-row"
          :class="{ 'is-deprecated': t.is_deprecated }"
          @click="openEditModal(t)"
        >
          <div class="col-num">
            <span class="row-num">{{ i + 1 }}</span>
          </div>
          <div class="col-name">
            <span class="row-name">{{ t.name }}</span>
            <!-- REQ-002-4: 已弃用 badge -->
            <span v-if="t.is_deprecated" class="ui-tag-grey text-[var(--text-micro)] ml-2" title="已弃用">
              已弃用
            </span>
          </div>
          <div class="col-types">
            <div class="flex flex-wrap gap-1">
              <span v-for="dt in t.doc_types" :key="dt" class="ui-tag-blue text-[var(--text-micro)]">
                {{ dt }}
              </span>
              <span v-if="t.doc_types.length === 0" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                未指定类型
              </span>
            </div>
          </div>
          <div class="col-fields">
            <span class="text-[var(--text-body)] text-[var(--color-ink)]">{{ countFields(t.fields) }}</span>
          </div>
          <div class="col-date">
            <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatDate(t.updated_at) }}</span>
          </div>
          <div class="col-ops" @click.stop>
            <button class="op-btn" @click="openEditModal(t)" title="编辑">
              <Pencil :size="14" class="text-[var(--color-ink-tertiary)]" />
            </button>
            <button class="op-btn" @click="openCloneDialog(t)" title="复制">
              <Copy :size="14" class="text-[var(--color-ink-tertiary)]" />
            </button>
            <!-- REQ-002-4: 弃用按钮（仅未弃用时显示） -->
            <button
              v-if="!t.is_deprecated"
              class="op-btn"
              @click="openDeprecateDialog(t)"
              title="弃用"
            >
              <ArchiveX :size="14" class="text-[var(--color-ink-tertiary)]" />
            </button>
            <button class="op-btn danger" @click="confirmDelete(t)" title="删除">
              <Trash2 :size="14" class="text-[var(--color-danger)]" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create/Edit Modal -->
    <TemplateModal
      v-model:open="showModal"
      :template="selectedTemplate"
      @saved="onSaved"
    />

    <!-- Delete Confirmation -->
    <ConfirmDialog
      v-model:open="showDelete"
      title="删除模板"
      :message="`确定删除模板「${deleteTarget?.name}」？此操作不可恢复。`"
      danger
      @confirm="doDelete"
    />

    <!-- Clone Dialog -->
    <CloneTemplateDialog
      v-if="cloneSource"
      v-model:open="showClone"
      :source="cloneSource"
      @cloned="onCloned"
    />

    <!-- Import Dialog -->
    <ImportTemplateDialog
      v-model:open="showImport"
      @imported="onImported"
    />

    <!-- REQ-002-4: deprecate dialog (inline to keep the diff minimal) -->
    <Teleport to="body">
      <div v-if="showDeprecate" class="modal-mask" @click.self="showDeprecate = false">
        <div class="modal-panel">
          <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)] mb-2">
            弃用模板
          </h3>
          <p class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-3">
            弃用后该模板将不再被新文档自动匹配。确定要弃用「{{ deprecateTarget?.name }}」？
          </p>
          <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">
            弃用原因 <span class="text-[var(--color-danger)]">*</span>
          </label>
          <textarea
            v-model="deprecateReason"
            class="ui-input w-full resize-none"
            rows="3"
            placeholder="如：使用率低，已被新模板替代"
          />
          <div class="flex justify-end gap-2 mt-4">
            <button class="ui-btn ui-btn-ghost" @click="showDeprecate = false">取消</button>
            <button class="ui-btn ui-btn-primary" :disabled="!deprecateReason.trim() || deprecating" @click="doDeprecate">
              确认弃用
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Trash2, Pencil, Copy, Upload, ArchiveX } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import CloneTemplateDialog from '@/components/CloneTemplateDialog.vue'
import ImportTemplateDialog from '@/components/ImportTemplateDialog.vue'
import TemplateModal from './TemplateModal.vue'
import { templateApi, type Template, type Field } from '@/services/template'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const toast = useToast()

const templates = ref<Template[]>([])
const loading = ref(false)
const showModal = ref(false)
const showDelete = ref(false)
const showClone = ref(false)
const showImport = ref(false)
const selectedTemplate = ref<Template | null>(null)
const deleteTarget = ref<Template | null>(null)
const cloneSource = ref<Template | null>(null)

// REQ-002-4: deprecate dialog state
const showDeprecate = ref(false)
const deprecateTarget = ref<Template | null>(null)
const deprecateReason = ref('')
const deprecating = ref(false)

function countFields(fields: Field[]): number {
  let count = 0
  for (const f of fields) {
    count++
    if (f.children) count += countFields(f.children)
    if (f.items) count += countFields(f.items)
  }
  return count
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    year: 'numeric',
  })
}

function openCreateModal() {
  selectedTemplate.value = null
  showModal.value = true
}

function openEditModal(t: Template) {
  selectedTemplate.value = t
  showModal.value = true
}

function confirmDelete(t: Template) {
  deleteTarget.value = t
  showDelete.value = true
}

async function doDelete() {
  if (!deleteTarget.value) return
  try {
    await templateApi.delete(deleteTarget.value.id)
    toast.success('模板已删除')
    templates.value = templates.value.filter(t => t.id !== deleteTarget.value!.id)
    deleteTarget.value = null
    showDelete.value = false
  } catch {
    toast.error('删除失败')
  }
}

function openCloneDialog(t: Template) {
  cloneSource.value = t
  showClone.value = true
}

function onCloned(newId: string) {
  router.push(`/admin/template/${newId}`)
}

function onImported(newId: string) {
  loadTemplates()
  router.push(`/admin/template/${newId}`)
}

function onSaved() {
  loadTemplates()
}

// REQ-002-4: deprecate flow
function openDeprecateDialog(t: Template) {
  deprecateTarget.value = t
  deprecateReason.value = ''
  showDeprecate.value = true
}

async function doDeprecate() {
  if (!deprecateTarget.value || !deprecateReason.value.trim()) return
  deprecating.value = true
  try {
    await templateApi.deprecate(deprecateTarget.value.id, {
      reason: deprecateReason.value.trim(),
    })
    toast.success('已弃用')
    showDeprecate.value = false
    await loadTemplates()
  } catch {
    toast.error('弃用失败')
  } finally {
    deprecating.value = false
  }
}

async function loadTemplates() {
  loading.value = true
  try {
    const { data } = await templateApi.list()
    templates.value = data
  } catch {
    toast.error('加载模板失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<style scoped>
.template-container {
  background: #ffffff;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 3px rgba(0, 0, 0, 0.06);
}

.list-header {
  display: grid;
  grid-template-columns: 56px 1fr 200px 80px 120px 100px;
  gap: 0;
  padding: 10px 16px;
  background: #f8f9fa;
  border-bottom: 1px solid #e5e7eb;
  font-size: 11px;
  font-weight: 600;
  color: #6b7280;
  align-items: center;
}

.list-row {
  display: grid;
  grid-template-columns: 56px 1fr 200px 80px 120px 100px;
  gap: 0;
  padding: 12px 16px;
  border-bottom: 1px solid #f3f4f6;
  cursor: pointer;
  align-items: center;
  transition: background 0.1s;
}

.list-row:last-child {
  border-bottom: none;
}

.list-row:hover {
  background: #f9fafb;
}

/* REQ-002-4: deprecated row visual */
.list-row.is-deprecated {
  background: #f3f4f6;
  opacity: 0.85;
}
.list-row.is-deprecated:hover {
  background: #e5e7eb;
}
.list-row.is-deprecated .row-name {
  color: var(--color-ink-tertiary);
  text-decoration: line-through;
  text-decoration-color: rgba(0, 0, 0, 0.25);
}
.ui-tag-grey {
  display: inline-flex;
  align-items: center;
  background: #e5e7eb;
  color: #6b7280;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
}

/* REQ-002-4: deprecate modal */
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

.col-num {
  display: flex;
  align-items: center;
}

.row-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #4f46e5;
  font-family: monospace;
}

.col-name {
  display: flex;
  align-items: center;
  min-width: 0;
}

.row-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.col-types {
  display: flex;
  align-items: center;
}

.col-fields {
  display: flex;
  align-items: center;
  justify-content: center;
}

.col-date {
  display: flex;
  align-items: center;
}

.col-ops {
  display: flex;
  align-items: center;
  gap: 4px;
}

.op-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  transition: background 0.1s;
}

.op-btn:hover {
  background: var(--interactive-hover-bg);
}

.op-btn.danger:hover {
  background: rgba(239, 68, 68, 0.08);
}
</style>
