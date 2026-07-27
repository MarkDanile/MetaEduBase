<template>
  <div class="flex min-h-screen">
    <!-- REQ-060 Slice 4: skip-link（a11y） -->
    <a href="#main-content" class="skip-link">跳到主要内容</a>

    <!-- REQ-060 Slice 4: 移动端 top-bar（<768 显示） -->
    <header
      class="mobile-topbar fixed top-0 left-0 right-0 h-12 flex items-center gap-2 px-3 border-b border-[var(--color-border)] bg-[var(--color-bg-elevated)] z-[calc(var(--z-sidebar)+1)] md:hidden"
    >
      <button
        ref="mobileOpenerRef"
        type="button"
        class="mobile-opener w-9 h-9 rounded-md flex items-center justify-center border border-[var(--color-border)] bg-[var(--color-bg-base)] hover:bg-[var(--color-bg-hover)] cursor-pointer"
        aria-controls="mobile-drawer"
        :aria-expanded="mobileDrawer.open.value"
        :aria-label="mobileDrawer.open.value ? '关闭导航' : '打开导航'"
        @click="mobileDrawer.toggleDrawer()"
      >
        <Menu v-if="!mobileDrawer.open.value" :size="18" :stroke-width="1.5" aria-hidden="true" />
        <X v-else :size="18" :stroke-width="1.5" aria-hidden="true" />
      </button>
      <h1 class="text-[var(--text-body)] font-semibold text-[var(--color-ink)] truncate">
        元知职教基座
      </h1>
    </header>

    <!-- REQ-060 Slice 4: drawer 容器 -->
    <aside
      id="mobile-drawer"
      ref="mobileDrawerRef"
      :class="[
        'sidebar-shell fixed left-0 top-0 bottom-0 flex flex-col z-[var(--z-sidebar)] transition-all duration-300 ease-out',
        desktopCollapsed ? 'md:w-[60px] md:translate-x-0' : 'md:w-[200px] md:translate-x-0',
        mobileDrawer.open.value
          ? 'translate-x-0'
          : '-translate-x-full md:translate-x-0',
      ]"
    >
      <div class="px-4 pt-5 pb-4 flex items-center" :class="desktopCollapsed ? 'md:justify-center' : 'md:gap-2.5'">
        <div class="app-brand-mark">
          <BookOpen :size="16" :stroke-width="2" />
        </div>
        <div v-if="!desktopCollapsed">
          <h1 class="text-[var(--text-body)] font-semibold text-[var(--color-ink)]">元知职教基座</h1>
          <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] -mt-0.5">MetaEduBase</p>
        </div>
      </div>

      <nav
        class="flex-1 px-2 space-y-0.5"
        :aria-label="mobileDrawer.open.value ? '主导航（已展开）' : '主导航'"
        @keydown="mobileDrawer.onDrawerKeydown"
      >
        <!-- REQ-060 Slice 3: 从 Route Record 投影导航（统一 section 分组） -->
        <div
          v-for="section in navSections"
          :key="section.id"
          class="nav-section"
        >
          <p v-if="!desktopCollapsed" class="nav-section-label">{{ section.label }}</p>
          <RouterLink
            v-for="item in section.items"
            :key="item.name"
            :to="{ name: item.name }"
            class="nav-item"
            :class="{
              'nav-item-active': isActive(item.name),
              'nav-item-collapsed': desktopCollapsed,
            }"
            :title="desktopCollapsed ? item.title : undefined"
            :aria-label="item.title"
            :aria-current="isActive(item.name) ? 'page' : undefined"
          >
            <div class="nav-icon">
              <component :is="item.icon" v-if="item.icon" :size="desktopCollapsed ? 20 : 18" :stroke-width="1.5" />
            </div>
            <span v-if="!desktopCollapsed" class="nav-label">{{ item.title }}</span>
          </RouterLink>
        </div>
      </nav>

      <div class="relative px-2 pb-3 pt-3 border-t border-[var(--color-border)]">
        <button
          @click="userMenuOpen = !userMenuOpen"
          class="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-[var(--color-bg-hover)] transition-colors cursor-pointer border-none bg-none"
          :class="desktopCollapsed ? 'md:justify-center' : ''"
          :aria-label="roleLabel"
          :aria-expanded="userMenuOpen"
          aria-haspopup="menu"
        >
          <div class="w-7 h-7 rounded-full bg-[var(--color-accent-bg)] flex items-center justify-center text-[var(--text-micro)] font-semibold text-[var(--color-accent)] flex-shrink-0">
            {{ roleInitial }}
          </div>
          <div v-if="!desktopCollapsed" class="flex-1 min-w-0 text-left">
            <p class="font-medium truncate text-[var(--text-caption)] text-[var(--color-ink)]">{{ roleLabel }}</p>
          </div>
          <ChevronUp
            v-if="!desktopCollapsed"
            :size="12"
            :stroke-width="2"
            class="text-[var(--color-ink-tertiary)] transition-transform duration-200"
            :class="{ 'rotate-180': !userMenuOpen }"
          />
        </button>

        <div
          v-if="userMenuOpen"
          class="absolute left-0 bottom-full mb-2 min-w-48 bg-[var(--surface-dialog-bg)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-[var(--surface-dialog-shadow)] p-2 z-[var(--z-dialog)]"
          :style="{ backdropFilter: 'var(--surface-glass-blur)', WebkitBackdropFilter: 'var(--surface-glass-blur)' }"
          role="menu"
        >
          <button class="user-menu-item" role="menuitem" @click="userMenuOpen = false">
            <User :size="15" :stroke-width="1.5" />
            个人中心
          </button>

          <button class="user-menu-item" role="menuitem" @click="toggleTheme">
            <component :is="themeIcon" :size="15" :stroke-width="1.5" />
            {{ themeLabel }}
          </button>

          <div class="user-menu-divider"></div>
          <button class="user-menu-item user-menu-item-danger" role="menuitem" @click="logout">
            <LogOut :size="15" :stroke-width="1.5" />
            退出登录
          </button>
        </div>

        <div
          v-if="userMenuOpen"
          class="fixed inset-0 z-[calc(var(--z-dialog)-1)]"
          @click="userMenuOpen = false"
        />
      </div>

      <!-- REQ-060 Slice 4: 桌面端 collapse toggle（仅 md+ 显示） -->
      <button
        v-show="!mobileDrawer.open.value"
        @click="desktopCollapsed = !desktopCollapsed"
        class="desktop-collapse-toggle absolute -right-3 top-7 w-6 h-6 rounded-full bg-[var(--color-bg-elevated)] border border-[var(--color-border)] shadow-sm flex items-center justify-center hover:bg-[var(--color-accent-bg)] transition-colors hidden md:flex"
        :aria-label="desktopCollapsed ? '展开侧边栏' : '折叠侧边栏'"
        :aria-expanded="!desktopCollapsed"
      >
        <ChevronLeft :size="10" :stroke-width="2" class="text-[var(--color-ink-secondary)] transition-transform duration-300" :class="{ 'rotate-180': desktopCollapsed }" />
      </button>
    </aside>

    <!-- REQ-060 Slice 4: drawer backdrop（drawer 打开时） -->
    <div
      v-if="mobileDrawer.open.value"
      class="drawer-backdrop fixed inset-0 bg-black/40 z-[calc(var(--z-sidebar)-1)] md:hidden"
      data-testid="drawer-backdrop"
      @click="mobileDrawer.closeDrawer()"
    />

    <main
      id="main-content"
      tabindex="-1"
      class="flex-1 min-h-screen transition-all duration-300 ease-out"
      :class="[mainMarginClass, mobileDrawer.open.value ? 'md:ml-[200px]' : ''].join(' ')"
    >
      <div class="ui-page-shell pt-12 md:pt-0">
        <!-- REQ-060 Slice 3 收口：全局 Breadcrumb（route.matched -> meta.title 链） -->
        <NavBreadcrumb />
        <RouterView v-slot="{ Component: RouteComponent, route: currentRoute }">
          <transition name="liquid-rise" mode="out-in">
            <component :is="RouteComponent" :key="currentRoute.path" />
          </transition>
        </RouterView>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useThemeStore } from "@/stores/theme";
import { roleMap } from "@/constants/maps";
import {
  BookOpen,
  LogOut,
  ChevronLeft,
  ChevronUp,
  Menu,
  User,
  Moon,
  Sun,
  X,
} from "lucide-vue-next";
import {
  projectNavigation,
  loadFeatureFlags,
  type NavSectionProjection,
} from "@/app/nav";
import NavBreadcrumb from "@/components/NavBreadcrumb.vue";
import { useMobileDrawer } from "@/composables/useMobileDrawer";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const themeStore = useThemeStore();

// REQ-060 Slice 4: 桌面端折叠与移动端 drawer 独立状态。
// 旧实现：单一 `collapsed` 混用 desktop/mobile，导致窄屏折叠态无法打开。
const desktopCollapsed = ref(false);
const mobileOpenerRef = ref<HTMLElement | null>(null);
const mobileDrawerRef = ref<HTMLElement | null>(null);
const mobileDrawer = useMobileDrawer({
  // eslint-disable-next-line vue/no-ref-as-operand
  openerRef: mobileOpenerRef,
  // eslint-disable-next-line vue/no-ref-as-operand
  drawerRef: mobileDrawerRef,
  route,
});
const userMenuOpen = ref(false);

const roleLabel = computed(() => roleMap[authStore.userRole ?? ""] ?? authStore.userRole ?? "用户");
const roleInitial = computed(() => roleLabel.value.charAt(0));
const themeLabel = computed(() => (themeStore.activeTheme === "dark" ? "切换浅色" : "切换深色"));
const themeIcon = computed(() => (themeStore.activeTheme === "dark" ? Sun : Moon));

// REQ-060 Slice 3: 从 Route Record 投影导航（删 navItems/adminItems/aiAppItems 三份数组）
// 复用 nav.ts#loadFeatureFlags（唯一运行时来源，防 flag key 漂移）
const navSections = computed<NavSectionProjection[]>(() => {
  return projectNavigation(router.getRoutes(), {
    role: authStore.userRole,
    featureFlags: loadFeatureFlags(),
  });
});

// REQ-060 Slice 3: 精确高亮 -- 比较 current.meta.activeNav ?? current.name，禁止 path startsWith
function isActive(itemName: string) {
  const activeNav = route.meta.activeNav ?? (typeof route.name === "string" ? route.name : "");
  return activeNav === itemName;
}

const mainMarginClass = computed(() => {
  // 桌面端（>=768）：随 desktopCollapsed 调整左边距
  // 移动端（<768）：drawer 打开时 aside translate-x-0 但不影响 main layout
  //              （main 始终 ml-0，drawer 覆盖在 main 上方）
  if (typeof window !== "undefined" && window.innerWidth >= 768) {
    return desktopCollapsed.value ? "md:ml-[60px]" : "md:ml-[200px]";
  }
  return "";
});

function logout() {
  authStore.clearAuth();
  router.push("/login");
}

function toggleTheme() {
  themeStore.toggleTheme();
  userMenuOpen.value = false;
}

// REQ-060 Slice 4: 桌面端 resize 时自动折叠（保持旧 UX），不动 drawer 状态
function handleResize() {
  if (window.innerWidth < 768) {
    desktopCollapsed.value = true;
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
/* REQ-060 Slice 4: skip-link 视觉隐藏 + focus 显示 */
.skip-link {
  position: absolute;
  top: -40px;
  left: 8px;
  z-index: 9999;
  padding: 8px 12px;
  background: var(--color-accent);
  color: white;
  font-size: var(--text-caption);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition: top 150ms ease-out;
}
.skip-link:focus,
.skip-link:focus-visible {
  top: 8px;
  outline: 2px solid var(--color-ink);
  outline-offset: 2px;
}

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

/* REQ-060 Slice 4: prefers-reduced-motion 取消所有过渡 */
@media (prefers-reduced-motion: reduce) {
  .sidebar-shell,
  .nav-item,
  .user-menu-item,
  .skip-link {
    transition: none !important;
  }
}

.nav-section {
  margin-bottom: 4px;
}

.nav-section-label {
  padding: 8px 12px 4px;
  font-size: var(--text-micro);
  color: var(--color-ink-tertiary);
  text-transform: uppercase;
  letter-spacing: 0;
  margin: 0;
}
</style>