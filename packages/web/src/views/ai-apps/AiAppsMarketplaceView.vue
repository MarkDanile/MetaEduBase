<template>
  <div class="ai-apps-marketplace">
    <div class="page-header">
      <h1 class="page-title">AI 应用广场</h1>
      <p class="page-desc">探索和使用已发布的 AI 应用</p>
    </div>

    <!-- 搜索和筛选 -->
    <div class="marketplace-controls">
      <div class="search-box">
        <Search :size="16" class="search-icon" />
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索应用..."
          class="search-input"
          @input="handleSearch"
        />
      </div>
      <div class="category-filter">
        <button
          v-for="cat in categories"
          :key="cat"
          class="category-btn"
          :class="{ 'category-btn-active': selectedCategory === cat }"
          @click="selectedCategory = cat"
        >
          {{ cat === '全部' ? '全部' : cat }}
        </button>
      </div>
    </div>

    <!-- 应用卡片列表 -->
    <div v-if="loading" class="loading-state">
      <div class="loading-skeleton-grid">
        <div v-for="i in 4" :key="i" class="skeleton-card"></div>
      </div>
    </div>
    <div v-else-if="filteredApps.length === 0" class="empty-state">
      <div class="empty-icon">🤖</div>
      <p class="empty-text">暂无应用</p>
      <p class="empty-hint">管理员发布应用后即可在这里看到</p>
    </div>
    <div v-else class="app-grid">
      <div
        v-for="app in filteredApps"
        :key="app.id"
        class="app-card"
        @click="goToDetail(app.code)"
      >
        <div class="app-card-icon">{{ app.icon || '🤖' }}</div>
        <div class="app-card-body">
          <h3 class="app-card-name">{{ app.name }}</h3>
          <p class="app-card-desc">{{ app.description || '暂无描述' }}</p>
          <div class="app-card-meta">
            <span class="app-card-category">{{ app.category || '未分类' }}</span>
            <span class="app-card-status" :class="`status-${app.status.toLowerCase()}`">
              {{ statusLabel(app.status) }}
            </span>
          </div>
        </div>
        <div class="app-card-action">
          <ArrowRight :size="16" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { Search, ArrowRight } from 'lucide-vue-next';
import { aiAppsApi, type AiAppPublic } from '@/services/aiAppsApi';

const router = useRouter();
const loading = ref(false);
const apps = ref<AiAppPublic[]>([]);
const searchKeyword = ref('');
const selectedCategory = ref('全部');

const categories = computed(() => {
  const cats = ['全部', ...new Set(apps.value.map(a => a.category).filter((c): c is string => Boolean(c)))];
  return cats;
});

const filteredApps = computed(() => {
  return apps.value.filter(app => {
    const matchKeyword = !searchKeyword.value ||
      app.name.toLowerCase().includes(searchKeyword.value.toLowerCase()) ||
      (app.description || '').toLowerCase().includes(searchKeyword.value.toLowerCase());
    const matchCategory = selectedCategory.value === '全部' || app.category === selectedCategory.value;
    return matchKeyword && matchCategory;
  });
});

function statusLabel(status: string) {
  const map: Record<string, string> = {
    Published: '可用',
    Draft: '规划中',
    Disabled: '已禁用',
    Archived: '已归档',
  };
  return map[status] || status;
}

function goToDetail(code: string) {
  router.push(`/ai-apps/${code}`);
}

function handleSearch() {
  // 搜索在 computed 中处理，无需额外逻辑
}

onMounted(async () => {
  loading.value = true;
  try {
    // BUG-018 AC-5: 公开应用广场走匿名 /public 端点，仅 Published+public+is_platform 子集。
    const res = await aiAppsApi.listPublic();
    apps.value = res.items || [];
  } catch (e) {
    console.error('加载应用列表失败', e);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.ai-apps-marketplace {
  padding: var(--spacing-page);
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--color-ink);
  margin: 0 0 4px;
}

.page-desc {
  font-size: 14px;
  color: var(--color-ink-tertiary);
  margin: 0;
}

.marketplace-controls {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
  align-items: center;
}

.search-box {
  position: relative;
  flex: 1;
  min-width: 200px;
  max-width: 320px;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-ink-tertiary);
}

.search-input {
  width: 100%;
  padding: 8px 12px 8px 36px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: 14px;
  background: var(--color-bg-base);
  color: var(--color-ink);
  outline: none;
  transition: border-color var(--duration-fast);
}

.search-input:focus {
  border-color: var(--color-accent);
}

.category-filter {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.category-btn {
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 13px;
  background: transparent;
  color: var(--color-ink-secondary);
  cursor: pointer;
  transition: all var(--duration-fast);
}

.category-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.category-btn-active {
  background: var(--color-accent-bg);
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.app-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  cursor: pointer;
  transition: all var(--duration-normal);
}

.app-card:hover {
  border-color: var(--color-accent);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-1px);
}

.app-card-icon {
  font-size: 32px;
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-accent-bg);
  border-radius: var(--radius-md);
}

.app-card-body {
  flex: 1;
  min-width: 0;
}

.app-card-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-ink);
  margin: 0 0 4px;
}

.app-card-desc {
  font-size: 13px;
  color: var(--color-ink-tertiary);
  margin: 0 0 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.app-card-meta {
  display: flex;
  gap: 8px;
  align-items: center;
}

.app-card-category {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--color-bg-base);
  color: var(--color-ink-tertiary);
  border: 1px solid var(--color-border-subtle);
}

.app-card-status {
  font-size: 11px;
  padding: 2px 8px;
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

.app-card-action {
  color: var(--color-ink-tertiary);
  flex-shrink: 0;
  margin-top: 4px;
}

.app-card:hover .app-card-action {
  color: var(--color-accent);
}

.loading-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.skeleton-card {
  height: 120px;
  background: linear-gradient(90deg, var(--color-bg-base) 25%, var(--color-bg-hover) 50%, var(--color-bg-base) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: var(--radius-lg);
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
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
  margin: 0 0 8px;
}

.empty-hint {
  font-size: 14px;
  color: var(--color-ink-tertiary);
  margin: 0;
}
</style>
