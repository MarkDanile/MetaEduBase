<template>
  <div class="ai-app-detail">
    <button class="back-btn" @click="router.push('/ai-apps')">
      <ArrowLeft :size="16" /> 返回广场
    </button>

    <div v-if="loading" class="loading-state">
      <div class="skeleton-header"></div>
      <div class="skeleton-body"></div>
    </div>

    <div v-else-if="!app" class="empty-state">
      <div class="empty-icon">🔍</div>
      <p class="empty-text">应用不存在或已下架</p>
      <button class="btn-primary" @click="router.push('/ai-apps')">返回广场</button>
    </div>

    <template v-else>
      <div class="detail-header">
        <div class="detail-icon">{{ app.icon || '🤖' }}</div>
        <div class="detail-title">
          <div class="detail-status-row">
            <h1 class="detail-name">{{ app.name }}</h1>
            <span class="detail-status-badge" :class="`status-${app.status.toLowerCase()}`">
              {{ statusLabel(app.status) }}
            </span>
          </div>
          <p class="detail-desc">{{ app.description || '暂无描述' }}</p>
          <div class="detail-meta">
            <span v-if="app.category" class="meta-tag">{{ app.category }}</span>
            <span v-if="app.version" class="meta-tag">v{{ app.version }}</span>
          </div>
        </div>
      </div>

      <div class="detail-actions">
        <button
          v-if="app.status === 'Published' && app.route_path"
          class="btn-primary btn-lg"
          @click="router.push(app.route_path)"
        >
          <Rocket :size="18" /> 立即使用
        </button>
        <button
          v-else-if="app.status === 'Draft'"
          class="btn-disabled btn-lg"
          disabled
        >
          🚧 规划中，暂未开放
        </button>
        <button
          v-else-if="app.status === 'Disabled'"
          class="btn-disabled btn-lg"
          disabled
        >
          ⏸️ 该应用已禁用
        </button>
      </div>

      <div v-if="app.required_capabilities && app.required_capabilities.length" class="detail-section">
        <h3 class="section-title">所需底座能力</h3>
        <div class="capabilities-list">
          <span v-for="cap in app.required_capabilities" :key="cap" class="capability-tag">
            {{ cap }}
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ArrowLeft, Rocket } from 'lucide-vue-next';
import { aiAppsApi, type AiAppPublic } from '@/services/aiAppsApi';

const route = useRoute();
const router = useRouter();
const loading = ref(false);
const app = ref<AiAppPublic | null>(null);

function statusLabel(status: string) {
  const map: Record<string, string> = {
    Published: '可用',
    Draft: '规划中',
    Disabled: '已禁用',
    Archived: '已归档',
  };
  return map[status] || status;
}

onMounted(async () => {
  const code = route.params.code as string;
  if (!code) {
    router.push('/ai-apps');
    return;
  }
  loading.value = true;
  try {
    const apps = await aiAppsApi.list({});
    app.value = apps.items?.find((a: AiAppPublic) => a.code === code) || null;
  } catch (e) {
    console.error('加载应用详情失败', e);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.ai-app-detail {
  padding: var(--spacing-page);
  max-width: 800px;
  margin: 0 auto;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  background: transparent;
  color: var(--color-ink-secondary);
  font-size: 14px;
  cursor: pointer;
  border-radius: var(--radius-md);
  margin-bottom: 20px;
  transition: all var(--duration-fast);
}

.back-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-ink);
}

.detail-header {
  display: flex;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 24px;
}

.detail-icon {
  font-size: 56px;
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-accent-bg);
  border-radius: var(--radius-lg);
  flex-shrink: 0;
}

.detail-title {
  flex: 1;
}

.detail-status-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.detail-name {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-ink);
  margin: 0;
}

.detail-status-badge {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 10px;
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

.detail-desc {
  font-size: 15px;
  color: var(--color-ink-secondary);
  margin: 0 0 12px;
  line-height: 1.6;
}

.detail-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-tag {
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 10px;
  background: var(--color-bg-base);
  color: var(--color-ink-tertiary);
  border: 1px solid var(--color-border-subtle);
}

.detail-actions {
  margin-bottom: 32px;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  background: var(--color-accent);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast);
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-lg {
  padding: 12px 28px;
  font-size: 15px;
}

.btn-disabled {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  background: var(--color-bg-base);
  color: var(--color-ink-tertiary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 15px;
  cursor: not-allowed;
}

.detail-section {
  border-top: 1px solid var(--color-border);
  padding-top: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-ink);
  margin: 0 0 12px;
}

.capabilities-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.capability-tag {
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 12px;
  background: var(--color-accent-bg);
  color: var(--color-accent);
  border: 1px solid var(--color-accent-subtle);
}

.loading-state {
  padding: 20px 0;
}

.skeleton-header {
  height: 100px;
  background: var(--color-bg-base);
  border-radius: var(--radius-lg);
  margin-bottom: 16px;
  animation: shimmer 1.5s infinite;
}

.skeleton-body {
  height: 60px;
  background: var(--color-bg-base);
  border-radius: var(--radius-lg);
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-ink);
  margin: 0 0 20px;
}
</style>
