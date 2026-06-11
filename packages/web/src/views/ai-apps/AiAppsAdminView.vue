<template>
  <div class="p-6">
    <PageHeader title="AI 应用管理" subtitle="配置和管理已注册的 AI 应用">
      <template #extra>
        <button class="ui-btn ui-btn-primary" @click="goToCreate">
          <Plus :size="14" /> 新建应用
        </button>
      </template>
    </PageHeader>

    <!-- 状态筛选 -->
    <div class="filter-tabs">
      <button
        v-for="tab in statusTabs"
        :key="tab.value"
        class="filter-tab"
        :class="{ 'filter-tab-active': currentTab === tab.value }"
        @click="currentTab = tab.value"
      >
        {{ tab.label }}
        <span class="tab-count">{{ countByStatus(tab.value) }}</span>
      </button>
    </div>

    <div class="mt-4">
      <LoadingSpinner v-if="loading" text="加载应用..." />
      <EmptyState
        v-else-if="filteredApps.length === 0"
        title="暂无应用"
        hint="点击右上角「新建应用」创建第一个 AI 应用"
      />
      <div v-else class="app-list-container">
        <!-- Header -->
        <div class="list-header">
          <div class="col-icon"></div>
          <div class="col-name">应用名称</div>
          <div class="col-code">编号</div>
          <div class="col-category">分类</div>
          <div class="col-status">状态</div>
          <div class="col-date">更新时间</div>
          <div class="col-ops">操作</div>
        </div>

        <!-- Rows -->
        <div
          v-for="app in filteredApps"
          :key="app.id"
          class="list-row"
        >
          <div class="col-icon">
            <span class="app-icon">{{ app.icon || '🤖' }}</span>
          </div>
          <div class="col-name">
            <span class="row-name">{{ app.name }}</span>
            <span v-if="app.route_path" class="row-route">{{ app.route_path }}</span>
          </div>
          <div class="col-code">
            <span class="code-badge">{{ app.code }}</span>
          </div>
          <div class="col-category">
            <span v-if="app.category" class="category-tag">{{ app.category }}</span>
            <span v-else class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">—</span>
          </div>
          <div class="col-status">
            <span class="status-badge" :class="`status-${app.status.toLowerCase()}`">
              {{ statusLabel(app.status) }}
            </span>
          </div>
          <div class="col-date">
            <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">{{ formatDate(app.updated_at) }}</span>
          </div>
          <div class="col-ops" @click.stop>
            <button class="op-btn" @click="goToEdit(app.id)" title="编辑">
              <Pencil :size="14" />
            </button>
            <button
              v-if="app.status === 'Draft'"
              class="op-btn"
              @click="doPublish(app)"
              title="发布"
            >
              <Rocket :size="14" />
            </button>
            <button
              v-if="app.status === 'Published'"
              class="op-btn"
              @click="doDisable(app)"
              title="禁用"
            >
              <Ban :size="14" />
            </button>
            <button
              v-if="app.status === 'Disabled'"
              class="op-btn"
              @click="doEnable(app)"
              title="启用"
            >
              <CheckCircle :size="14" />
            </button>
            <button class="op-btn danger" @click="confirmArchive(app)" title="归档">
              <Archive :size="14" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 归档确认 -->
    <ConfirmDialog
      v-model:open="showArchiveConfirm"
      title="归档应用"
      :message="`确定归档应用「${archiveTarget?.name}」？归档后将不在广场展示，但数据会保留。`"
      danger
      @confirm="doArchive"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { Plus, Pencil, Rocket, Ban, CheckCircle, Archive } from 'lucide-vue-next';
import PageHeader from '@/components/PageHeader.vue';
import EmptyState from '@/components/EmptyState.vue';
import LoadingSpinner from '@/components/LoadingSpinner.vue';
import ConfirmDialog from '@/components/ConfirmDialog.vue';
import { aiAppsApi, type AiAppResponse } from '@/services/aiAppsApi';
import { useToast } from '@/composables/useToast';

const router = useRouter();
const toast = useToast();

const loading = ref(false);
const apps = ref<AiAppResponse[]>([]);
const currentTab = ref('all');
const showArchiveConfirm = ref(false);
const archiveTarget = ref<AiAppResponse | null>(null);

const statusTabs = [
  { value: 'all', label: '全部' },
  { value: 'Published', label: '已发布' },
  { value: 'Draft', label: '草稿' },
  { value: 'Disabled', label: '已禁用' },
  { value: 'Archived', label: '已归档' },
];

const filteredApps = computed(() => {
  if (currentTab.value === 'all') return apps.value;
  return apps.value.filter(a => a.status === currentTab.value);
});

function countByStatus(status: string): number {
  if (status === 'all') return apps.value.length;
  return apps.value.filter(a => a.status === status).length;
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    Published: '已发布',
    Draft: '草稿',
    Disabled: '已禁用',
    Archived: '已归档',
  };
  return map[status] || status;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

function goToCreate() {
  router.push('/ai-apps/admin/create');
}

function goToEdit(id: string) {
  router.push(`/ai-apps/admin/${id}`);
}

async function loadApps() {
  loading.value = true;
  try {
    const res = await aiAppsApi.list({ include_archived: true });
    apps.value = res.items || [];
  } catch {
    toast.error('加载应用列表失败');
  } finally {
    loading.value = false;
  }
}

async function doPublish(app: AiAppResponse) {
  try {
    await aiAppsApi.publish(app.id);
    toast.success('应用已发布');
    await loadApps();
  } catch {
    toast.error('发布失败');
  }
}

async function doDisable(app: AiAppResponse) {
  try {
    await aiAppsApi.disable(app.id);
    toast.success('应用已禁用');
    await loadApps();
  } catch {
    toast.error('禁用失败');
  }
}

async function doEnable(app: AiAppResponse) {
  try {
    await aiAppsApi.enable(app.id);
    toast.success('应用已启用');
    await loadApps();
  } catch {
    toast.error('启用失败');
  }
}

function confirmArchive(app: AiAppResponse) {
  archiveTarget.value = app;
  showArchiveConfirm.value = true;
}

async function doArchive() {
  if (!archiveTarget.value) return;
  try {
    await aiAppsApi.archive(archiveTarget.value.id);
    toast.success('应用已归档');
    showArchiveConfirm.value = false;
    archiveTarget.value = null;
    await loadApps();
  } catch {
    toast.error('归档失败');
  }
}

onMounted(loadApps);
</script>

<style scoped>
.filter-tabs {
  display: flex;
  gap: 4px;
  margin-top: 16px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 0;
}

.filter-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: var(--color-ink-secondary);
  font-size: 14px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all var(--duration-fast);
}

.filter-tab:hover {
  color: var(--color-ink);
}

.filter-tab-active {
  color: var(--color-accent);
  border-bottom-color: var(--color-accent);
}

.tab-count {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 10px;
  background: var(--color-bg-base);
  color: var(--color-ink-tertiary);
}

.filter-tab-active .tab-count {
  background: var(--color-accent-bg);
  color: var(--color-accent);
}

.app-list-container {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.list-header {
  display: grid;
  grid-template-columns: 48px 2fr 1fr 1fr 80px 100px 140px;
  gap: 8px;
  padding: 10px 16px;
  background: var(--color-bg-base);
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
  font-weight: 600;
  color: var(--color-ink-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.list-row {
  display: grid;
  grid-template-columns: 48px 2fr 1fr 1fr 80px 100px 140px;
  gap: 8px;
  padding: 12px 16px;
  align-items: center;
  border-bottom: 1px solid var(--color-border-subtle);
  transition: background var(--duration-fast);
  cursor: pointer;
}

.list-row:last-child {
  border-bottom: none;
}

.list-row:hover {
  background: var(--color-bg-hover);
}

.app-icon {
  font-size: 24px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-base);
  border-radius: var(--radius-md);
}

.row-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink);
  display: block;
}

.row-route {
  font-size: 12px;
  color: var(--color-ink-tertiary);
  display: block;
  margin-top: 2px;
  font-family: monospace;
}

.code-badge {
  font-size: 12px;
  font-family: monospace;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--color-bg-base);
  color: var(--color-ink-secondary);
  border: 1px solid var(--color-border-subtle);
}

.category-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--color-bg-base);
  color: var(--color-ink-tertiary);
  border: 1px solid var(--color-border-subtle);
}

.status-badge {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 10px;
  font-weight: 500;
}

.status-published {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.status-draft {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.status-disabled {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
}

.status-archived {
  background: rgba(156, 163, 175, 0.1);
  color: #9ca3af;
}

.col-ops {
  display: flex;
  gap: 4px;
  align-items: center;
}

.op-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  background: transparent;
  border-radius: var(--radius-md);
  color: var(--color-ink-tertiary);
  cursor: pointer;
  transition: all var(--duration-fast);
}

.op-btn:hover {
  background: var(--color-bg-base);
  color: var(--color-ink);
}

.op-btn.danger:hover {
  background: rgba(239, 68, 68, 0.08);
  color: var(--color-danger);
}
</style>
