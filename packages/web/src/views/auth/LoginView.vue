<template>
  <div class="min-h-screen flex">
    <div class="hidden md:flex w-[480px] flex-shrink-0 relative overflow-hidden items-center justify-center" style="background: linear-gradient(180deg, #3B82F6 0%, #60A5FA 100%)">
      <div class="absolute inset-0 z-0">
        <svg width="100%" height="100%" viewBox="0 0 480 900" fill="none" preserveAspectRatio="xMidYMid slice">
          <circle cx="120" cy="120" r="300" fill="white" opacity="0.02"/>
          <circle cx="400" cy="750" r="250" fill="white" opacity="0.02"/>
          <circle cx="240" cy="450" r="180" fill="white" opacity="0.015"/>
          <rect x="60" y="200" width="160" height="160" rx="24" stroke="white" stroke-width="1" stroke-opacity="0.06" fill="none"/>
          <rect x="280" y="60" width="140" height="140" rx="20" stroke="white" stroke-width="1" stroke-opacity="0.05" fill="none"/>
          <rect x="300" y="580" width="180" height="180" rx="32" stroke="white" stroke-width="1" stroke-opacity="0.06" fill="none"/>
          <rect x="40" y="520" width="120" height="120" rx="16" stroke="white" stroke-width="1" stroke-opacity="0.04" fill="none"/>
          <circle cx="140" cy="280" r="4" fill="white" opacity="0.1"/>
          <circle cx="350" cy="160" r="3" fill="white" opacity="0.08"/>
          <circle cx="240" cy="380" r="5" fill="white" opacity="0.06"/>
          <circle cx="140" cy="620" r="3" fill="white" opacity="0.08"/>
          <circle cx="400" cy="500" r="4" fill="white" opacity="0.06"/>
          <line x1="140" y1="288" x2="240" y2="375" stroke="white" stroke-width="0.6" stroke-opacity="0.05" stroke-dasharray="4 6"/>
          <line x1="350" y1="166" x2="280" y2="280" stroke="white" stroke-width="0.5" stroke-opacity="0.04" stroke-dasharray="4 6"/>
          <line x1="140" y1="626" x2="300" y2="670" stroke="white" stroke-width="0.5" stroke-opacity="0.04" stroke-dasharray="4 6"/>
          <line x1="400" y1="506" x2="240" y2="377" stroke="white" stroke-width="0.5" stroke-opacity="0.03" stroke-dasharray="4 8"/>
          <path d="M180 130 L180 160" stroke="white" stroke-width="0.5" stroke-opacity="0.04"/>
          <path d="M300 130 L300 160" stroke="white" stroke-width="0.5" stroke-opacity="0.04"/>
          <path d="M340 680 L340 710" stroke="white" stroke-width="0.5" stroke-opacity="0.04"/>
          <path d="M400 680 L400 710" stroke="white" stroke-width="0.5" stroke-opacity="0.04"/>
          <rect x="165" y="118" width="14" height="14" rx="3" stroke="white" stroke-width="0.8" stroke-opacity="0.1" fill="none"/>
          <circle cx="172" cy="132" r="3" fill="white" opacity="0.12"/>
          <rect x="285" y="118" width="12" height="12" rx="2.5" stroke="white" stroke-width="0.7" stroke-opacity="0.08" fill="none"/>
          <rect x="325" y="668" width="14" height="14" rx="3" stroke="white" stroke-width="0.8" stroke-opacity="0.1" fill="none"/>
          <circle cx="332" cy="682" r="2.5" fill="white" opacity="0.12"/>
          <rect x="385" y="668" width="10" height="10" rx="2" stroke="white" stroke-width="0.6" stroke-opacity="0.07" fill="none"/>
          <path d="M120 450 Q240 380 360 450" stroke="white" stroke-width="4" stroke-opacity="0.03" fill="none"/>
          <path d="M140 470 Q240 410 340 470" stroke="white" stroke-width="2" stroke-opacity="0.02" fill="none"/>
        </svg>
      </div>
      <div class="relative z-10 text-center px-12">
        <div class="mx-auto mb-10" :class="{ 'icon-focused': inputFocused }">
          <div class="relative inline-flex items-center justify-center">
            <svg width="72" height="72" viewBox="0 0 72 72" fill="none" class="relative z-[1]">
              <rect x="4" y="4" width="64" height="64" rx="16" stroke="white" stroke-width="1.5" stroke-opacity="0.3" fill="none"/>
              <path d="M14 20C14 16.69 16.69 14 20 14H34L40 20H58C61.31 20 64 22.69 64 26V48C64 51.31 61.31 54 58 54H20C16.69 54 14 51.31 14 48V20Z" stroke="white" stroke-width="2" fill="rgba(255,255,255,0.1)"/>
              <rect x="24" y="32" width="24" height="3" rx="1.5" fill="white" opacity="0.55"/>
              <rect x="24" y="39" width="32" height="3" rx="1.5" fill="white" opacity="0.4"/>
              <rect x="24" y="46" width="18" height="3" rx="1.5" fill="white" opacity="0.3"/>
            </svg>
            <div class="absolute inset-[-12px] rounded-2xl bg-white/10 blur-lg transition-opacity duration-300" :class="inputFocused ? 'opacity-100' : 'opacity-0'"></div>
          </div>
        </div>
        <h1 class="text-[28px] font-semibold text-white mb-2" style="letter-spacing:-0.5px;line-height:1.2">元知职教基座</h1>
        <p class="text-[16px] text-white/80 mb-3" style="line-height:1.4">MetaEduBase</p>
        <p class="text-[14px] text-white/70" style="line-height:1.5">面向职业教育的 AI 知识平台</p>
        <div class="mt-12 flex justify-center gap-6">
          <div class="bg-white/15 rounded-[var(--radius-lg)] px-4 py-4 min-w-[88px] text-center">
            <p class="text-[24px] font-semibold text-white tabular-nums">10</p>
            <p class="text-[12px] text-white/70 mt-0.5">专业域</p>
          </div>
          <div class="bg-white/15 rounded-[var(--radius-lg)] px-4 py-4 min-w-[88px] text-center">
            <p class="text-[24px] font-semibold text-white tabular-nums">6</p>
            <p class="text-[12px] text-white/70 mt-0.5">知识层级</p>
          </div>
          <div class="bg-white/15 rounded-[var(--radius-lg)] px-4 py-4 min-w-[88px] text-center">
            <p class="text-[24px] font-semibold text-white">AI</p>
            <p class="text-[12px] text-white/70 mt-0.5">智能助教</p>
          </div>
        </div>
      </div>
    </div>

    <div class="flex-1 flex items-center justify-center bg-[var(--color-bg-base)] relative overflow-hidden">
      <div class="absolute inset-0 z-0 pointer-events-none">
        <svg width="100%" height="100%" viewBox="0 0 600 900" fill="none" preserveAspectRatio="xMidYMid slice">
          <rect x="380" y="120" width="200" height="200" rx="28" stroke="var(--color-border)" stroke-width="0.8" stroke-opacity="0.25" fill="none"/>
          <rect x="420" y="160" width="120" height="120" rx="14" stroke="var(--color-border)" stroke-width="0.6" stroke-opacity="0.18" fill="none"/>
          <rect x="460" y="200" width="40" height="40" rx="6" stroke="var(--color-accent)" stroke-width="0.6" stroke-opacity="0.08" fill="var(--color-accent-bg)" fill-opacity="0.15"/>
          <rect x="60" y="600" width="160" height="160" rx="20" stroke="var(--color-border)" stroke-width="0.8" stroke-opacity="0.2" fill="none"/>
          <rect x="100" y="640" width="80" height="80" rx="10" stroke="var(--color-accent)" stroke-width="0.5" stroke-opacity="0.06" fill="var(--color-accent-bg)" fill-opacity="0.1"/>
          <circle cx="500" cy="620" r="6" fill="var(--color-ink-tertiary)" opacity="0.05"/>
          <circle cx="300" cy="750" r="250" fill="var(--color-accent)" opacity="0.01"/>
          <circle cx="150" cy="200" r="180" fill="var(--color-accent)" opacity="0.01"/>
          <path d="M140 700 L300 730" stroke="var(--color-border)" stroke-width="0.5" stroke-opacity="0.15" stroke-dasharray="3 5"/>
          <path d="M460 220 L500 620" stroke="var(--color-border)" stroke-width="0.5" stroke-opacity="0.12" stroke-dasharray="3 5"/>
        </svg>
      </div>

      <div class="w-full max-w-[400px] mx-6 animate-slide-up relative z-10">
        <div class="md:hidden text-center mb-8">
          <div class="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[var(--color-accent)] mb-4">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
          </div>
          <h1 class="text-[24px] font-semibold tracking-tight" style="letter-spacing:-0.5px">元知职教基座</h1>
          <p class="text-[12px] text-[var(--color-ink-tertiary)] mt-0.5">MetaEduBase</p>
        </div>

        <div class="login-card px-7 py-8">
          <div>
            <h2 class="text-[20px] font-semibold text-[var(--color-ink)]" style="line-height:1.3">欢迎登录</h2>
            <p class="text-[14px] text-[var(--color-ink-secondary)] mt-2" style="line-height:1.4">开启你的校本知识之旅</p>
            <div class="wet-line mt-2.5" style="width:36px"></div>
          </div>

          <form @submit.prevent="handleLogin" class="mt-6 space-y-4">
            <div>
              <label class="block text-[14px] font-medium text-[var(--color-ink)] mb-2">用户名</label>
              <input
                v-model="form.username"
                type="text"
                class="liquid-input"
                placeholder="请输入用户名"
                required
                @focus="inputFocused = true"
                @blur="inputFocused = false"
              />
            </div>
            <div>
              <label class="block text-[14px] font-medium text-[var(--color-ink)] mb-2">密码</label>
              <input
                v-model="form.password"
                type="password"
                class="liquid-input"
                placeholder="请输入密码"
                required
                @focus="inputFocused = true"
                @blur="inputFocused = false"
              />
            </div>

            <transition name="error-fade">
              <p v-if="error" class="text-[13px] text-[var(--color-danger)] bg-[rgba(239,68,68,0.04)] px-3 py-2 rounded-[var(--radius-md)]">{{ error }}</p>
            </transition>

            <button
              type="submit"
              :disabled="loading"
              class="liquid-btn liquid-btn-primary w-full text-[16px] login-btn"
            >
              <template v-if="loading">
                <div class="flow-line">
                  <div class="flow-line-bar"></div>
                </div>
                正在验证
              </template>
              <template v-else>登 录</template>
            </button>
          </form>

          <p class="text-[12px] text-[var(--color-ink-tertiary)] text-center mt-4">
            默认账号: admin / admin123
          </p>
        </div>
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

.icon-focused svg {
  filter: drop-shadow(0 0 12px rgba(255, 255, 255, 0.3));
  transition: filter 200ms var(--ease-out);
}

.login-card {
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(59, 130, 246, 0.1);
  border-radius: var(--radius-xl);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.login-btn {
  height: 40px;
}

.login-btn:hover {
  transform: scale(1.02);
}

.flow-line {
  width: 32px;
  height: 3px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.flow-line-bar {
  width: 12px;
  height: 100%;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0.4));
  border-radius: 2px;
  animation: flow-slide 1.6s ease-in-out infinite;
}

@keyframes flow-slide {
  0% { transform: translateX(0); }
  30% { transform: translateX(10px); }
  50% { transform: translateX(20px); }
  70% { transform: translateX(6px); }
  100% { transform: translateX(0); }
}

@media (prefers-reduced-motion: reduce) {
  .flow-line-bar { animation: none; }
}
</style>
