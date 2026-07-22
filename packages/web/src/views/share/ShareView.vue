<template>
  <div class="share-page">
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>正在加载应用...</p>
    </div>
    <div v-else-if="!app" class="error-state">
      <div class="error-icon">🔗</div>
      <h1>应用不存在或已下架</h1>
      <p>该分享链接已失效或应用已归档</p>
      <a href="/" class="back-link">返回首页</a>
    </div>
    <div v-else-if="app.status !== 'Published'" class="error-state">
      <div class="error-icon">🔒</div>
      <h1>应用暂未公开</h1>
      <p>该应用当前不对外开放</p>
      <a href="/" class="back-link">返回首页</a>
    </div>
    <div v-else class="share-content">
      <div class="share-icon">{{ app.icon || '🤖' }}</div>
      <h1 class="share-title">{{ app.name }}</h1>
      <p class="share-desc">{{ app.description || '暂无描述' }}</p>
      <div class="share-meta">
        <span v-if="app.category" class="meta-tag">{{ app.category }}</span>
        <span class="meta-tag">v{{ app.version }}</span>
      </div>
      <button class="open-btn" @click="router.push(app.route_path || '/')">
        <Rocket :size="18" /> 打开应用
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Rocket } from 'lucide-vue-next';
import { aiAppsApi, type AiAppPublic } from '@/services/aiAppsApi';

const route = useRoute();
const router = useRouter();
const loading = ref(true);
const app = ref<AiAppPublic | null>(null);

onMounted(async () => {
  const token = route.params.token as string;
  if (!token) {
    loading.value = false;
    return;
  }
  try {
    // BUG-018 Slice 4: 公开 share 端点按 token 直接查（不枚举 + 不暴露 share_token）。
    app.value = await aiAppsApi.getByShareToken(token);
  } catch {
    app.value = null;
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.share-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-page);
  background: var(--color-bg-base);
}

.loading-state,
.error-state,
.share-content {
  text-align: center;
  max-width: 480px;
}

.loading-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}

@keyframes spin { to { transform: rotate(360deg); } }

.error-icon,
.share-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.share-icon {
  width: 96px;
  height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-accent-bg);
  border-radius: var(--radius-xl);
  font-size: 48px;
  margin: 0 auto 20px;
}

h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-ink);
  margin: 0 0 12px;
}

.share-desc {
  font-size: 15px;
  color: var(--color-ink-secondary);
  line-height: 1.7;
  margin: 0 0 20px;
}

.share-meta {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-bottom: 28px;
}

.meta-tag {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 12px;
  background: var(--color-bg-elevated);
  color: var(--color-ink-tertiary);
  border: 1px solid var(--color-border-subtle);
}

.open-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 32px;
  background: var(--color-accent);
  color: white;
  border: none;
  border-radius: var(--radius-md);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast);
}

.open-btn:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

.back-link {
  display: inline-block;
  margin-top: 16px;
  color: var(--color-accent);
  text-decoration: none;
  font-size: 14px;
}
</style>
