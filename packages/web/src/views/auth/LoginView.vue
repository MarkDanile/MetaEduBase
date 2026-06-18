<template>
  <div class="login-page">
    <div class="brand-side">
      <div class="brand-noise"></div>
      <div class="brand-content">
        <div class="brand-logo app-brand-mark">
          <BookOpen :size="22" :stroke-width="1.8" />
        </div>
        <h1 class="brand-title">元知职教基座</h1>
        <p class="brand-subtitle">AI Native · 职业教育知识基座</p>
        <div class="brand-capabilities" aria-label="核心能力">
          <span>RAG</span>
          <span>Agent</span>
          <span>Knowledge Base</span>
        </div>
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
                class="ui-input has-left-icon"
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
                class="ui-input has-left-icon has-right-icon"
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
            class="ui-btn ui-btn-primary submit-btn"
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
import { User, Lock, Eye, EyeOff, BookOpen } from "lucide-vue-next";
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
  background: var(--login-brand-gradient);
  border-right: 1px solid var(--login-brand-border);
  overflow: hidden;
}

.brand-side::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(115deg, rgba(255, 255, 255, 0.18), transparent 34%),
    linear-gradient(180deg, transparent 0%, rgba(15, 23, 42, 0.18) 100%);
  pointer-events: none;
}

.brand-side::after {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--login-brand-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--login-brand-grid) 1px, transparent 1px),
    radial-gradient(circle at 50% 42%, var(--login-brand-orbit) 0 1px, transparent 1px),
    linear-gradient(135deg, transparent 0 42%, rgba(255, 255, 255, 0.16) 42% 43%, transparent 43% 100%);
  background-size: 34px 34px, 34px 34px, 164px 164px, 100% 100%;
  mask-image: linear-gradient(90deg, rgba(0, 0, 0, 0.86), transparent 94%);
  pointer-events: none;
}

.brand-noise {
  position: absolute;
  inset: auto -72px -96px auto;
  width: 240px;
  height: 240px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 999px;
  box-shadow:
    0 0 0 32px rgba(255, 255, 255, 0.04),
    0 0 0 72px rgba(255, 255, 255, 0.03);
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
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  margin-bottom: 20px;
  color: var(--login-brand-title);
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.28);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.22);
}

.brand-title {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
  color: var(--login-brand-title);
  letter-spacing: 0.06em;
  line-height: 1.3;
  text-shadow: 0 8px 24px rgba(15, 23, 42, 0.24);
}

.brand-subtitle {
  font-size: var(--text-caption);
  font-weight: 500;
  color: var(--login-brand-subtitle);
  letter-spacing: 0.08em;
  margin-top: 8px;
}

.brand-capabilities {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 24px;
}

.brand-capabilities span {
  padding: 5px 10px;
  border: 1px solid var(--login-brand-pill-border);
  border-radius: var(--radius-full);
  background: var(--login-brand-pill-bg);
  color: var(--login-brand-pill-text);
  font-size: var(--text-micro);
  font-weight: 600;
  letter-spacing: 0.04em;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
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
  display: none;
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
  letter-spacing: 0;
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
