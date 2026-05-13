<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden" style="background: linear-gradient(135deg, #EFF6FF 0%, #F0F4FF 30%, #F5F7FF 60%, #F8FAFC 100%)">
    <div class="absolute inset-0 z-0 pointer-events-none">
      <div class="absolute -top-60 -right-40 w-[500px] h-[500px] rounded-full bg-[#DBEAFE] opacity-30 blur-[80px]"></div>
      <div class="absolute -bottom-40 -left-20 w-[400px] h-[400px] rounded-full bg-[#BFDBFE] opacity-25 blur-[100px]"></div>
      <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[300px] h-[300px] rounded-full bg-[#EFF6FF] opacity-40 blur-[60px]"></div>
    </div>
    <div class="absolute inset-0 z-[1] pointer-events-none">
      <svg width="100%" height="100%" viewBox="0 0 1200 900" fill="none" preserveAspectRatio="xMidYMid slice">
        <rect x="80" y="80" width="280" height="220" rx="16" stroke="#93C5FD" stroke-width="1.2" stroke-opacity="0.25" fill="none"/>
        <rect x="120" y="120" width="120" height="18" rx="4" fill="#60A5FA" opacity="0.12"/>
        <rect x="120" y="150" width="200" height="12" rx="3" fill="#93C5FD" opacity="0.1"/>
        <rect x="120" y="174" width="160" height="10" rx="2.5" fill="#93C5FD" opacity="0.08"/>
        <rect x="120" y="196" width="220" height="10" rx="2.5" fill="#BFDBFE" opacity="0.1"/>
        <rect x="120" y="218" width="100" height="8" rx="2" fill="#BFDBFE" opacity="0.08"/>
        <rect x="120" y="238" width="140" height="8" rx="2" fill="#BFDBFE" opacity="0.06"/>
        <rect x="480" y="100" width="320" height="200" rx="18" stroke="#60A5FA" stroke-width="1.2" stroke-opacity="0.22" fill="none"/>
        <rect x="520" y="140" width="140" height="16" rx="4" fill="#3B82F6" opacity="0.1"/>
        <rect x="520" y="168" width="240" height="12" rx="3" fill="#60A5FA" opacity="0.09"/>
        <rect x="520" y="192" width="180" height="10" rx="2.5" fill="#93C5FD" opacity="0.08"/>
        <rect x="520" y="214" width="220" height="10" rx="2.5" fill="#BFDBFE" opacity="0.07"/>
        <rect x="520" y="236" width="140" height="8" rx="2" fill="#BFDBFE" opacity="0.06"/>
        <rect x="900" y="60" width="220" height="260" rx="14" stroke="#93C5FD" stroke-width="1" stroke-opacity="0.2" fill="none"/>
        <rect x="940" y="100" width="100" height="18" rx="4" fill="#60A5FA" opacity="0.1"/>
        <rect x="940" y="130" width="140" height="12" rx="3" fill="#93C5FD" opacity="0.08"/>
        <rect x="940" y="154" width="120" height="10" rx="2.5" fill="#BFDBFE" opacity="0.07"/>
        <rect x="940" y="176" width="80" height="10" rx="2.5" fill="#BFDBFE" opacity="0.06"/>
        <rect x="200" y="620" width="300" height="200" rx="16" stroke="#60A5FA" stroke-width="1.2" stroke-opacity="0.22" fill="none"/>
        <rect x="240" y="660" width="120" height="16" rx="4" fill="#3B82F6" opacity="0.1"/>
        <rect x="240" y="688" width="220" height="12" rx="3" fill="#60A5FA" opacity="0.08"/>
        <rect x="240" y="712" width="180" height="10" rx="2.5" fill="#93C5FD" opacity="0.07"/>
        <rect x="240" y="734" width="100" height="10" rx="2.5" fill="#BFDBFE" opacity="0.06"/>
        <rect x="800" y="620" width="280" height="180" rx="16" stroke="#93C5FD" stroke-width="1" stroke-opacity="0.2" fill="none"/>
        <rect x="840" y="660" width="130" height="16" rx="4" fill="#60A5FA" opacity="0.09"/>
        <rect x="840" y="688" width="180" height="12" rx="3" fill="#93C5FD" opacity="0.07"/>
        <rect x="840" y="712" width="140" height="10" rx="2.5" fill="#BFDBFE" opacity="0.06"/>
        <circle cx="340" cy="360" r="6" fill="#3B82F6" opacity="0.2"/>
        <circle cx="420" cy="340" r="4" fill="#60A5FA" opacity="0.15"/>
        <circle cx="380" cy="420" r="5" fill="#3B82F6" opacity="0.18"/>
        <circle cx="560" cy="380" r="4" fill="#60A5FA" opacity="0.15"/>
        <circle cx="680" cy="420" r="5" fill="#3B82F6" opacity="0.16"/>
        <circle cx="620" cy="500" r="3" fill="#93C5FD" opacity="0.12"/>
        <circle cx="500" cy="520" r="4" fill="#60A5FA" opacity="0.14"/>
        <circle cx="350" cy="540" r="3" fill="#93C5FD" opacity="0.12"/>
        <circle cx="260" cy="440" r="4" fill="#60A5FA" opacity="0.13"/>
        <circle cx="720" cy="340" r="3" fill="#93C5FD" opacity="0.11"/>
        <circle cx="820" cy="480" r="4" fill="#60A5FA" opacity="0.12"/>
        <circle cx="450" cy="560" r="3" fill="#93C5FD" opacity="0.1"/>
        <line x1="340" y1="360" x2="420" y2="340" stroke="#93C5FD" stroke-width="0.8" stroke-opacity="0.2"/>
        <line x1="340" y1="360" x2="380" y2="420" stroke="#93C5FD" stroke-width="0.8" stroke-opacity="0.18"/>
        <line x1="380" y1="420" x2="260" y2="440" stroke="#BFDBFE" stroke-width="0.7" stroke-opacity="0.15"/>
        <line x1="420" y1="340" x2="560" y2="380" stroke="#93C5FD" stroke-width="0.8" stroke-opacity="0.18"/>
        <line x1="560" y1="380" x2="680" y2="420" stroke="#BFDBFE" stroke-width="0.7" stroke-opacity="0.15"/>
        <line x1="560" y1="380" x2="500" y2="520" stroke="#93C5FD" stroke-width="0.7" stroke-opacity="0.16"/>
        <line x1="680" y1="420" x2="620" y2="500" stroke="#BFDBFE" stroke-width="0.7" stroke-opacity="0.14"/>
        <line x1="380" y1="420" x2="350" y2="540" stroke="#BFDBFE" stroke-width="0.7" stroke-opacity="0.13"/>
        <line x1="680" y1="420" x2="820" y2="480" stroke="#BFDBFE" stroke-width="0.7" stroke-opacity="0.12"/>
        <line x1="620" y1="500" x2="500" y2="520" stroke="#BFDBFE" stroke-width="0.6" stroke-opacity="0.1"/>
      </svg>
    </div>

    <div class="relative z-10 w-full max-w-[420px] mx-6 animate-slide-up">
      <div class="login-card">
        <div class="flex items-center justify-center gap-3 mb-7" :class="{ 'logo-focused': inputFocused }">
          <div class="relative flex-shrink-0">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" class="relative z-[1]">
              <rect x="1" y="1" width="38" height="38" rx="10" fill="url(#logo-grad)"/>
              <text x="20" y="27" text-anchor="middle" fill="white" font-size="20" font-weight="700" font-family="Inter, sans-serif">元</text>
              <defs>
                <linearGradient id="logo-grad" x1="0" y1="0" x2="0" y2="40">
                  <stop stop-color="#3B82F6"/>
                  <stop offset="1" stop-color="#60A5FA"/>
                </linearGradient>
              </defs>
            </svg>
            <div class="absolute inset-[-6px] rounded-xl bg-[var(--color-accent-bg)] blur-sm transition-opacity duration-300" :class="inputFocused ? 'opacity-100' : 'opacity-0'"></div>
          </div>
          <div>
            <h1 class="text-[18px] font-semibold text-[var(--color-ink)]" style="letter-spacing:-0.3px">元知职教基座</h1>
            <p class="text-[13px] text-[var(--color-ink-secondary)]">开启你的校本知识之旅</p>
          </div>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-4">
          <input
            v-model="form.username"
            type="text"
            class="liquid-input"
            style="height:40px"
            placeholder="用户名"
            required
            @focus="inputFocused = true"
            @blur="inputFocused = false"
          />
          <input
            v-model="form.password"
            type="password"
            class="liquid-input"
            style="height:40px"
            placeholder="密码"
            required
            @focus="inputFocused = true"
            @blur="inputFocused = false"
          />

          <transition name="error-fade">
            <p v-if="error" class="text-[13px] text-[var(--color-danger)] bg-[rgba(239,68,68,0.04)] px-3 py-2 rounded-[var(--radius-md)]">{{ error }}</p>
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

        <p class="text-[12px] text-[var(--color-ink-tertiary)] text-center mt-5">
          默认账号: admin / admin123
        </p>
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
const inputFocused = ref(false);

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
.error-fade-enter-active {
  transition: all var(--duration-normal) var(--ease-out);
}
.error-fade-leave-active {
  transition: all var(--duration-fast) var(--ease-out);
}
.error-fade-enter-from,
.error-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.login-card {
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-xl);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
  padding: 40px 32px;
  transition: box-shadow var(--duration-slow) var(--ease-out);
}

.login-btn {
  height: 40px;
  font-size: 16px;
}

.login-btn:hover {
  transform: scale(1.02);
}

.logo-focused svg {
  filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.2));
  transition: filter 200ms var(--ease-out);
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

@media (max-width: 480px) {
  .login-card {
    padding: 32px 24px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .flow-line-bar { animation: none; }
}
</style>
