<template>
  <div class="min-h-screen flex">
    <div class="hidden lg:flex w-[480px] flex-shrink-0 bg-[var(--color-accent)] relative overflow-hidden items-center justify-center">
      <div class="absolute inset-0 z-0">
        <svg width="100%" height="100%" viewBox="0 0 480 900" fill="none" preserveAspectRatio="xMidYMid slice">
          <circle cx="120" cy="120" r="300" fill="white" opacity="0.03"/>
          <circle cx="400" cy="750" r="250" fill="white" opacity="0.03"/>
          <circle cx="240" cy="450" r="180" fill="white" opacity="0.02"/>
          <rect x="60" y="200" width="160" height="160" rx="24" stroke="white" stroke-width="1" stroke-opacity="0.08" fill="none"/>
          <rect x="280" y="60" width="140" height="140" rx="20" stroke="white" stroke-width="1" stroke-opacity="0.06" fill="none"/>
          <rect x="300" y="580" width="180" height="180" rx="32" stroke="white" stroke-width="1" stroke-opacity="0.07" fill="none"/>
          <rect x="40" y="520" width="120" height="120" rx="16" stroke="white" stroke-width="1" stroke-opacity="0.05" fill="none"/>
          <circle cx="140" cy="280" r="4" fill="white" opacity="0.12"/>
          <circle cx="140" cy="280" r="8" fill="white" opacity="0.04"/>
          <circle cx="350" cy="160" r="3" fill="white" opacity="0.1"/>
          <circle cx="240" cy="380" r="5" fill="white" opacity="0.08"/>
          <circle cx="140" cy="620" r="3" fill="white" opacity="0.1"/>
          <circle cx="400" cy="500" r="4" fill="white" opacity="0.08"/>
          <line x1="140" y1="288" x2="240" y2="375" stroke="white" stroke-width="0.6" stroke-opacity="0.06" stroke-dasharray="4 6"/>
          <line x1="350" y1="166" x2="280" y2="280" stroke="white" stroke-width="0.5" stroke-opacity="0.05" stroke-dasharray="4 6"/>
          <line x1="140" y1="626" x2="300" y2="670" stroke="white" stroke-width="0.5" stroke-opacity="0.05" stroke-dasharray="4 6"/>
          <line x1="400" y1="506" x2="240" y2="377" stroke="white" stroke-width="0.5" stroke-opacity="0.04" stroke-dasharray="4 8"/>
          <path d="M180 130 L180 160" stroke="white" stroke-width="0.5" stroke-opacity="0.05"/>
          <path d="M300 130 L300 160" stroke="white" stroke-width="0.5" stroke-opacity="0.05"/>
          <path d="M340 680 L340 710" stroke="white" stroke-width="0.5" stroke-opacity="0.05"/>
          <path d="M400 680 L400 710" stroke="white" stroke-width="0.5" stroke-opacity="0.05"/>
          <rect x="165" y="118" width="14" height="14" rx="3" stroke="white" stroke-width="0.8" stroke-opacity="0.12" fill="none"/>
          <circle cx="172" cy="132" r="3" fill="white" opacity="0.15"/>
          <rect x="285" y="118" width="12" height="12" rx="2.5" stroke="white" stroke-width="0.7" stroke-opacity="0.1" fill="none"/>
          <rect x="325" y="668" width="14" height="14" rx="3" stroke="white" stroke-width="0.8" stroke-opacity="0.12" fill="none"/>
          <circle cx="332" cy="682" r="2.5" fill="white" opacity="0.14"/>
          <rect x="385" y="668" width="10" height="10" rx="2" stroke="white" stroke-width="0.6" stroke-opacity="0.09" fill="none"/>
          <path d="M120 450 Q240 380 360 450" stroke="white" stroke-width="4" stroke-opacity="0.04" fill="none"/>
          <path d="M140 470 Q240 410 340 470" stroke="white" stroke-width="2" stroke-opacity="0.03" fill="none"/>
        </svg>
      </div>
      <div class="relative z-10 text-center px-12">
        <svg class="mx-auto mb-8" width="72" height="72" viewBox="0 0 72 72" fill="none">
          <rect x="4" y="4" width="64" height="64" rx="16" stroke="white" stroke-width="1.5" stroke-opacity="0.3" fill="none"/>
          <path d="M14 20C14 16.69 16.69 14 20 14H34L40 20H58C61.31 20 64 22.69 64 26V48C64 51.31 61.31 54 58 54H20C16.69 54 14 51.31 14 48V20Z" stroke="white" stroke-width="2" fill="rgba(255,255,255,0.08)"/>
          <rect x="24" y="32" width="24" height="3" rx="1.5" fill="white" opacity="0.5"/>
          <rect x="24" y="39" width="32" height="3" rx="1.5" fill="white" opacity="0.35"/>
          <rect x="24" y="46" width="18" height="3" rx="1.5" fill="white" opacity="0.25"/>
        </svg>
        <h1 class="text-[32px] font-semibold text-white tracking-tight mb-2" style="letter-spacing:-0.5px">元知职教基座</h1>
        <p class="text-[13px] text-white/50 font-medium tracking-wide mb-3">MetaEduBase</p>
        <p class="text-[14px] text-white/60 leading-relaxed">面向职业教育的 AI 知识平台</p>
        <div class="mt-12 flex justify-center gap-8">
          <div class="text-center">
            <p class="text-[28px] font-semibold text-white tabular-nums">10</p>
            <p class="text-[11px] text-white/40 mt-0.5">专业域</p>
          </div>
          <div class="w-px h-12 bg-white/15"></div>
          <div class="text-center">
            <p class="text-[28px] font-semibold text-white tabular-nums">6</p>
            <p class="text-[11px] text-white/40 mt-0.5">知识层级</p>
          </div>
          <div class="w-px h-12 bg-white/15"></div>
          <div class="text-center">
            <p class="text-[28px] font-semibold text-white">AI</p>
            <p class="text-[11px] text-white/40 mt-0.5">智能助教</p>
          </div>
        </div>
      </div>
    </div>

    <div class="flex-1 flex items-center justify-center bg-gradient-to-br from-[#1E293B] via-[#172033] to-[#0F172A] relative overflow-hidden">
      <div class="absolute inset-0 z-0 pointer-events-none">
        <svg width="100%" height="100%" viewBox="0 0 600 900" fill="none" preserveAspectRatio="xMidYMid slice">
          <rect x="380" y="120" width="200" height="200" rx="28" stroke="white" stroke-width="0.8" stroke-opacity="0.06" fill="none"/>
          <rect x="420" y="160" width="120" height="120" rx="14" stroke="white" stroke-width="0.6" stroke-opacity="0.05" fill="none"/>
          <rect x="460" y="200" width="40" height="40" rx="6" stroke="#3B82F6" stroke-width="0.8" stroke-opacity="0.12" fill="#3B82F6" fill-opacity="0.06"/>
          <rect x="60" y="600" width="160" height="160" rx="20" stroke="white" stroke-width="0.8" stroke-opacity="0.05" fill="none"/>
          <rect x="100" y="640" width="80" height="80" rx="10" stroke="#3B82F6" stroke-width="0.6" stroke-opacity="0.1" fill="#3B82F6" fill-opacity="0.04"/>
          <circle cx="140" cy="680" r="5" fill="#3B82F6" opacity="0.08"/>
          <circle cx="500" cy="620" r="6" fill="#94A3B8" opacity="0.06"/>
          <circle cx="300" cy="750" r="250" fill="#3B82F6" opacity="0.02"/>
          <circle cx="150" cy="200" r="180" fill="#3B82F6" opacity="0.02"/>
          <path d="M140 700 L300 730" stroke="white" stroke-width="0.5" stroke-opacity="0.06" stroke-dasharray="3 5"/>
          <path d="M460 220 L500 620" stroke="white" stroke-width="0.5" stroke-opacity="0.05" stroke-dasharray="3 5"/>
          <path d="M500 240 L300 200" stroke="white" stroke-width="0.4" stroke-opacity="0.04"/>
        </svg>
      </div>
      <div class="w-full max-w-[400px] mx-6 animate-slide-up relative z-10">
        <div class="lg:hidden text-center mb-8">
          <div class="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[var(--color-accent)] mb-4">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
          </div>
          <h1 class="text-[24px] font-semibold tracking-tight text-white" style="letter-spacing:-0.5px">元知职教基座</h1>
          <p class="text-[12px] text-white/30 mt-0.5">MetaEduBase</p>
        </div>

        <div class="liquid-card p-8">
          <div class="mb-6">
            <h2 class="text-[20px] font-semibold tracking-tight" style="letter-spacing:-0.5px">欢迎登录</h2>
            <p class="text-[13px] text-[var(--color-ink-tertiary)] mt-1">进入你的知识空间</p>
            <div class="wet-line mt-2.5" style="width:36px"></div>
          </div>

          <form @submit.prevent="handleLogin" class="space-y-4">
            <div>
              <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">用户名</label>
              <input
                v-model="form.username"
                type="text"
                class="liquid-input"
                placeholder="请输入用户名"
                required
              />
            </div>
            <div>
              <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">密码</label>
              <input
                v-model="form.password"
                type="password"
                class="liquid-input"
                placeholder="请输入密码"
                required
              />
            </div>

            <transition name="error-fade">
              <p v-if="error" class="text-[13px] text-[var(--color-danger)] bg-[rgba(239,68,68,0.04)] px-3 py-2 rounded-[var(--radius-md)]">{{ error }}</p>
            </transition>

            <button
              type="submit"
              :disabled="loading"
              class="liquid-btn liquid-btn-primary w-full py-2.5 text-[15px]"
            >
              <svg v-if="loading" class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              {{ loading ? "正在验证..." : "登 录" }}
            </button>
          </form>
        </div>

        <p class="text-[11px] text-white/20 text-center mt-6">
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
</style>
