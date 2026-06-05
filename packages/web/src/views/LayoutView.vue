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
          <h1 class="text-[var(--text-body)] font-semibold tracking-tight text-[var(--color-ink)]" style="letter-spacing:-0.3px">元知职教基座</h1>
          <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] -mt-0.5">MetaEduBase</p>
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

        <!-- Admin submenu -->
        <div class="nav-admin-section">
          <button
            class="nav-item nav-item-admin"
            :class="{ 'nav-item-collapsed': collapsed }"
            @click="adminExpanded = !adminExpanded"
            :title="collapsed ? '系统管理' : undefined"
          >
            <div class="nav-icon">
              <Cog :size="18" :stroke-width="1.5" />
            </div>
            <span v-if="!collapsed" class="nav-label flex-1">系统管理</span>
            <ChevronDown
              v-if="!collapsed"
              :size="14"
              :class="{ 'rotate-180': adminExpanded }"
              class="text-[var(--color-ink-tertiary)] transition-transform"
            />
          </button>
          <div v-if="adminExpanded && !collapsed" class="nav-admin-subitems">
            <RouterLink
              v-for="item in adminItems"
              :key="item.route"
              :to="item.route"
              class="nav-item nav-item-sub"
              :class="{ 'nav-item-active': isActive(item.route) }"
            >
              <div class="nav-icon">
                <component :is="item.icon" :size="16" :stroke-width="1.5" />
              </div>
              <span class="nav-label">{{ item.title }}</span>
            </RouterLink>
          </div>
        </div>
      </nav>

      <div class="relative px-2 pb-3 pt-3 border-t border-[var(--color-border)]">
        <button
          @click="menuOpen = !menuOpen"
          class="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors cursor-pointer border-none bg-none"
          :class="collapsed ? 'justify-center' : ''"
          :aria-label="roleLabel"
        >
          <div class="w-7 h-7 rounded-full bg-[var(--color-accent-bg)] flex items-center justify-center text-[var(--text-micro)] font-semibold text-[var(--color-accent)] flex-shrink-0">
            {{ roleInitial }}
          </div>
          <div v-if="!collapsed" class="flex-1 min-w-0 text-left">
            <p class="font-medium truncate text-[var(--text-caption)] text-[var(--color-ink)]">{{ roleLabel }}</p>
          </div>
          <ChevronUp
            v-if="!collapsed"
            :size="12"
            :stroke-width="2"
            class="text-[var(--color-ink-tertiary)] transition-transform duration-200"
            :class="{ 'rotate-180': !menuOpen }"
          />
        </button>

        <div
          v-if="menuOpen"
          class="absolute left-0 bottom-full mb-2 min-w-48 bg-[var(--surface-dialog-bg)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--surface-dialog-shadow)] p-2 z-[var(--z-dialog)]"
          :style="{ backdropFilter: 'var(--surface-glass-blur)', WebkitBackdropFilter: 'var(--surface-glass-blur)' }"
        >
          <button class="user-menu-item" @click="menuOpen = false">
            <User :size="15" :stroke-width="1.5" />
            个人中心
          </button>

          <div class="user-menu-divider"></div>
          <p class="user-menu-label">主题</p>
          <div class="flex gap-1 px-1">
            <button
              v-for="t in themes"
              :key="t.id"
              @click="themeStore.setTheme(t.id)"
              class="flex-1 h-7 rounded-[var(--radius-sm)] text-[10px] font-normal transition-all duration-200 border cursor-pointer"
              :class="themeStore.activeTheme === t.id
                ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                : 'border-[var(--color-border-subtle)] text-[var(--color-ink-tertiary)] hover:border-[var(--color-border)] hover:text-[var(--color-ink-secondary)]'"
            >
              {{ t.shortLabel }}
            </button>
          </div>

          <div class="user-menu-divider"></div>
          <button class="user-menu-item user-menu-item-danger" @click="logout">
            <LogOut :size="15" :stroke-width="1.5" />
            退出登录
          </button>
        </div>

        <div
          v-if="menuOpen"
          class="fixed inset-0 z-[calc(var(--z-dialog)-1)]"
          @click="menuOpen = false"
        />
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
      class="flex-1 min-h-screen transition-all duration-300 ease-out"
      :class="collapsed ? 'ml-[60px]' : 'ml-[200px]'"
    >
      <div class="ui-page-shell">
        <RouterView v-slot="{ Component: RouteComponent, route: currentRoute }">
          <transition name="liquid-rise" mode="out-in">
            <component :is="RouteComponent" :key="currentRoute.path" />
          </transition>
        </RouterView>
      </div>
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
  Database,
  FolderOpen,
  LayoutGrid,
  MessageSquare,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronUp,
  Cog,
  User,
  LayoutTemplate,
} from "lucide-vue-next";
import { useThemeStore, type ThemeId } from "@/stores/theme";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const themeStore = useThemeStore();
const collapsed = ref(false);
const mobileMenuOpen = ref(false);
const menuOpen = ref(false);

const themes: { id: ThemeId; label: string; shortLabel: string }[] = [
  { id: "liquid", label: "液态玻璃", shortLabel: "液态" },
  { id: "ink", label: "墨韵书香", shortLabel: "墨韵" },
  { id: "navy", label: "沉稳奢华", shortLabel: "奢华" },
  { id: "notion", label: "Notion", shortLabel: "N" },
];

const roleLabel = computed(() => roleMap[authStore.userRole ?? ""] ?? authStore.userRole ?? "用户");
const roleInitial = computed(() => roleLabel.value.charAt(0));

const navItems: { title: string; route: string; icon: Component }[] = [
  { title: "总览", route: "/", icon: LayoutGrid },
  { title: "知识库", route: "/knowledge", icon: BookOpen },
  { title: "资源库", route: "/resource", icon: FolderOpen },
  { title: "数据库", route: "/database", icon: Database },
  { title: "AI 问答", route: "/ai-chat", icon: MessageSquare },
  { title: "技能编排", route: "/skill-editor", icon: Settings },
];

const adminItems = [
  { title: "数据要素模板", route: "/admin/template", icon: LayoutTemplate },
];

const adminExpanded = ref(false);

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
.user-menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  border-radius: var(--radius-md);
  font-size: var(--text-caption);
  color: var(--color-ink-secondary);
  cursor: pointer;
  font-family: var(--font-body);
  transition: all var(--duration-fast) var(--ease-out);
}

.user-menu-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-ink);
}

.user-menu-item-danger {
  color: var(--color-danger);
}

.user-menu-item-danger:hover {
  background: rgba(239, 68, 68, 0.06);
  color: var(--color-danger);
}

.user-menu-divider {
  height: 1px;
  margin: 4px 4px;
  background: var(--color-border-subtle);
}

.user-menu-label {
  padding: 4px 12px 6px;
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

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

.nav-admin-section {
  margin-top: 2px;
}

.nav-item-admin {
  justify-content: flex-start !important;
}

.nav-admin-subitems {
  margin-left: 8px;
  padding-left: 8px;
  border-left: 1px solid var(--panel-border);
}

.nav-item-sub {
  height: 38px !important;
  padding-left: 12px !important;
}

.nav-item-sub .nav-icon {
  opacity: 0.7;
}
</style>
