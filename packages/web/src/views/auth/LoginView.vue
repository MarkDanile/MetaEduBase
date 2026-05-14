<template>
  <div class="login-page">
    <div class="brand-side">
      <div class="brand-noise"></div>
      <div class="brand-content">
        <div class="brand-logo">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <rect x="1" y="1" width="46" height="46" rx="12" fill="rgba(255,255,255,0.12)"/>
            <rect x="1" y="1" width="46" height="46" rx="12" stroke="rgba(255,255,255,0.2)" stroke-width="1"/>
            <text x="24" y="33" text-anchor="middle" fill="#fff" font-size="22" font-weight="700" font-family="system-ui, sans-serif">元</text>
          </svg>
        </div>
        <h1 class="brand-title">元知职教基座</h1>
        <p class="brand-subtitle">AI Native · 职业教育知识基座</p>
      </div>
    </div>

    <div class="login-side">
      <div class="login-card liquid-card">
        <h2 class="login-heading">欢迎回来</h2>

        <form @submit.prevent="handleLogin" class="login-form">
          <div class="input-group">
            <label class="input-label">用户名</label>
            <div class="input-wrapper">
              <User :size="18" :stroke-width="1.5" class="input-icon" />
              <input
                v-model="form.username"
                type="text"
                class="liquid-input has-left-icon"
                placeholder="请输入用户名"
                required
              />
            </div>
          </div>

          <div class="input-group">
            <label class="input-label">密码</label>
            <div class="input-wrapper">
              <Lock :size="18" :stroke-width="1.5" class="input-icon" />
              <input
                v-model="form.password"
                :type="showPassword ? 'text' : 'password'"
                class="liquid-input has-left-icon has-right-icon"
                placeholder="请输入密码"
                required
              />
              <button
                type="button"
                class="password-toggle"
                @click="showPassword = !showPassword"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              >
                <EyeOff v-if="showPassword" :size="18" :stroke-width="1.5" />
                <Eye v-else :size="18" :stroke-width="1.5" />
              </button>
            </div>
          </div>

          <transition name="error-fade">
            <p v-if="error" class="error-msg">{{ error }}</p>
          </transition>

          <button
            type="submit"
            :disabled="loading"
            class="liquid-btn liquid-btn-primary submit-btn"
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
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from "vue";
import { useRouter } from "vue-router";
import { User, Lock, Eye, EyeOff } from "lucide-vue-next";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/services/auth";

const router = useRouter();
const authStore = useAuthStore();

const form = reactive({ username: "", password: "" });
const loading = ref(false);
const error = ref("");
const showPassword = ref(false);

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

/* ===== 品牌侧 ===== */

.brand-side {
  flex: 0 0 45%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #0F172A 0%, #1E3A5F 40%, #1E40AF 100%);
  overflow: hidden;
}

.brand-noise {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 256px 256px;
  pointer-events: none;
}

.brand-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 48px;
}

.brand-logo {
  margin-bottom: 20px;
}

.brand-logo svg {
  filter: drop-shadow(0 4px 16px rgba(0, 0, 0, 0.15));
}

.brand-title {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  color: var(--color-ink-inverse);
  letter-spacing: 0.06em;
  line-height: 1.3;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.brand-subtitle {
  font-size: var(--text-caption);
  font-weight: 500;
  color: rgba(255, 255, 255, 0.85);
  letter-spacing: 0.08em;
  margin-top: 8px;
}

/* ===== 登录侧 ===== */

.login-side {
  flex: 1 1 55%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-base);
  position: relative;
  padding: 40px;
}

.login-side::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, var(--color-border) 0.5px, transparent 0.5px);
  background-size: 22px 22px;
  opacity: 0.5;
  pointer-events: none;
}

/* ===== 登录卡片 ===== */

.login-card {
  position: relative;
  width: 100%;
  max-width: 420px;
  padding: 44px 40px;
}

.login-heading {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--color-ink);
  text-align: center;
  margin-bottom: 32px;
  letter-spacing: -0.02em;
}

/* ===== 表单 ===== */

.login-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  font-size: var(--text-caption);
  font-weight: 500;
  color: var(--color-ink-secondary);
  padding-left: 2px;
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 12px;
  color: var(--color-ink-tertiary);
  pointer-events: none;
  z-index: 1;
  transition: color var(--duration-liquid) var(--ease-out);
}

.input-wrapper:focus-within .input-icon {
  color: var(--color-accent);
}

.has-left-icon {
  padding-left: 38px;
}

.has-right-icon {
  padding-right: 38px;
}

.password-toggle {
  position: absolute;
  right: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  background: none;
  color: var(--color-ink-tertiary);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color var(--duration-fast) var(--ease-out);
}

.password-toggle:hover {
  color: var(--color-ink-secondary);
}

/* ===== 错误消息 ===== */

.error-msg {
  font-size: var(--text-caption);
  color: var(--color-danger);
  background: rgba(239, 68, 68, 0.05);
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(239, 68, 68, 0.1);
}

/* ===== 提交按钮 ===== */

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  margin-top: 8px;
}

/* ===== 加载动画 ===== */

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

/* ===== 过渡动画 ===== */

.error-fade-enter-active { transition: all var(--duration-normal) var(--ease-out); }
.error-fade-leave-active { transition: all var(--duration-fast) var(--ease-out); }
.error-fade-enter-from,
.error-fade-leave-to { opacity: 0; transform: translateY(-4px); }

/* ===== 响应式 ===== */

@media (max-width: 720px) {
  .login-page {
    flex-direction: column;
  }

  .brand-side {
    flex: 0 0 auto;
    padding: 36px 24px;
  }

  .brand-content {
    padding: 16px;
  }

  .brand-title { font-size: 22px; }
  .brand-subtitle { font-size: var(--text-small); }

  .login-side {
    flex: 1 1 auto;
    padding: 20px 24px 48px;
  }

  .login-card {
    max-width: 100%;
    padding: 32px 24px;
  }

  .login-heading {
    font-size: 20px;
    margin-bottom: 24px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .flow-line-bar { animation: none; }
}
</style>
