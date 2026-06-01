<template>
  <div class="ui-page-shell">
    <PageHeader :title="isNew ? '新建模板' : '编辑模板'" subtitle="配置结构化数据抽取字段">
      <template #extra>
        <button class="liquid-btn liquid-btn-primary" @click="save" :disabled="saving">
          保存
        </button>
      </template>
    </PageHeader>

    <div v-if="loading" class="flex justify-center py-12">
      <LoadingSpinner text="加载中..." />
    </div>

    <div v-else class="xl:grid xl:grid-cols-[1fr_340px] gap-6">
      <!-- Left: form -->
      <div class="space-y-4">
        <div class="ui-panel p-4 space-y-4">
          <div>
            <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">模板名称</label>
            <input v-model="form.name" class="liquid-input w-full" placeholder="如：教案模板" />
          </div>
          <div>
            <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] mb-1 block">关联文档类型</label>
            <input v-model="docTypeInput" class="liquid-input w-full" placeholder="输入后回车添加，多个用逗号分隔" @keydown.enter.prevent="addDocType" />
            <div class="flex flex-wrap gap-1 mt-2">
              <span v-for="dt in form.doc_types" :key="dt" class="liquid-tag-blue flex items-center gap-1">
                {{ dt }}
                <button @click="form.doc_types.splice(form.doc_types.indexOf(dt), 1)"><X :size="10" /></button>
              </span>
            </div>
          </div>
        </div>

        <div class="ui-panel p-4">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">字段定义</h3>
            <button class="liquid-btn-ghost text-[var(--text-small)]" @click="addField">
              <Plus :size="14" /> 添加字段
            </button>
          </div>
          <div class="space-y-4">
            <FieldEditor
              v-for="(field, i) in form.fields"
              :key="i"
              :model-value="form.fields[i]"
              @update:model-value="form.fields[i] = $event"
              @remove="form.fields.splice(i, 1)"
            />
            <p v-if="form.fields.length === 0" class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] text-center py-4">
              暂无字段，点击上方按钮添加
            </p>
          </div>
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
            class="liquid-input w-full resize-none"
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
import FieldEditor from '@/components/FieldEditor.vue'
import { templateApi, type Template, type Field } from '@/services/template'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const loading = ref(false)
const saving = ref(false)
const docTypeInput = ref('')

const isNew = computed(() => route.params.id === 'new')

const defaultField = (): Field => ({ key: '', label: '', type: 'text' })

const form = ref({
  name: '',
  doc_types: [] as string[],
  fields: [] as Field[],
  ai_prompt: null as string | null,
  ai_context: null as string | null,
  source_file_id: null as string | null,
})

function addDocType() {
  const val = docTypeInput.value.trim()
  if (val && !form.value.doc_types.includes(val)) {
    form.value.doc_types.push(val)
  }
  docTypeInput.value = ''
}

function addField() {
  form.value.fields.push(defaultField())
}

async function load(id: string) {
  loading.value = true
  try {
    const { data } = await templateApi.get(id)
    form.value.name = data.name
    form.value.doc_types = [...data.doc_types]
    form.value.fields = JSON.parse(JSON.stringify(data.fields))
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