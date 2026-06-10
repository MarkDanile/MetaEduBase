<template>
  <div class="version-panel">
    <div class="version-header">
      <h3 class="text-[var(--text-subtitle)] font-semibold text-[var(--color-ink)]">版本历史</h3>
    </div>
    <LoadingSpinner v-if="loading" text="加载版本..." />
    <div v-else-if="versions.length === 0" class="text-[var(--text-small)] text-[var(--color-ink-tertiary)] py-4 text-center">
      暂无版本
    </div>
    <ul v-else class="version-list">
      <li v-for="v in versions" :key="v.version_number" class="version-item">
        <div class="version-info">
          <span class="version-number">v{{ v.version_number }}</span>
          <span class="version-date">{{ formatDate(v.snapshot_at) }}</span>
          <span class="version-name">{{ v.name }}</span>
        </div>
        <button class="ui-btn ui-btn-ghost text-[var(--text-small)]" @click="onRollback(v.version_number)">
          <RotateCcw :size="12" />
          回滚
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { RotateCcw } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { templateApi, type TemplateVersion } from '@/services/template'
import LoadingSpinner from '@/components/LoadingSpinner.vue'

const props = defineProps<{ templateId: string }>()
const emit = defineEmits<{ 'rolled-back': [] }>()

const toast = useToast()
const versions = ref<TemplateVersion[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await templateApi.listVersions(props.templateId, 20, 0)
    versions.value = data
  } catch {
    toast.error('加载版本失败')
  } finally {
    loading.value = false
  }
}

async function onRollback(n: number) {
  if (!confirm(`确认回滚到 v${n}？当前未保存修改将丢失`)) return
  try {
    await templateApi.rollback(props.templateId, n)
    toast.success('已回滚')
    emit('rolled-back')
    await load()
  } catch {
    toast.error('回滚失败')
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
watch(() => props.templateId, load)
</script>

<style scoped>
.version-panel {
  background: white;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-lg);
  padding: 16px;
  margin-top: 12px;
}

.version-header {
  margin-bottom: 12px;
}

.version-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.version-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 8px;
  transition: background 0.1s;
}

.version-item:hover {
  background: var(--interactive-hover-bg);
}

.version-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.version-number {
  font-size: var(--text-small);
  font-weight: 600;
  color: var(--color-accent);
  font-family: monospace;
}

.version-date {
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
}

.version-name {
  font-size: var(--text-small);
  color: var(--color-ink);
}
</style>
