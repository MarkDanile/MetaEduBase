<template>
  <div class="flex min-h-screen">
    <aside class="sidebar-shell fixed left-0 top-0 bottom-0 w-[200px] flex flex-col z-10">
      <div class="px-5 pt-5 pb-4">
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
          </div>
          <div>
            <h1 class="text-[14px] font-semibold tracking-tight text-[var(--color-ink)]" style="letter-spacing:-0.3px">元知职教基座</h1>
            <p class="text-[10px] text-[var(--color-ink-tertiary)] -mt-0.5">MetaEduBase</p>
          </div>
        </div>
      </div>

      <nav class="flex-1 px-3 space-y-0.5">
        <RouterLink
          v-for="item in navItems"
          :key="item.route"
          :to="item.route"
          class="nav-item"
          :class="{ 'nav-item-active': isActive(item.route) }"
        >
          <div class="nav-icon" v-html="item.icon" />
          <span class="nav-label">{{ item.title }}</span>
        </RouterLink>
      </nav>

      <div class="px-4 pb-4 pt-3 border-t border-[var(--color-border)]">
        <div class="flex items-center gap-2.5 px-2">
          <div class="w-7 h-7 rounded-full bg-[var(--color-accent-bg)] flex items-center justify-center text-[11px] font-semibold text-[var(--color-accent)]">
            {{ roleInitial }}
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[13px] font-medium truncate text-[var(--color-ink)]">{{ roleLabel }}</p>
          </div>
          <button @click="logout" class="p-1.5 rounded-md hover:bg-[var(--color-bg-hover)] transition-colors group" title="退出登录">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-[var(--color-ink-tertiary)] group-hover:text-[var(--color-danger)] transition-colors">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </div>
    </aside>

    <main class="ml-[200px] flex-1 min-h-screen content-bg">
      <RouterView v-slot="{ Component, route }">
        <transition name="liquid-rise" mode="out-in">
          <component :is="Component" :key="route.path" />
        </transition>
      </RouterView>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const roleMap: Record<string, string> = {
  super_admin: "超级管理员",
  domain_expert: "领域专家",
  teacher: "教师",
  student: "学生",
  harness_engineer: "线束工程师",
  system_ops: "系统运维",
};

const roleLabel = computed(() => roleMap[authStore.userRole ?? ""] ?? authStore.userRole ?? "用户");
const roleInitial = computed(() => roleLabel.value.charAt(0));

const navItems = [
  {
    title: "总览",
    route: "/",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>',
  },
  {
    title: "知识库",
    route: "/knowledge",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
  },
  {
    title: "校本资源",
    route: "/resource",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  },
  {
    title: "AI 问答",
    route: "/ai-chat",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    title: "技能编排",
    route: "/skill-editor",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
  },
  {
    title: "系统管理",
    route: "/admin",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 6v6m9-7h-6m-6 0H3m15.36 5.64l-4.24-4.24M9.88 9.88L5.64 5.64m12.72 0l-4.24 4.24M9.88 14.12l-4.24 4.24"/></svg>',
  },
];

function isActive(routePath: string) {
  if (routePath === "/") return route.path === "/";
  return route.path.startsWith(routePath);
}

function logout() {
  authStore.clearAuth();
  router.push("/login");
}
</script>

<style scoped>
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 48px;
  padding: 0 12px;
  border-radius: 12px;
  color: var(--color-ink-secondary);
  font-size: 14px;
  font-weight: 400;
  text-decoration: none;
  transition: all 300ms cubic-bezier(0.34, 1.56, 0.64, 1);
}

.nav-item:hover {
  background: #DBEAFE;
  color: var(--color-ink);
}

.nav-item-active {
  background: #EFF6FF;
  color: var(--color-accent);
  font-weight: 500;
}

.nav-item-active:hover {
  background: #EFF6FF;
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
}

.nav-item-active .nav-icon {
  color: var(--color-accent);
}

.nav-item-active .nav-icon::before {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 8px;
  background: linear-gradient(to top, var(--color-accent-bg) 0%, transparent 60%);
  background-size: 100% 200%;
  animation: liquid-fill 3s ease-in-out infinite;
  z-index: -1;
}

.nav-icon :deep(svg) {
  position: relative;
  z-index: 1;
}

@keyframes liquid-fill {
  0%, 100% { background-position: 0% 100%; }
  50% { background-position: 0% 0%; }
}

.nav-label {
  font-family: var(--font-body);
}

@media (prefers-reduced-motion: reduce) {
  .nav-item-active .nav-icon::before {
    animation: none;
  }
}
</style>
