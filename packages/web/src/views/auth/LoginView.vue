<template>
  <div class="login-page">
    <div class="brand-side">
      <div class="brand-bg">
        <div class="brand-orb brand-orb-1"></div>
        <div class="brand-orb brand-orb-2"></div>
        <div class="brand-orb brand-orb-3"></div>
        <svg class="brand-grid" width="100%" height="100%" viewBox="0 0 600 900" fill="none" preserveAspectRatio="xMidYMid slice">
          <g opacity="0.06">
            <line x1="0" y1="120" x2="600" y2="120" stroke="#fff" stroke-width="0.5"/>
            <line x1="0" y1="240" x2="600" y2="240" stroke="#fff" stroke-width="0.5"/>
            <line x1="0" y1="360" x2="600" y2="360" stroke="#fff" stroke-width="0.5"/>
            <line x1="0" y1="480" x2="600" y2="480" stroke="#fff" stroke-width="0.5"/>
            <line x1="0" y1="600" x2="600" y2="600" stroke="#fff" stroke-width="0.5"/>
            <line x1="0" y1="720" x2="600" y2="720" stroke="#fff" stroke-width="0.5"/>
          </g>
          <g opacity="0.04">
            <circle cx="60" cy="60" r="3" fill="#fff"/>
            <circle cx="300" cy="180" r="4" fill="#fff"/>
            <circle cx="480" cy="120" r="2.5" fill="#fff"/>
            <circle cx="150" cy="300" r="3.5" fill="#fff"/>
            <circle cx="420" cy="360" r="3" fill="#fff"/>
            <circle cx="540" cy="420" r="2" fill="#fff"/>
            <circle cx="90" cy="540" r="4" fill="#fff"/>
            <circle cx="360" cy="600" r="3" fill="#fff"/>
            <circle cx="510" cy="660" r="2.5" fill="#fff"/>
            <circle cx="240" cy="780" r="3" fill="#fff"/>
            <circle cx="450" cy="800" r="2" fill="#fff"/>
            <line x1="60" y1="60" x2="300" y2="180" stroke="#fff" stroke-width="0.4"/>
            <line x1="300" y1="180" x2="480" y2="120" stroke="#fff" stroke-width="0.4"/>
            <line x1="150" y1="300" x2="420" y2="360" stroke="#fff" stroke-width="0.4"/>
            <line x1="420" y1="360" x2="540" y2="420" stroke="#fff" stroke-width="0.4"/>
            <line x1="90" y1="540" x2="360" y2="600" stroke="#fff" stroke-width="0.4"/>
            <line x1="360" y1="600" x2="510" y2="660" stroke="#fff" stroke-width="0.4"/>
            <line x1="510" y1="660" x2="450" y2="800" stroke="#fff" stroke-width="0.3"/>
            <line x1="480" y1="120" x2="420" y2="360" stroke="#fff" stroke-width="0.3"/>
            <line x1="540" y1="420" x2="360" y2="600" stroke="#fff" stroke-width="0.3"/>
          </g>
        </svg>
      </div>
      <div class="brand-content">
        <div class="brand-logo">
          <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
            <rect x="1" y="1" width="54" height="54" rx="14" fill="rgba(255,255,255,0.15)"/>
            <rect x="1" y="1" width="54" height="54" rx="14" stroke="rgba(255,255,255,0.25)" stroke-width="1"/>
            <text x="28" y="38" text-anchor="middle" fill="#fff" font-size="26" font-weight="700" font-family="system-ui, sans-serif">元</text>
          </svg>
        </div>

        <h1 class="brand-title">元知职教基座</h1>
        <p class="brand-subtitle">AI Native · 职业教育知识基座</p>

        <div class="brand-divider"></div>

        <p class="brand-desc">面向职业院校的一体化知识管理平台，深度融合 RAG 检索增强与层级知识图谱</p>

        <div class="brand-features">
          <div class="feature-item">
            <span class="feature-icon">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="7" stroke="rgba(255,255,255,0.5)" stroke-width="1"/><path d="M5.5 8h5M8 5.5v5" stroke="rgba(255,255,255,0.5)" stroke-width="1" stroke-linecap="round"/></svg>
            </span>
            <span>RAG 检索增强生成</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="3.5" r="2.5" stroke="rgba(255,255,255,0.5)" stroke-width="1"/><circle cx="3" cy="12.5" r="2.5" stroke="rgba(255,255,255,0.5)" stroke-width="1"/><circle cx="13" cy="12.5" r="2.5" stroke="rgba(255,255,255,0.5)" stroke-width="1"/><line x1="7" y1="5.8" x2="4.2" y2="10.5" stroke="rgba(255,255,255,0.3)" stroke-width="0.8"/><line x1="9" y1="5.8" x2="11.8" y2="10.5" stroke="rgba(255,255,255,0.3)" stroke-width="0.8"/></svg>
            </span>
            <span>层级知识图谱</span>
          </div>
          <div class="feature-item">
            <span class="feature-icon">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><rect x="1" y="1" width="14" height="14" rx="3" stroke="rgba(255,255,255,0.5)" stroke-width="1"/><rect x="4.5" y="4.5" width="7" height="7" rx="1.5" stroke="rgba(255,255,255,0.4)" stroke-width="0.8"/></svg>
            </span>
            <span>多租户安全隔离</span>
          </div>
        </div>

        <div class="brand-footer">
          <span>PostgreSQL 16</span>
          <span class="footer-dot">·</span>
          <span>pgvector</span>
          <span class="footer-dot">·</span>
          <span>FastAPI</span>
        </div>
      </div>
    </div>

    <div class="login-side">
      <div class="login-card">
        <h2 class="login-heading">欢迎登录</h2>

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
import { authApi } from "@/services/auth";

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

.brand-orb-3 {
  width: 250px;
  height: 250px;
  background: rgba(59, 130, 246, 0.12);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.brand-grid {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.brand-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 56px 56px;
  max-width: 480px;
}

.brand-logo {
  margin-bottom: 16px;
}

.brand-logo svg {
  filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.12));
}

.brand-title {
  font-size: 26px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.05em;
  line-height: 1.3;
}

.brand-subtitle {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.7);
  letter-spacing: 0.08em;
  margin-top: 6px;
}

.brand-divider {
  width: 48px;
  height: 2px;
  border-radius: 1px;
  background: rgba(255, 255, 255, 0.35);
  margin: 18px 0 16px;
}

.brand-desc {
  font-size: 14px;
  line-height: 1.8;
  color: rgba(255, 255, 255, 0.7);
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 24px;
  width: 100%;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 14px;
  color: rgba(255, 255, 255, 0.7);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 12px 16px;
}

.feature-icon {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 24px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
  letter-spacing: 0.05em;
}

.footer-dot {
  opacity: 0.4;
}

.login-side {
  flex: 1 1 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    linear-gradient(135deg, #F8FAFC 0%, #F1F5F9 50%, #F8FAFC 100%);
  position: relative;
}

.login-side::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(59, 130, 246, 0.03) 1px, transparent 1px);
  background-size: 20px 20px;
  pointer-events: none;
}

.login-card {
  position: relative;
  width: 100%;
  max-width: 400px;
  background: #fff;
  border: 1px solid rgba(59, 130, 246, 0.08);
  border-radius: 16px;
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.04),
    0 8px 24px rgba(0, 0, 0, 0.04),
    0 16px 48px rgba(59, 130, 246, 0.04);
  padding: 40px 36px;
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
    padding: 24px 24px;
    max-width: 100%;
  }

  .brand-title { font-size: 22px; }
  .brand-subtitle { font-size: 13px; }
  .brand-desc { font-size: 13px; }
  .brand-features { gap: 8px; margin-top: 18px; }
  .feature-item { padding: 10px 14px; font-size: 13px; }
  .brand-footer { margin-top: 18px; }

  .login-side {
    flex: 1 1 auto;
    padding: 24px 28px 48px;
  }

  .login-card {
    max-width: 100%;
    padding: 32px 28px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .flow-line-bar { animation: none; }
}
</style>
