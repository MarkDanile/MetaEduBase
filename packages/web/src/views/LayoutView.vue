<template>
  <div class="flex min-h-screen">
    <aside
      class="sidebar-shell fixed left-0 top-0 bottom-0 flex flex-col z-[var(--z-sidebar)] transition-all duration-300 ease-out"
      :class="collapsed ? 'w-[60px]' : 'w-[200px]'"
    >
      <div class="px-4 pt-5 pb-4 flex items-center" :class="collapsed ? 'justify-center' : 'gap-2.5'">
        <div class="app-brand-mark">
          <BookOpen :size="16" :stroke-width="2" />
        </div>
        <div v-if="!collapsed">
          <h1 class="text-[var(--text-body)] font-semibold text-[var(--color-ink)]">元知职教基座</h1>
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

        <!-- AI Apps submenu -->
        <div class="nav-admin-section">
          <button
            class="nav-item nav-item-admin"
            :class="{ 'nav-item-collapsed': collapsed }"
            @click="appsExpanded = !appsExpanded"
            :title="collapsed ? 'AI 应用' : undefined"
          >
            <div class="nav-icon">
              <Bot :size="18" :stroke-width="1.5" />
            </div>
            <span v-if="!collapsed" class="nav-label flex-1">AI 应用</span>
            <ChevronDown
              v-if="!collapsed"
              :size="14"
              :class="{ 'rotate-180': appsExpanded }"
              class="text-[var(--color-ink-tertiary)] transition-transform"
            />
          </button>
          <div v-if="appsExpanded && !collapsed" class="nav-admin-subitems">
            <RouterLink
              v-for="item in aiAppItems"
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

          <button class="user-menu-item" @click="toggleTheme">
            <component :is="themeIcon" :size="15" :stroke-width="1.5" />
            {{ themeLabel }}
          </button>

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
import { useThemeStore } from "@/stores/theme";
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
  Bot,
  ChevronDown,
  Moon,
  Sun,
  Plug,
  Workflow,
} from "lucide-vue-next";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const themeStore = useThemeStore();
const collapsed = ref(false);
const mobileMenuOpen = ref(false);
const menuOpen = ref(false);

const roleLabel = computed(() => roleMap[authStore.userRole ?? ""] ?? authStore.userRole ?? "用户");
const roleInitial = computed(() => roleLabel.value.charAt(0));
const themeLabel = computed(() => (themeStore.activeTheme === "dark" ? "切换浅色" : "切换深色"));
const themeIcon = computed(() => (themeStore.activeTheme === "dark" ? Sun : Moon));

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
  { title: "MCP 服务", route: "/admin/mcp-servers", icon: Plug },
  { title: "Skill 服务", route: "/admin/skills", icon: Workflow },
];

const adminExpanded = ref(false);
const appsExpanded = ref(false);

const aiAppItems = [
  { title: "应用广场", route: "/ai-apps", icon: Bot },
  { title: "应用管理", route: "/ai-apps/admin", icon: Bot },
];

function isActive(routePath: string) {
  if (routePath === "/") return route.path === "/";
  return route.path.startsWith(routePath);
}

function logout() {
  authStore.clearAuth();
  router.push("/login");
}

function toggleTheme() {
  themeStore.toggleTheme();
  menuOpen.value = false;
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
  height: 40px;
  padding: 0 12px;
  border-radius: var(--radius-md);
  color: var(--color-ink-secondary);
  font-size: 14px;
  font-weight: 400;
  text-decoration: none;
  transition: background-color var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out);
  overflow: hidden;
  white-space: nowrap;
}

.nav-item-collapsed {
  justify-content: center;
  padding: 0;
}

.nav-item:hover {
  background: var(--color-bg-hover);
  color: var(--color-ink);
}

.nav-item-active {
  background: var(--color-accent-bg);
  color: var(--color-ink);
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
  color: var(--color-ink);
}

@media (max-width: 640px) {
  aside {
    transform: translateX(-100%);
  }
  main {
    margin-left: 0 !important;
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
  border-left: 1px solid var(--color-border-subtle);
}

.nav-item-sub {
  height: 38px !important;
  padding-left: 12px !important;
}

.nav-item-sub .nav-icon {
  opacity: 0.7;
}
</style>
