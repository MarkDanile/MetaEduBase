<template>
  <div class="flex min-h-screen">
    <aside class="fixed left-0 top-0 bottom-0 w-[260px] glass-heavy flex flex-col z-10">
      <div class="px-6 pt-7 pb-6">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-[var(--radius-md)] bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-accent-light)] flex items-center justify-center">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
            </svg>
          </div>
          <div>
            <h1 class="text-base font-semibold tracking-tight" style="font-family: var(--font-display)">MetaEduBase</h1>
            <p class="text-[11px] text-[var(--color-ink-tertiary)] -mt-0.5">元知职教基座</p>
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

      <div class="px-4 pb-6 pt-4 border-t border-[var(--color-glass-border-subtle)]">
        <div class="flex items-center gap-3 px-2">
          <div class="w-8 h-8 rounded-full bg-gradient-to-br from-[var(--color-bg-mesh-1)] to-[var(--color-bg-mesh-2)] flex items-center justify-center text-xs font-semibold text-[var(--color-accent)]">
            {{ roleInitial }}
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium truncate">{{ roleLabel }}</p>
            <p class="text-[11px] text-[var(--color-ink-tertiary)]">在线</p>
          </div>
          <button @click="logout" class="p-1.5 rounded-lg hover:bg-[var(--color-glass)] transition-colors group" title="退出登录">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="group-hover:stroke-[var(--color-danger)] transition-colors">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
          </button>
        </div>
      </div>
    </aside>

    <main class="ml-[260px] flex-1 min-h-screen">
      <RouterView />
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
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>',
  },
  {
    title: "知识库",
    route: "/knowledge",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
  },
  {
    title: "校本资源",
    route: "/resource",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  },
  {
    title: "AI 助教",
    route: "/ai-chat",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    title: "Skill 编排",
    route: "/skill-editor",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
  },
  {
    title: "系统管理",
    route: "/admin",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 6v6m9-7h-6m-6 0H3m15.36 5.64l-4.24-4.24M9.88 9.88L5.64 5.64m12.72 0l-4.24 4.24M9.88 14.12l-4.24 4.24"/></svg>',
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
  gap: 10px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  color: var(--color-ink-secondary);
  font-size: 14px;
  font-weight: 450;
  text-decoration: none;
  transition: all var(--duration-normal) var(--ease-liquid);
}

.nav-item:hover {
  background: var(--color-glass);
  color: var(--color-ink);
}

.nav-item-active {
  background: var(--color-accent-bg) !important;
  color: var(--color-accent) !important;
  font-weight: 550;
}

.nav-item-active .nav-icon {
  color: var(--color-accent);
}

.nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--color-ink-tertiary);
  transition: color var(--duration-fast) var(--ease-liquid);
}

.nav-item:hover .nav-icon {
  color: var(--color-ink-secondary);
}

.nav-label {
  font-family: var(--font-body);
  letter-spacing: -0.01em;
}
</style>
