<template>
  <div class="p-6">
    <PageHeader title="数据要素模板" subtitle="配置各类文档的结构化抽取模板">
      <template #extra>
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
          @click="openEditModal(t)"
        >
          <div class="col-num">
            <span class="row-num">{{ i + 1 }}</span>
          </div>
          <div class="col-name">
            <span class="row-name">{{ t.name }}</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Trash2, Pencil } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import LoadingSpinner from '@/components/LoadingSpinner.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import TemplateModal from './TemplateModal.vue'
import { templateApi, type Template, type Field } from '@/services/template'
import { useToast } from '@/composables/useToast'

const toast = useToast()

const templates = ref<Template[]>([])
const loading = ref(false)
const showModal = ref(false)
const showDelete = ref(false)
const selectedTemplate = ref<Template | null>(null)
const deleteTarget = ref<Template | null>(null)

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

function onSaved() {
  loadTemplates()
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
  grid-template-columns: 56px 1fr 200px 80px 120px 80px;
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
  grid-template-columns: 56px 1fr 200px 80px 120px 80px;
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
