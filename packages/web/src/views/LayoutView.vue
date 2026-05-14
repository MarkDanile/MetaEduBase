<template>
  <div class="flex min-h-screen">
    <aside
      class="sidebar-shell fixed left-0 top-0 bottom-0 flex flex-col z-[var(--z-sidebar)] transition-all duration-300 ease-out"
      :class="collapsed ? 'w-[60px]' : 'w-[200px]'"
    >
      <div class="px-4 pt-5 pb-4 flex items-center" :class="collapsed ? 'justify-center' : 'gap-2.5'">
        <div class="w-8 h-8 rounded-lg bg-[var(--color-accent)] flex items-center justify-center flex-shrink-0">
          <BookOpen :size="16" color="white" :stroke-width="2" />
        </div>
        <div v-if="!collapsed">
          <h1 class="text-[14px] font-semibold tracking-tight text-[var(--color-ink)]" style="letter-spacing:-0.3px">元知职教基座</h1>
          <p class="text-[10px] text-[var(--color-ink-tertiary)] -mt-0.5">MetaEduBase</p>
        </div>
      </div>

      <nav class="flex-1 px-2 space-y-0.5">
        <RouterLink
          v-for="item in navItems"
          :key="item.route"
          :to="item.route"
          class="nav-item"
          :class="{ 'nav-item-active': isActive(item.route), 'nav-item-collapsed': collapsed }"
          :title="collapsed ? item.title : undefined"
        >
          <div class="nav-icon">
            <component :is="item.icon" :size="18" :stroke-width="1.5" />
          </div>
          <span v-if="!collapsed" class="nav-label">{{ item.title }}</span>
        </RouterLink>
      </nav>

      <div class="px-2 pb-3 pt-3 border-t border-[var(--color-border)]">
        <div class="flex items-center gap-2 px-2" :class="collapsed ? 'justify-center' : ''">
          <div class="w-7 h-7 rounded-full bg-[var(--color-accent-bg)] flex items-center justify-center text-[11px] font-semibold text-[var(--color-accent)] flex-shrink-0">
            {{ roleInitial }}
          </div>
          <div v-if="!collapsed" class="flex-1 min-w-0">
            <p class="text-[13px] font-medium truncate text-[var(--color-ink)]">{{ roleLabel }}</p>
          </div>
          <button v-if="!collapsed" @click="logout" class="p-1.5 rounded-md hover:bg-[var(--color-bg-hover)] transition-colors group" title="退出登录" aria-label="退出登录">
            <LogOut :size="14" :stroke-width="1.5" class="text-[var(--color-ink-tertiary)] group-hover:text-[var(--color-danger)] transition-colors" />
          </button>
        </div>
      </div>

      <button
        @click="collapsed = !collapsed"
        class="absolute -right-3 top-7 w-6 h-6 rounded-full bg-[var(--color-bg-elevated)] border border-[var(--color-border)] shadow-sm flex items-center justify-center hover:bg-[var(--color-accent-bg)] transition-colors"
        :aria-label="collapsed ? '展开侧边栏' : '折叠侧边栏'"
      >
        <ChevronLeft :size="10" :stroke-width="2" class="text-[var(--color-ink-secondary)] transition-transform duration-300" :class="{ 'rotate-180': collapsed }" />
      </button>
    </aside>

    <main
      id="main-content"
      class="flex-1 min-h-screen content-bg transition-all duration-300 ease-out"
      :class="collapsed ? 'ml-[60px]' : 'ml-[200px]'"
    >
      <RouterView v-slot="{ Component, route }">
        <transition name="liquid-rise" mode="out-in">
          <component :is="Component" :key="route.path" />
        </transition>
      </RouterView>
    </main>

    <div
      v-if="mobileMenuOpen"
      class="fixed inset-0 bg-black/20 z-[var(--z-sidebar)] md:hidden"
      @click="mobileMenuOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, type Component } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { roleMap } from "@/constants/maps";
import {
  BookOpen,
  LayoutGrid,
  Upload,
  MessageSquare,
  Settings,
  LogOut,
  ChevronLeft,
  Cog,
} from "lucide-vue-next";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const collapsed = ref(false);
const mobileMenuOpen = ref(false);

const roleLabel = computed(() => roleMap[authStore.userRole ?? ""] ?? authStore.userRole ?? "用户");
const roleInitial = computed(() => roleLabel.value.charAt(0));

const navItems: { title: string; route: string; icon: Component }[] = [
  { title: "总览", route: "/", icon: LayoutGrid },
  { title: "知识库", route: "/knowledge", icon: BookOpen },
  { title: "校本资源", route: "/resource", icon: Upload },
  { title: "AI 问答", route: "/ai-chat", icon: MessageSquare },
  { title: "技能编排", route: "/skill-editor", icon: Settings },
  { title: "系统管理", route: "/admin", icon: Cog },
];

function isActive(routePath: string) {
  if (routePath === "/") return route.path === "/";
  return route.path.startsWith(routePath);
}

function logout() {
  authStore.clearAuth();
  router.push("/login");
}

function handleResize() {
  if (window.innerWidth < 768) {
    collapsed.value = true;
  }
}

onMounted(() => {
  handleResize();
  window.addEventListener("resize", handleResize);
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
});
</script>

<style scoped>
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 44px;
  padding: 0 12px;
  border-radius: 10px;
  color: var(--color-ink-secondary);
  font-size: 14px;
  font-weight: 400;
  text-decoration: none;
  transition: all 300ms cubic-bezier(0.34, 1.56, 0.64, 1);
  overflow: hidden;
  white-space: nowrap;
}

.nav-item-collapsed {
  justify-content: center;
  padding: 0;
}

.nav-item:hover {
  background: var(--color-accent-glow);
  color: var(--color-ink);
}

.nav-item-active {
  background: var(--color-accent-bg);
  color: var(--color-accent);
  font-weight: 500;
}

.nav-item-active:hover {
  background: var(--color-accent-bg);
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

@keyframes liquid-fill {
  0%, 100% { background-position: 0% 100%; }
  50% { background-position: 0% 0%; }
}

@media (max-width: 640px) {
  aside {
    transform: translateX(-100%);
  }
  main {
    margin-left: 0 !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  .nav-item-active .nav-icon::before {
    animation: none;
  }
}
</style>
