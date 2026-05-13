<template>
  <div class="login-page">
    <div class="brand-side">
      <div class="brand-bg">
        <div class="brand-orb brand-orb-1"></div>
        <div class="brand-orb brand-orb-2"></div>
      </div>
      <div class="brand-content">
        <div class="brand-logo">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
            <rect x="1.5" y="1.5" width="61" height="61" rx="16" fill="rgba(255,255,255,0.15)"/>
            <rect x="1.5" y="1.5" width="61" height="61" rx="16" stroke="rgba(255,255,255,0.25)" stroke-width="1.5"/>
            <text x="32" y="43" text-anchor="middle" fill="#fff" font-size="30" font-weight="700" font-family="system-ui, sans-serif">元</text>
          </svg>
        </div>

        <h1 class="brand-title">元知职教基座</h1>
        <p class="brand-subtitle">AI Native 职业教育知识基座</p>

        <div class="brand-divider"></div>

        <p class="brand-desc">
          面向职业院校的一体化知识管理平台<br/>深度融合 RAG 检索增强与层级知识图谱
        </p>

        <div class="brand-features">
          <div class="feature-item">
            <span class="feature-icon">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="rgba(255,255,255,0.6)" stroke-width="1"/><path d="M5 7h4M7 5v4" stroke="rgba(255,255,255,0.6)" stroke-width="1" stroke-linecap="round"/></svg>
            </span>
            RAG 检索增强生成
          </div>
          <div class="feature-item">
            <span class="feature-icon">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="3" r="2" stroke="rgba(255,255,255,0.6)" stroke-width="1"/><circle cx="3" cy="11" r="2" stroke="rgba(255,255,255,0.6)" stroke-width="1"/><circle cx="11" cy="11" r="2" stroke="rgba(255,255,255,0.6)" stroke-width="1"/><line x1="7" y1="5" x2="4" y2="9.5" stroke="rgba(255,255,255,0.35)" stroke-width="0.8"/><line x1="7" y1="5" x2="10" y2="9.5" stroke="rgba(255,255,255,0.35)" stroke-width="0.8"/></svg>
            </span>
            层级知识图谱
          </div>
          <div class="feature-item">
            <span class="feature-icon">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="1" width="12" height="12" rx="3" stroke="rgba(255,255,255,0.6)" stroke-width="1"/><rect x="4" y="4" width="6" height="6" rx="1.5" stroke="rgba(255,255,255,0.5)" stroke-width="0.8"/></svg>
            </span>
            多租户隔离
          </div>
        </div>
      </div>
    </div>

    <div class="login-side">
      <div class="login-form-wrap">
        <h2 class="login-heading">登录</h2>

        <form @submit.prevent="handleLogin" class="space-y-4">
          <div class="input-group">
            <label class="input-label">用户名</label>
            <input
              v-model="form.username"
              type="text"
              class="liquid-input"
              placeholder="请输入用户名"
              required
            />
          </div>
          <div class="input-group">
            <label class="input-label">密码</label>
            <input
              v-model="form.password"
              type="password"
              class="liquid-input"
              placeholder="请输入密码"
              required
            />
          </div>

          <transition name="error-fade">
            <p v-if="error" class="error-msg">{{ error }}</p>
          </transition>

          <button
            type="submit"
            :disabled="loading"
            class="liquid-btn liquid-btn-primary w-full login-btn"
          >
            <template v-if="loading">
              <div class="flow-line">
                <div class="flow-line-bar"></div>
              </div>
              验证中
            </template>
            <template v-else>登 录</template>
          </button>
        </form>

        <p class="login-hint">默认账号: admin / admin123</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/services/knowledge";

const router = useRouter();
const authStore = useAuthStore();

const form = reactive({ username: "", password: "" });
const loading = ref(false);
const error = ref("");

async function handleLogin() {
  error.value = "";
  loading.value = true;
  try {
    const { data } = await authApi.login(form);
    authStore.setAuth(data.access_token, data.tenant_id, data.role, data.domain ?? undefined);
    router.push("/");
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } };
    error.value = err.response?.data?.detail ?? "登录失败，请检查用户名和密码";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
}

.brand-side {
  flex: 0 0 50%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #1E3A5F 0%, #1E40AF 30%, #2563EB 60%, #3B82F6 100%);
  overflow: hidden;
}

.brand-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.brand-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
}

.brand-orb-1 {
  width: 400px;
  height: 400px;
  background: rgba(96, 165, 250, 0.2);
  top: -120px;
  right: -100px;
}

.brand-orb-2 {
  width: 300px;
  height: 300px;
  background: rgba(147, 197, 253, 0.15);
  bottom: -80px;
  left: -80px;
}

.brand-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 64px 48px;
  max-width: 380px;
}

.brand-logo {
  margin-bottom: 20px;
}

.brand-logo svg {
  filter: drop-shadow(0 4px 16px rgba(0, 0, 0, 0.15));
}

.brand-title {
  font-size: 28px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.04em;
  line-height: 1.3;
}

.brand-subtitle {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.6);
  letter-spacing: 0.06em;
  margin-top: 6px;
}

.brand-divider {
  width: 40px;
  height: 3px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.3);
  margin: 20px 0;
}

.brand-desc {
  font-size: 13px;
  line-height: 1.9;
  color: rgba(255, 255, 255, 0.5);
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 28px;
  width: 100%;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 10px 14px;
}

.feature-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-side {
  flex: 1 1 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #F8FAFC;
}

.login-form-wrap {
  width: 100%;
  max-width: 360px;
  padding: 0 48px;
}

.login-heading {
  font-size: 22px;
  font-weight: 700;
  color: #1E3A5F;
  text-align: center;
  margin-bottom: 28px;
  letter-spacing: 0.04em;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  padding-left: 2px;
}

.error-msg {
  font-size: 13px;
  color: var(--color-danger);
  background: rgba(239, 68, 68, 0.04);
  padding: 8px 12px;
  border-radius: var(--radius-md);
}

.login-btn {
  height: 44px;
  font-size: 16px;
  margin-top: 4px;
}

.login-btn:hover {
  transform: scale(1.01);
}

.login-hint {
  font-size: 12px;
  color: #94A3B8;
  text-align: center;
  margin-top: 24px;
}

.flow-line {
  width: 28px;
  height: 2.5px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.flow-line-bar {
  width: 10px;
  height: 100%;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 2px;
  animation: flow-slide 1.6s ease-in-out infinite;
}

@keyframes flow-slide {
  0% { transform: translateX(0); }
  30% { transform: translateX(8px); }
  50% { transform: translateX(16px); }
  70% { transform: translateX(4px); }
  100% { transform: translateX(0); }
}

.error-fade-enter-active { transition: all var(--duration-normal) var(--ease-out); }
.error-fade-leave-active { transition: all var(--duration-fast) var(--ease-out); }
.error-fade-enter-from,
.error-fade-leave-to { opacity: 0; transform: translateY(-4px); }

@media (max-width: 720px) {
  .login-page {
    flex-direction: column;
  }

  .brand-side {
    flex: 0 0 auto;
    padding: 40px 28px;
  }

  .brand-content {
    padding: 24px 16px;
  }

  .brand-title { font-size: 24px; }
  .brand-subtitle { font-size: 13px; }
  .brand-desc { font-size: 12px; }
  .brand-features { gap: 8px; margin-top: 20px; }

  .login-side {
    flex: 1 1 auto;
    padding: 32px 28px 48px;
    align-items: flex-start;
  }

  .login-form-wrap {
    max-width: 100%;
    padding: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .flow-line-bar { animation: none; }
}
</style>
