/**
 * REQ-060 Slice 3: LayoutView 单元测试 -- 覆盖 Slice 3 review 反馈的 4 项契约。
 *
 * 测试维度：
 * 1. 角色过滤：低权角色看不到 capabilities/system；高权角色能看到
 * 2. 折叠态图标可见：collapsed=true 时图标仍然渲染（图标 + aria-label 保留）
 * 3. activeNav 唯一高亮：基于 route.meta.activeNav 恰好一个 section 被高亮
 * 4. 可见 route 全有 icon：每个 .nav-item 内的 .nav-icon 必含可渲染图标组件
 *
 * 测试隔离：每个 case fresh Pinia + stub localStorage（auth + feature flag）。
 * LayoutView 直接 import RouterView/RouterLink；为避免子路由触发 axios 401，
 * 这里 stub RouterView/RouterLink 为最小占位（仅渲染 slot / children）。
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h, nextTick } from "vue";
import LayoutView from "./LayoutView.vue";
import { useThemeStore } from "@/stores/theme";

// localStorage stub（隔离 auth + feature flag 状态）
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();
// 用 defineProperty 覆盖 window.localStorage（每个 spec file 自带隔离；
// jsdom 默认 localStorage 也存在，但为了 auth role/feature flag 显式可观察，
// 我们替换为 fresh mock）。这与 router.spec.ts / nav.spec.ts 同源约定。
Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  configurable: true,
  writable: true,
});

function setAuth(role: string | null) {
  if (role) {
    localStorageMock.setItem("metaedu_token", "fake");
    localStorageMock.setItem("metaedu_role", role);
    localStorageMock.setItem("metaedu_tenant_id", "t1");
  } else {
    localStorageMock.removeItem("metaedu_token");
    localStorageMock.removeItem("metaedu_role");
    localStorageMock.removeItem("metaedu_tenant_id");
  }
}

beforeEach(() => {
  localStorageMock.clear();
  document.body.innerHTML = "";
});

afterEach(() => {
  document.body.innerHTML = "";
});

async function mountLayout(role: string | null) {
  setActivePinia(createPinia());
  setAuth(role);
  // theme store init（读 localStorage）
  useThemeStore();

  const { default: router } = await import("@/app/router");
  await router.replace("/").catch(() => {});
  await router.isReady();
  await flushPromises();

  // stub 真实 RouterView / RouterLink：避免触发子路由组件 axios 401
  // 重要：vue-router 已经注入 RouterView/RouterLink，这里用 stubs 覆盖
  const wrapper = mount(LayoutView, {
    global: {
      plugins: [router],
      stubs: {
        RouterView: defineComponent({
          name: "RouterViewStub",
          setup(_, { slots }) {
            // 占位 v-slot：layout 用 <RouterView v-slot="{ Component, route }">，
            // stub 必须提供 slot props 才能让 layout 渲染。
            return () =>
              h("div", { class: "stub-router-view" }, slots.default?.({ Component: null, route: { path: "/" } }));
          },
        }),
        RouterLink: defineComponent({
          name: "RouterLinkStub",
          setup(_, { slots }) {
            return () => h("a", {}, slots.default?.());
          },
        }),
        transition: false,
      },
    },
    attachTo: document.body,
  });
  await flushPromises();
  return { wrapper, router };
}

describe("LayoutView: role-based filtering", () => {
  it("teacher (low role) does not see capabilities/system/templates in nav", async () => {
    const { wrapper } = await mountLayout("teacher");
    const labels = wrapper.findAll(".nav-item").map((l) => l.text());
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.some((s) => s.includes("Skill"))).toBe(false);
    expect(labels.some((s) => s.includes("MCP"))).toBe(false);
    expect(labels.some((s) => s.includes("系统管理"))).toBe(false);
    expect(labels.some((s) => s.includes("数据要素模板"))).toBe(false);
    expect(labels.some((s) => s.includes("应用管理"))).toBe(false);
    wrapper.unmount();
  });

  it("super_admin with system_management flag off -> system hidden (hiddenInNav)", async () => {
    localStorageMock.setItem("metaedu_feature_system_management", "false");
    const { wrapper } = await mountLayout("super_admin");
    const labels = wrapper.findAll(".nav-item").map((l) => l.text());
    expect(labels.some((s) => s.includes("系统管理"))).toBe(false);
    wrapper.unmount();
  });

  it("super_admin with system_management flag on -> system still hidden (hiddenInNav by design)", async () => {
    // 系统管理 route 在 router.ts 中 hiddenInNav=true（仅经 /admin redirect 访问），
    // 永不进入 sidebar 投影。flag on/off 对 sidebar 可见性不影响。
    localStorageMock.setItem("metaedu_feature_system_management", "true");
    const { wrapper } = await mountLayout("super_admin");
    const labels = wrapper.findAll(".nav-item").map((l) => l.text());
    expect(labels.some((s) => s.includes("系统管理"))).toBe(false);
    wrapper.unmount();
  });

  it("admin (high privilege) sees capabilities + templates, no system", async () => {
    const { wrapper } = await mountLayout("admin");
    const labels = wrapper.findAll(".nav-item").map((l) => l.text());
    expect(labels.length).toBeGreaterThan(0);
    expect(labels.some((s) => s.includes("Skill"))).toBe(true);
    expect(labels.some((s) => s.includes("MCP"))).toBe(true);
    expect(labels.some((s) => s.includes("数据要素模板"))).toBe(true);
    // admin 没有 nav.system 权限（fail-closed）
    expect(labels.some((s) => s.includes("系统管理"))).toBe(false);
    wrapper.unmount();
  });

  it("sections ordered by SECTION_DESCRIPTORS.order (overview before knowledge_data)", async () => {
    localStorageMock.setItem("metaedu_feature_system_management", "true");
    const { wrapper } = await mountLayout("super_admin");
    const sectionLabels = wrapper.findAll(".nav-section-label").map((n) => n.text());
    expect(sectionLabels.length).toBeGreaterThan(0);
    expect(sectionLabels[0]).toBe("总览");
    expect(sectionLabels.indexOf("总览")).toBeLessThan(sectionLabels.indexOf("知识与数据"));
    wrapper.unmount();
  });
});

describe("LayoutView: collapsed-state icon visibility", () => {
  it("expanded: every nav item renders an icon element (svg)", async () => {
    const { wrapper } = await mountLayout("admin");
    const items = wrapper.findAll(".nav-item");
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      const icon = item.find(".nav-icon");
      expect(icon.exists(), `nav-item missing .nav-icon: ${item.text()}`).toBe(true);
      expect(icon.find("svg").exists(), `nav-item .nav-icon missing svg: ${item.text()}`).toBe(true);
    }
    wrapper.unmount();
  });

  it("collapsed: icons stay visible + aria-label retained + label hidden", async () => {
    const { wrapper } = await mountLayout("admin");
    const toggle = wrapper.find('button[aria-label="折叠侧边栏"]');
    expect(toggle.exists()).toBe(true);
    await toggle.trigger("click");
    await nextTick();
    await flushPromises();
    const items = wrapper.findAll(".nav-item");
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) {
      const icon = item.find(".nav-icon");
      // 图标必须仍在 DOM（不要被折叠态隐藏）
      expect(icon.exists(), `collapsed: .nav-icon missing on ${item.text()}`).toBe(true);
      expect(icon.find("svg").exists(), `collapsed: svg missing on ${item.text()}`).toBe(true);
      // aria-label 必须保留可访问性
      expect(item.attributes("aria-label"), "collapsed nav-item must keep aria-label").toBeTruthy();
    }
    // 所有 nav-label 在折叠态不应渲染
    const labels = wrapper.findAll(".nav-label");
    expect(labels.length, "collapsed: no .nav-label should be rendered").toBe(0);
    wrapper.unmount();
  });

  it("collapsed: brand BookOpen icon still visible", async () => {
    const { wrapper } = await mountLayout("admin");
    const toggle = wrapper.find('button[aria-label="折叠侧边栏"]');
    await toggle.trigger("click");
    await nextTick();
    await flushPromises();
    const brand = wrapper.find(".app-brand-mark");
    expect(brand.exists()).toBe(true);
    expect(brand.find("svg").exists()).toBe(true);
    wrapper.unmount();
  });
});

describe("LayoutView: activeNav unique highlighting", () => {
  it("on /, only home nav-item has nav-item-active class", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["总览"]);
    wrapper.unmount();
  });

  it("on /knowledge, only knowledge nav-item has nav-item-active class", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["知识库"]);
    wrapper.unmount();
  });

  it("on /capabilities/skills, capabilities-skills item highlighted; unique", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/capabilities/skills");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active.length).toBe(1);
    expect(active[0]).toContain("Skill");
    wrapper.unmount();
  });

  it("route change updates activeNav (no stale highlight)", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(collectActiveLabels(wrapper)).toEqual(["总览"]);
    await router.replace("/ai-chat");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active.length).toBe(1);
    expect(active[0]).toContain("AI 问答");
    wrapper.unmount();
  });
});

describe("LayoutView: every visible route has icon", () => {
  it("every rendered nav-item contains a rendered svg icon", async () => {
    const { wrapper } = await mountLayout("admin");
    const items = wrapper.findAll(".nav-item");
    expect(items.length).toBeGreaterThan(0);
    const missing: string[] = [];
    for (const item of items) {
      const icon = item.find(".nav-icon");
      const svg = icon.find("svg");
      if (!icon.exists() || !svg.exists()) {
        missing.push(item.text().trim());
      }
    }
    expect(missing, `nav-items missing icon: ${missing.join("; ")}`).toEqual([]);
    wrapper.unmount();
  });

  it("projectNavigation drops icon = undefined when route.meta.icon missing", async () => {
    const { projectNavigation } = await import("@/app/nav");
    const routes = [
      {
        name: "no-icon",
        path: "/no-icon",
        meta: { section: "overview" as const, title: "X", order: 99 },
      },
    ];
    const sections = projectNavigation(routes, {
      role: "super_admin",
      featureFlags: {},
    });
    const item = sections[0].items[0];
    expect(item.name).toBe("no-icon");
    expect(item.icon).toBeUndefined();
  });

  it("projectNavigation on real router.getRoutes() yields icons for every visible item", async () => {
    const { default: router } = await import("@/app/router");
    const { projectNavigation } = await import("@/app/nav");
    const sections = projectNavigation(router.getRoutes(), {
      role: "super_admin",
      featureFlags: { system_management: true },
    });
    const items = sections.flatMap((s) => s.items);
    expect(items.length).toBeGreaterThan(0);
    const missing: string[] = [];
    for (const item of items) {
      if (!item.icon) missing.push(item.name);
    }
    expect(missing, `nav-items without icon: ${missing.join("; ")}`).toEqual([]);
  });
});

describe("LayoutView: smoke render", () => {
  it("mounts without throwing for known role", async () => {
    const { wrapper } = await mountLayout("admin");
    expect(wrapper.find(".sidebar-shell").exists()).toBe(true);
    wrapper.unmount();
  });

  it("role label reflects roleMap (admin -> 管理员)", async () => {
    const { wrapper } = await mountLayout("admin");
    const userBtn = wrapper.find('button[aria-label="管理员"]');
    expect(userBtn.exists()).toBe(true);
    wrapper.unmount();
  });
});

/**
 * 收集所有 `.nav-item-active` 元素的文本，去除重复（因 stub 多次渲染）。
 * 本测试关注"应当只有一个 section 高亮"，允许出现重复文本但要求集合只有一项。
 */
function collectActiveLabels(wrapper: ReturnType<typeof mount>): string[] {
  const items = wrapper.findAll(".nav-item-active");
  const labels = items.map((i) => i.text().trim());
  // 去重，保留第一次出现
  const unique: string[] = [];
  for (const label of labels) {
    if (label && !unique.includes(label)) unique.push(label);
  }
  return unique;
}