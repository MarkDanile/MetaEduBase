/**
 * REQ-060 Slice 4: 移动端 off-canvas drawer 状态机。
 *
 * 封装焦点管理、body scroll lock、Escape 关闭、route change 关闭逻辑。
 * 不引入新依赖（focus-trap 等），手写 Tab/Shift+Tab 循环焦点。
 *
 * 设计：
 * - openerRef: 触发 drawer 打开的按钮（用于关闭后焦点返回）
 * - drawerRef: drawer 容器（用于查找 data-autofocus 元素）
 * - state: open (bool) — 单一事实源，drawer 与 aria-expanded 同步
 * - openDrawer: 设 true + body scroll lock + nextTick 把焦点移到 data-autofocus
 * - closeDrawer: 设 false + 恢复 scroll + 返回焦点到 opener（除非 returnFocus=false）
 * - onEscape: document keydown 监听（drawer focus 内或外都生效）
 * - onRouteChange: LayoutView 通过 watch(route, ...) 调用（不绑定 router.afterEach 全局副作用）
 *
 * a11y:
 * - body scroll lock 不依赖 fixed/overflow 之外的方式
 * - focus 回到 opener 时调用 openerRef.value.focus()（不调用 click 避免触发 toggle）
 * - Escape 关闭时 preventDefault 避免冒泡到其他组件
 */
import { ref, nextTick, onMounted, onUnmounted, watch, toRef, type Ref, type MaybeRef } from "vue";
import { useRoute, type RouteLocationNormalizedLoaded } from "vue-router";

export interface UseMobileDrawerOptions {
  /** 触发 drawer 打开的按钮元素（ref 或 getter）。关闭后焦点返回。 */
  openerRef: MaybeRef<HTMLElement | null>;
  /** drawer 容器 ref；用于查找 data-autofocus 元素。 */
  drawerRef: MaybeRef<HTMLElement | null>;
  /**
   * 可选：注入 route 用于监听 route change 关闭 drawer。
   * 默认用 vue-router 的 `useRoute()`；测试时可传 mock route。
   * 传 `null` 禁用 route change 关闭。
   */
  route?: RouteLocationNormalizedLoaded | null | Ref<RouteLocationNormalizedLoaded | null>;
}

export interface UseMobileDrawerReturn {
  open: Ref<boolean>;
  openDrawer: () => void;
  closeDrawer: (returnFocus?: boolean) => void;
  toggleDrawer: () => void;
  /** 处理 drawer 内 Tab/Shift+Tab 焦点循环。drawer 打开时由 LayoutView 在 nav 上挂 keydown 监听调用。 */
  onDrawerKeydown: (e: KeyboardEvent) => void;
}

export function useMobileDrawer(opts: UseMobileDrawerOptions): UseMobileDrawerReturn {
  const openerRefResolved = toRef(opts.openerRef);
  const drawerRefResolved = toRef(opts.drawerRef);
  const { route: routeOpt } = opts;
  const open = ref(false);

  function lockBody() {
    document.body.style.overflow = "hidden";
  }
  function unlockBody() {
    document.body.style.overflow = "";
  }

  function openDrawer() {
    if (open.value) return;
    open.value = true;
    lockBody();
    nextTick(() => {
      const drawer = drawerRefResolved.value;
      if (!drawer) return;
      const target =
        drawer.querySelector<HTMLElement>("[data-autofocus]") ??
        drawer.querySelector<HTMLElement>(
          "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])",
        );
      target?.focus();
    });
  }

  function closeDrawer(returnFocus = true) {
    if (!open.value) return;
    open.value = false;
    unlockBody();
    if (returnFocus) {
      // 调用 .focus() 而不是 .click()，避免触发 toggle 重新打开
      nextTick(() => openerRefResolved.value?.focus());
    }
  }

  function toggleDrawer() {
    if (open.value) closeDrawer();
    else openDrawer();
  }

  function onDocumentKeydown(e: KeyboardEvent) {
    if (e.key === "Escape" && open.value) {
      e.preventDefault();
      e.stopPropagation();
      closeDrawer();
    }
  }

  /**
   * Drawer 内 keydown 处理：Tab/Shift+Tab 在 drawer 内容里循环焦点。
   * 外部 LayoutView 在 `<aside>` 上挂 keydown 监听，命中后调用本函数。
   *
   * 可见性过滤：排除 CSS display:none / visibility:hidden / hidden 属性
   * 的元素（如桌面端折叠按钮在移动端被 `hidden md:flex` 隐藏）。
   * 同时排除带 `data-desktop-only` 标记的元素（桌面端专属控件）。
   *
   * active 不在 focusables 中的处理（P1 修订）：
   * - 初始焦点可能在 `tabindex="-1"` 的 data-autofocus 元素上（不在 focusables 中）
   * - Tab (forward): 定向到 first
   * - Shift+Tab (backward): 定向到 last
   * - 这样从 data-autofocus 按 Tab 进入循环，按 Shift+Tab 也不会逃出
   */
  function onDrawerKeydown(e: KeyboardEvent) {
    if (!open.value) return;
    if (e.key !== "Tab") return;
    const drawer = drawerRefResolved.value;
    if (!drawer) return;
    const candidates = drawer.querySelectorAll<HTMLElement>(
      "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
    );
    const focusables = Array.from(candidates).filter((el) => {
      if (el.hasAttribute("data-desktop-only")) return false;
      if (el.hidden) return false;
      const style = getComputedStyle(el);
      if (style.display === "none") return false;
      if (style.visibility === "hidden") return false;
      return true;
    });
    if (focusables.length === 0) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    const active = document.activeElement as HTMLElement | null;
    const activeIndex = active ? focusables.indexOf(active) : -1;

    if (e.shiftKey) {
      // Shift+Tab: 如果 active 是 first 或不在 focusables 中，定向到 last
      if (activeIndex <= 0) {
        e.preventDefault();
        last.focus();
      }
    } else {
      // Tab: 如果 active 是 last 或不在 focusables 中，定向到 first
      if (activeIndex === -1 || activeIndex === focusables.length - 1) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  // route change 关闭（route 是 reactive from vue-router）
  // 三态：undefined = 注入；null = 禁用；route = 直接用
  if (routeOpt !== null) {
    let routeRef: Ref<RouteLocationNormalizedLoaded | null> | null = null;
    if (routeOpt && typeof routeOpt === "object" && "value" in routeOpt) {
      routeRef = routeOpt as Ref<RouteLocationNormalizedLoaded | null>;
    } else if (routeOpt) {
      routeRef = ref(routeOpt as RouteLocationNormalizedLoaded);
    } else {
      // 注入 undefined = 用 vue-router 的 useRoute()
      try {
        const r = useRoute();
        routeRef = ref(r) as Ref<RouteLocationNormalizedLoaded | null>;
      } catch {
        // useRoute 在无 router context 下抛错；忽略
      }
    }
    if (routeRef) {
      watch(
        () => routeRef!.value?.fullPath,
        (next: string | undefined) => {
          if (open.value && next !== undefined) closeDrawer(false);
        },
      );
    }
  }

  onMounted(() => {
    document.addEventListener("keydown", onDocumentKeydown);
  });
  onUnmounted(() => {
    document.removeEventListener("keydown", onDocumentKeydown);
    // 防御性清理：组件卸载时若 drawer 仍 open，恢复 body scroll
    if (open.value) unlockBody();
  });

  return { open, openDrawer, closeDrawer, toggleDrawer, onDrawerKeydown };
}