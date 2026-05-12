<template>
  <div class="min-h-screen flex items-center justify-center relative overflow-hidden">
    <div class="mesh-bg" />

    <div class="absolute top-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full bg-[var(--color-bg-mesh-1)] opacity-40 blur-[120px] animate-orb-1" />
    <div class="absolute bottom-[-15%] right-[-5%] w-[500px] h-[500px] rounded-full bg-[var(--color-bg-mesh-2)] opacity-35 blur-[100px] animate-orb-2" />
    <div class="absolute top-[40%] right-[20%] w-[350px] h-[350px] rounded-full bg-[var(--color-bg-mesh-3)] opacity-30 blur-[80px] animate-orb-3" />

    <div class="relative z-10 w-full max-w-[420px] mx-6 animate-slide-up">
      <div class="glass-heavy rounded-[var(--radius-xl)] p-10">
        <div class="text-center mb-8">
          <div class="inline-flex items-center justify-center w-14 h-14 rounded-[var(--radius-lg)] bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-light)] mb-5 shadow-[var(--shadow-glow)]">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
          </div>
          <h1 class="text-[26px] font-semibold tracking-tight" style="font-family: var(--font-display)">MetaEduBase</h1>
          <p class="text-[13px] text-[var(--color-ink-tertiary)] mt-1.5 tracking-wide">元知职教基座 · AI Native 知识平台</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-5">
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1.5 ml-1">用户名</label>
            <input
              v-model="form.username"
              type="text"
              class="liquid-input"
              placeholder="请输入用户名"
              required
            />
          </div>
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1.5 ml-1">密码</label>
            <input
              v-model="form.password"
              type="password"
              class="liquid-input"
              placeholder="请输入密码"
              required
            />
          </div>

          <transition name="error-fade">
            <p v-if="error" class="text-[13px] text-[var(--color-danger)] bg-[rgba(239,68,68,0.08)] px-4 py-2.5 rounded-[var(--radius-md)] leading-snug">{{ error }}</p>
          </transition>

          <button
            type="submit"
            :disabled="loading"
            class="liquid-btn liquid-btn-primary w-full py-3 text-[15px]"
          >
            <svg v-if="loading" class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
            {{ loading ? "正在验证..." : "登 录" }}
          </button>
        </form>

        <p class="text-[11px] text-[var(--color-ink-tertiary)] mt-7 text-center tracking-wide">默认账号: admin / admin123</p>
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
.animate-orb-1 {
  animation: orb-float-1 20s ease-in-out infinite alternate;
}
.animate-orb-2 {
  animation: orb-float-2 18s ease-in-out infinite alternate;
}
.animate-orb-3 {
  animation: orb-float-3 22s ease-in-out infinite alternate;
}

@keyframes orb-float-1 {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(40px, -30px) scale(1.08); }
}
@keyframes orb-float-2 {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(-30px, 20px) scale(1.05); }
}
@keyframes orb-float-3 {
  0% { transform: translate(0, 0) scale(1); }
  100% { transform: translate(20px, 30px) scale(0.95); }
}

.error-fade-enter-active {
  transition: all var(--duration-normal) var(--ease-liquid);
}
.error-fade-leave-active {
  transition: all var(--duration-fast) var(--ease-liquid);
}
.error-fade-enter-from,
.error-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
