<template>
  <div class="app-placeholder">
    <div class="placeholder-icon">{{ icon }}</div>
    <h1 class="placeholder-title">{{ title }}</h1>
    <p class="placeholder-desc">{{ desc }}</p>
    <div class="placeholder-badge">
      <span class="badge-dot"></span>
      功能开发中
    </div>
    <p class="placeholder-hint">该应用正在积极开发中，敬请期待</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const route = useRoute();

const appMap: Record<string, { icon: string; title: string; desc: string }> = {
  '/apps/course-capability-map': {
    icon: '🗺️',
    title: '课程能力图谱',
    desc: '自动构建、动态管理与智能应用课程能力图谱，支撑个性化学习路径规划和资源推荐。',
  },
  '/apps/preview-guide': {
    icon: '📚',
    title: '智能预习导学',
    desc: '基于课程能力图谱与学生学情，智能规划预习任务、推送预习资源、诊断预习效果。',
  },
  '/apps/resource-recommendation': {
    icon: '🎯',
    title: '个性化资源推荐',
    desc: '基于学生画像与学习情境实现精准资源匹配与智能推送，提升学习资源利用效率。',
  },
  '/apps/review-planner': {
    icon: '🧠',
    title: '智能复习巩固',
    desc: '基于遗忘曲线与学习记录，智能规划复习任务、推送巩固内容，实现高效巩固。',
  },
};

const info = computed(() => appMap[route.path] || { icon: '🤖', title: 'AI 应用', desc: '' });
const icon = computed(() => info.value.icon);
const title = computed(() => info.value.title);
const desc = computed(() => info.value.desc);
</script>

<style scoped>
.app-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: var(--spacing-page);
  text-align: center;
}

.placeholder-icon {
  font-size: 72px;
  margin-bottom: 24px;
  filter: grayscale(0.3);
}

.placeholder-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-ink);
  margin: 0 0 12px;
}

.placeholder-desc {
  font-size: 15px;
  color: var(--color-ink-secondary);
  max-width: 480px;
  line-height: 1.7;
  margin: 0 0 24px;
}

.placeholder-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  border-radius: 20px;
  background: var(--color-accent-bg);
  color: var(--color-accent);
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 16px;
}

.badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-accent);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.placeholder-hint {
  font-size: 13px;
  color: var(--color-ink-tertiary);
  margin: 0;
}
</style>
