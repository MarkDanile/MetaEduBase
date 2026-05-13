<template>
  <div class="min-h-screen flex items-center justify-center bg-[var(--color-bg-base)] relative overflow-hidden">
    <div class="absolute inset-0 z-0 pointer-events-none opacity-[0.04]">
      <svg width="100%" height="100%" viewBox="0 0 1200 900" fill="none" preserveAspectRatio="xMidYMid slice">
        <rect x="100" y="80" width="220" height="200" rx="20" stroke="var(--color-ink)" stroke-width="1.2" fill="none"/>
        <rect x="140" y="120" width="140" height="24" rx="4" fill="var(--color-ink)" opacity="0.4"/>
        <rect x="140" y="156" width="100" height="16" rx="3" fill="var(--color-ink)" opacity="0.3"/>
        <rect x="140" y="184" width="160" height="12" rx="2" fill="var(--color-ink)" opacity="0.2"/>
        <rect x="140" y="208" width="80" height="10" rx="2" fill="var(--color-ink)" opacity="0.15"/>
        <rect x="140" y="230" width="120" height="10" rx="2" fill="var(--color-ink)" opacity="0.1"/>
        <rect x="480" y="100" width="280" height="180" rx="24" stroke="var(--color-ink)" stroke-width="1.2" fill="none"/>
        <rect x="520" y="140" width="120" height="20" rx="3" fill="var(--color-ink)" opacity="0.35"/>
        <rect x="520" y="172" width="200" height="14" rx="2.5" fill="var(--color-ink)" opacity="0.25"/>
        <rect x="520" y="198" width="160" height="14" rx="2.5" fill="var(--color-ink)" opacity="0.2"/>
        <rect x="520" y="224" width="100" height="12" rx="2" fill="var(--color-ink)" opacity="0.15"/>
        <rect x="850" y="60" width="200" height="240" rx="18" stroke="var(--color-ink)" stroke-width="1" fill="none"/>
        <rect x="890" y="100" width="120" height="22" rx="3" fill="var(--color-ink)" opacity="0.3"/>
        <rect x="890" y="134" width="100" height="14" rx="2.5" fill="var(--color-ink)" opacity="0.2"/>
        <rect x="890" y="160" width="140" height="12" rx="2" fill="var(--color-ink)" opacity="0.15"/>
        <rect x="890" y="184" width="80" height="12" rx="2" fill="var(--color-ink)" opacity="0.1"/>
        <rect x="890" y="208" width="110" height="10" rx="2" fill="var(--color-ink)" opacity="0.08"/>
        <rect x="890" y="230" width="90" height="10" rx="2" fill="var(--color-ink)" opacity="0.06"/>
        <rect x="200" y="620" width="240" height="180" rx="22" stroke="var(--color-ink)" stroke-width="1" fill="none"/>
        <rect x="240" y="660" width="100" height="20" rx="3" fill="var(--color-ink)" opacity="0.3"/>
        <rect x="240" y="692" width="160" height="14" rx="2.5" fill="var(--color-ink)" opacity="0.2"/>
        <rect x="240" y="718" width="140" height="12" rx="2" fill="var(--color-ink)" opacity="0.15"/>
        <rect x="240" y="742" width="80" height="10" rx="2" fill="var(--color-ink)" opacity="0.1"/>
        <rect x="750" y="650" width="260" height="200" rx="20" stroke="var(--color-ink)" stroke-width="1" fill="none"/>
        <rect x="790" y="690" width="130" height="22" rx="3" fill="var(--color-ink)" opacity="0.3"/>
        <rect x="790" y="724" width="180" height="14" rx="2.5" fill="var(--color-ink)" opacity="0.2"/>
        <rect x="790" y="750" width="150" height="14" rx="2.5" fill="var(--color-ink)" opacity="0.15"/>
        <rect x="790" y="776" width="100" height="12" rx="2" fill="var(--color-ink)" opacity="0.1"/>
        <rect x="790" y="800" width="120" height="10" rx="2" fill="var(--color-ink)" opacity="0.08"/>
        <circle cx="380" cy="380" r="4" fill="var(--color-accent)" opacity="0.15"/>
        <circle cx="620" cy="420" r="3" fill="var(--color-accent)" opacity="0.12"/>
        <circle cx="550" cy="530" r="5" fill="var(--color-accent)" opacity="0.1"/>
        <circle cx="320" cy="510" r="3" fill="var(--color-accent)" opacity="0.1"/>
        <circle cx="780" cy="380" r="4" fill="var(--color-accent)" opacity="0.12"/>
        <line x1="380" y1="380" x2="480" y2="280" stroke="var(--color-accent)" stroke-width="0.6" stroke-opacity="0.1" stroke-dasharray="4 6"/>
        <line x1="380" y1="380" x2="320" y2="510" stroke="var(--color-accent)" stroke-width="0.6" stroke-opacity="0.08" stroke-dasharray="4 6"/>
        <line x1="550" y1="530" x2="620" y2="420" stroke="var(--color-accent)" stroke-width="0.6" stroke-opacity="0.08" stroke-dasharray="4 6"/>
        <line x1="620" y1="420" x2="780" y2="380" stroke="var(--color-accent)" stroke-width="0.5" stroke-opacity="0.06" stroke-dasharray="4 6"/>
      </svg>
    </div>

    <div class="relative z-10 w-full max-w-[420px] mx-6 animate-slide-up">
      <div class="login-card">
        <div class="text-center mb-8" :class="{ 'icon-focused': inputFocused }">
          <div class="relative inline-flex items-center justify-center mb-5">
            <svg width="64" height="64" viewBox="0 0 64 64" fill="none" class="relative z-[1]">
              <rect x="2" y="2" width="60" height="60" rx="14" stroke="var(--color-accent)" stroke-width="1.5" stroke-opacity="0.3" fill="none"/>
              <path d="M12 18C12 15.24 14.24 13 17 13H30L35 18H49C51.76 18 54 20.24 54 23V41C54 43.76 51.76 46 49 46H17C14.24 46 12 43.76 12 41V18Z" stroke="var(--color-accent)" stroke-width="1.8" fill="var(--color-accent-bg)" fill-opacity="0.4"/>
              <rect x="21" y="28" width="22" height="2.5" rx="1.2" fill="var(--color-accent)" opacity="0.45"/>
              <rect x="21" y="34" width="28" height="2.5" rx="1.2" fill="var(--color-accent)" opacity="0.3"/>
              <rect x="21" y="40" width="16" height="2.5" rx="1.2" fill="var(--color-accent)" opacity="0.2"/>
            </svg>
            <div class="absolute inset-[-8px] rounded-xl bg-[var(--color-accent-bg)] blur-md transition-opacity duration-300" :class="inputFocused ? 'opacity-100' : 'opacity-0'"></div>
          </div>
          <h1 class="text-[20px] font-semibold text-[var(--color-ink)] mb-1.5" style="letter-spacing:-0.3px">元知职教基座</h1>
          <p class="text-[14px] text-[var(--color-ink-secondary)]">MetaEduBase</p>
        </div>

        <div class="text-center mb-8">
          <h2 class="text-[18px] font-medium text-[var(--color-ink)]">欢迎登录</h2>
          <p class="text-[13px] text-[var(--color-ink-secondary)] mt-1">开启你的校本知识之旅</p>
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
  background: #FFFFFF;
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

.icon-focused svg {
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
