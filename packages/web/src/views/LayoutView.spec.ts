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

describe("LayoutView: detail parent highlighting (activeNav -> visible sidebar parent)", () => {
  it("on /resource/:id, parent 资源库 highlighted (file-detail.activeNav = resource)", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/resource/abc");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["资源库"]);
    wrapper.unmount();
  });

  it("on /database/:catalogCode, parent 数据库 highlighted (catalog-detail.activeNav = database)", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/database/electronics_info");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["数据库"]);
    wrapper.unmount();
  });

  it("on /data/templates/:id, parent 数据要素模板 highlighted (template-detail.activeNav = templates-list)", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/data/templates/42");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["数据要素模板"]);
    wrapper.unmount();
  });

  it("on /capabilities/skills (admin), Skill 库 highlighted; not parent fallback", async () => {
    // capabilities section 只有一个 visible sidebar item，detail parent 场景
    // 在 capabilities/mcp 才有意义。
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/capabilities/skills");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["Skill 库"]);
    wrapper.unmount();
  });

  it("on /ai-apps/:code (admin), parent AI 应用广场 highlighted (AiAppDetail.activeNav = AiAppsMarketplace)", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/ai-apps/sample-app");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["AI 应用广场"]);
    wrapper.unmount();
  });

  it("on /ai-apps/admin/:id (admin), parent 应用管理 highlighted (AiAppEdit.activeNav = AiAppsAdmin)", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/ai-apps/admin/42");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const active = collectActiveLabels(wrapper);
    expect(active).toEqual(["应用管理"]);
    wrapper.unmount();
  });
});

describe("LayoutView: 7-role visibility matrix", () => {
  // 7 角色 × sidebar section 可见性契约（plan §Slice 3 验收要求）
  // Section label 集合驱动断言；不硬编码具体 link 数。
  const SECTION_LABELS: Record<string, string[]> = {
    teacher: ["总览", "AI 工作", "智能体应用", "知识与数据"],
    employee: ["总览", "AI 工作", "智能体应用", "知识与数据"],
    student: ["总览", "AI 工作", "智能体应用", "知识与数据"],
    leader: ["总览", "AI 工作", "智能体应用", "知识与数据"],
    admin: ["总览", "AI 工作", "智能体应用", "知识与数据", "能力中心"],
    data_admin: ["总览", "AI 工作", "智能体应用", "知识与数据", "能力中心"],
  };

  for (const role of Object.keys(SECTION_LABELS) as Array<keyof typeof SECTION_LABELS>) {
    it(`${role} sees only the role-allowed sections`, async () => {
      const { wrapper } = await mountLayout(role);
      const labels = wrapper.findAll(".nav-section-label").map((n) => n.text());
      const expected = SECTION_LABELS[role];
      for (const e of expected) {
        expect(labels, `${role} should see ${e}`).toContain(e);
      }
      // 关键反向断言：低权角色看不到高权 section
      if (["teacher", "employee", "student", "leader"].includes(role)) {
        expect(labels, `${role} should NOT see 能力中心`).not.toContain("能力中心");
      }
      wrapper.unmount();
    });
  }

  it("unknown role -> empty sidebar (fail-closed)", async () => {
    const { wrapper } = await mountLayout("unknown_role");
    expect(wrapper.findAll(".nav-item").length).toBe(0);
    expect(wrapper.findAll(".nav-section-label").length).toBe(0);
    wrapper.unmount();
  });

  it("null role -> empty sidebar (fail-closed)", async () => {
    const { wrapper } = await mountLayout(null);
    expect(wrapper.findAll(".nav-item").length).toBe(0);
    wrapper.unmount();
  });

  it("super_admin: 系统管理 route is hiddenInNav, never in sidebar even with flag on", async () => {
    localStorageMock.setItem("metaedu_feature_system_management", "true");
    const { wrapper } = await mountLayout("super_admin");
    const labels = wrapper.findAll(".nav-item").map((l) => l.text());
    // 系统管理 route hiddenInNav=true：sidebar 永不展示（仅经 /admin redirect 访问）
    expect(labels.some((s) => s.includes("系统管理"))).toBe(false);
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

/* =========================================================================
 * REQ-060 Slice 4: 移动端 drawer + a11y + skip-link + aria-current
 * =======================================================================*/

describe("LayoutView: skip-link (a11y)", () => {
  it("渲染指向 #main-content 的 skip-link", async () => {
    const { wrapper } = await mountLayout("admin");
    const skip = wrapper.find("a.skip-link");
    expect(skip.exists()).toBe(true);
    expect(skip.attributes("href")).toBe("#main-content");
    wrapper.unmount();
  });
});

describe("LayoutView: mobile top-bar opener", () => {
  it("渲染 mobile-opener 按钮（含 aria-controls + aria-expanded）", async () => {
    const { wrapper } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    expect(opener.exists()).toBe(true);
    expect(opener.attributes("aria-controls")).toBe("mobile-drawer");
    expect(opener.attributes("aria-expanded")).toBe("false");
    expect(opener.attributes("aria-label")).toBe("打开导航");
    wrapper.unmount();
  });

  it("点击 opener 切换 aria-expanded + 切换菜单图标", async () => {
    const { wrapper } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    expect(opener.attributes("aria-expanded")).toBe("false");
    await opener.trigger("click");
    expect(opener.attributes("aria-expanded")).toBe("true");
    expect(opener.attributes("aria-label")).toBe("关闭导航");
    expect(wrapper.find(".drawer-backdrop").exists()).toBe(true);
    wrapper.unmount();
  });
});

describe("LayoutView: mobile drawer state", () => {
  it("drawer open 时 aside 不带 -translate-x-full", async () => {
    const { wrapper } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    await opener.trigger("click");
    const aside = wrapper.find("aside#mobile-drawer");
    const cls = aside.attributes("class") ?? "";
    expect(cls.includes("-translate-x-full")).toBe(false);
    expect(cls.includes("translate-x-0")).toBe(true);
    wrapper.unmount();
  });

  it("drawer open 时 backdrop 存在并可点击关闭", async () => {
    const { wrapper } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    await opener.trigger("click");
    const backdrop = wrapper.find("[data-testid='drawer-backdrop']");
    expect(backdrop.exists()).toBe(true);
    await backdrop.trigger("click");
    expect(opener.attributes("aria-expanded")).toBe("false");
    wrapper.unmount();
  });

  it("drawer open 时 document.body.style.overflow = hidden", async () => {
    const { wrapper } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    await opener.trigger("click");
    expect(document.body.style.overflow).toBe("hidden");
    wrapper.unmount();
  });

  it("drawer close 后 body.style.overflow 恢复", async () => {
    const { wrapper } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    await opener.trigger("click");
    expect(document.body.style.overflow).toBe("hidden");
    await opener.trigger("click");
    expect(document.body.style.overflow).toBe("");
    wrapper.unmount();
  });

  it("drawer open 时按 Escape 关闭", async () => {
    const { wrapper } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    await opener.trigger("click");
    expect(opener.attributes("aria-expanded")).toBe("true");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await nextTick();
    expect(opener.attributes("aria-expanded")).toBe("false");
    expect(document.body.style.overflow).toBe("");
    wrapper.unmount();
  });

  it("route change 自动关闭 drawer（returnFocus=false）", async () => {
    const { wrapper, router } = await mountLayout("admin");
    const opener = wrapper.find("button.mobile-opener");
    await opener.trigger("click");
    expect(opener.attributes("aria-expanded")).toBe("true");
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(opener.attributes("aria-expanded")).toBe("false");
    wrapper.unmount();
  });
});

describe("LayoutView: nav item aria-current", () => {
  it("active nav-item 设置 aria-current=page", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const activeItem = wrapper.findAll(".nav-item").find((i) =>
      i.text().includes("知识库"),
    );
    expect(activeItem).toBeTruthy();
    expect(activeItem?.attributes("aria-current")).toBe("page");
    wrapper.unmount();
  });

  it("非 active nav-item 不设 aria-current", async () => {
    const { wrapper, router } = await mountLayout("admin");
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const items = wrapper.findAll(".nav-item");
    const inactive = items.find((i) =>
      i.text().includes("AI 问答"),
    );
    expect(inactive).toBeTruthy();
    // aria-current 应当是 undefined（或无属性）
    expect(inactive?.attributes("aria-current")).toBeUndefined();
    wrapper.unmount();
  });
});

describe("LayoutView: desktop collapse 独立于 mobile drawer", () => {
  it("desktop collapsed 与 mobile drawer 独立：桌面折叠不影响 mobile drawer 状态", async () => {
    const { wrapper } = await mountLayout("admin");
    const desktopToggle = wrapper.find(".desktop-collapse-toggle");
    expect(desktopToggle.exists()).toBe(true);
    // 桌面折叠
    await desktopToggle.trigger("click");
    // mobile opener 不受影响
    const opener = wrapper.find("button.mobile-opener");
    expect(opener.attributes("aria-expanded")).toBe("false");
    // 桌面折叠的 nav-item-collapsed 类生效
    const collapsedItems = wrapper.findAll(".nav-item-collapsed");
    expect(collapsedItems.length).toBeGreaterThan(0);
    wrapper.unmount();
  });
});

describe("LayoutView: user menu a11y", () => {
  it("user menu 按钮 aria-expanded + aria-haspopup", async () => {
    const { wrapper } = await mountLayout("admin");
    const userBtn = wrapper.find('button[aria-label="管理员"]');
    expect(userBtn.exists()).toBe(true);
    expect(userBtn.attributes("aria-expanded")).toBe("false");
    expect(userBtn.attributes("aria-haspopup")).toBe("menu");
    wrapper.unmount();
  });

  it("user menu 打开时 menu role + menuitem role", async () => {
    const { wrapper } = await mountLayout("admin");
    const userBtn = wrapper.find('button[aria-label="管理员"]');
    await userBtn.trigger("click");
    expect(wrapper.find('[role="menu"]').exists()).toBe(true);
    expect(wrapper.findAll('[role="menuitem"]').length).toBeGreaterThan(0);
    wrapper.unmount();
  });
});

describe("LayoutView: prefers-reduced-motion", () => {
  it("CSS 包含 prefers-reduced-motion: reduce 媒体查询", async () => {
    // 静态断言：通过 Vite `?raw` import 在构建时读取 LayoutView.vue 源码
    // 避免引入 @types/node 依赖。
    // vitest.config.ts 用 vite，运行时支持 ?raw。
    const src = (await import("./LayoutView.vue?raw")).default as string;
    expect(src).toContain("prefers-reduced-motion");
    expect(src).toContain("transition: none");
  });
});
