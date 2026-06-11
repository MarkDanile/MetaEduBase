<template>
  <div class="admin-placeholder">
    <div class="placeholder-icon">⚙️</div>
    <h1 class="placeholder-title">AI 应用管理</h1>
    <p class="placeholder-desc">管理已注册的应用、配置和发布状态</p>
    <div class="placeholder-badge">
      <span class="badge-dot"></span>
      功能开发中
    </div>
    <p class="placeholder-hint">Slice 3 将实现完整的应用管理功能</p>
  </div>
</template>

<style scoped>
.admin-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: var(--spacing-page);
  text-align: center;
}
.placeholder-icon { font-size: 64px; margin-bottom: 20px; }
.placeholder-title { font-size: 24px; font-weight: 700; color: var(--color-ink); margin: 0 0 10px; }
.placeholder-desc { font-size: 15px; color: var(--color-ink-secondary); margin: 0 0 20px; }
.placeholder-badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 16px; border-radius: 20px;
  background: var(--color-accent-bg); color: var(--color-accent);
  font-size: 13px; font-weight: 500; margin-bottom: 12px;
}
.badge-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--color-accent); animation: pulse 2s infinite; }
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }
.placeholder-hint { font-size: 13px; color: var(--color-ink-tertiary); margin: 0; }
</style>
