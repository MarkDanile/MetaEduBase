/**
 * REQ-060 Slice 3 收口（修订-2）：HomeView 单元测试。
 *
 * 覆盖：
 * - homeCards = HOME_CARD_SPECS ∩ projectNavigation 可见名称集合
 * - 卡片使用稳定选择器 `.home-card[data-card-name="<routeName>"]`，避免整页 text 假阳性
 * - 同一 section 多入口都保留（知识与数据 → 知识库/资源库/数据库/数据要素模板）
 * - 「技能编排」旧入口已下线（spec 不含 skill-editor）
 * - shortcut 经 (section, itemName) 解析；权限缺失自动隐藏
 * - unknown / null role fail-closed
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";
import HomeView from "./HomeView.vue";

// localStorage stub（隔离）
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
Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  configurable: true,
  writable: true,
});

// stub axios 防止 loadStats() 触发 401
vi.mock("axios", () => {
  const handler = {
    get: () => Promise.resolve({ data: { total: 0 } }),
    create: () => handler,
    interceptors: {
      request: { use: () => 0 },
      response: { use: () => 0 },
    },
  };
  return { default: handler };
});

// 用稳定选择器：卡片带 class .home-card + data-card-name（routeName）
function cardSelector(routeName: string): string {
  return `.home-card[data-card-name="${routeName}"]`;
}

async function mountHome(role: string | null, opts: { flags?: Record<string, boolean> } = {}) {
  setActivePinia(createPinia());
  if (role) {
    localStorageMock.setItem("metaedu_token", "fake");
    localStorageMock.setItem("metaedu_role", role);
    localStorageMock.setItem("metaedu_tenant_id", "t1");
  } else {
    localStorageMock.setItem("metaedu_token", "fake");
    localStorageMock.removeItem("metaedu_role");
    localStorageMock.setItem("metaedu_tenant_id", "t1");
  }
  for (const [k, v] of Object.entries(opts.flags ?? {})) {
    if (v) localStorageMock.setItem(`metaedu_feature_${k}`, "true");
  }

  const { default: router } = await import("@/app/router");
  await router.replace("/");
  await router.isReady();
  await flushPromises();

  // stub RouterView 防止 LayoutView 子路由触发 axios；HomeView 直接渲染
  const wrapper = mount(HomeView, {
    global: {
      plugins: [router],
      stubs: {
        RouterView: defineComponent({
          name: "RouterViewStub",
          setup(_, { slots }) {
            return () => h("div", { class: "stub-router-view" }, slots.default?.());
          },
        }),
      },
    },
    attachTo: document.body,
  });
  await flushPromises();
  return { wrapper, router };
}

beforeEach(() => {
  localStorageMock.clear();
  document.body.innerHTML = "";
});

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("HomeView: homeCards = HOME_CARD_SPECS ∩ projectNavigation", () => {
  it("admin: 知识与数据 section 多入口全保留（知识库/资源库/数据库/数据要素模板）", async () => {
    const { wrapper } = await mountHome("admin");
    // admin 拥有 nav.data.templates 权限 → 数据要素模板应出现
    expect(wrapper.find(cardSelector("knowledge")).exists()).toBe(true);
    expect(wrapper.find(cardSelector("resource")).exists()).toBe(true);
    expect(wrapper.find(cardSelector("database")).exists()).toBe(true);
    expect(wrapper.find(cardSelector("templates-list")).exists()).toBe(true);
    // 知识与数据 section 共 4 入口全部保留（不允许"每段取首项"导致丢失）
    const knowledgeDataCards = wrapper
      .findAll(".home-card")
      .filter((c) =>
        ["knowledge", "resource", "database", "templates-list"].includes(
          c.attributes("data-card-name") ?? "",
        ),
      );
    expect(knowledgeDataCards.length).toBe(4);
    wrapper.unmount();
  });

  it("admin: 能力中心 section 多入口全保留（Skill 库 + MCP 工具）", async () => {
    const { wrapper } = await mountHome("admin");
    expect(wrapper.find(cardSelector("capabilities-skills")).exists()).toBe(true);
    expect(wrapper.find(cardSelector("capabilities-mcp")).exists()).toBe(true);
    wrapper.unmount();
  });

  it("teacher: 能力中心 cards 不出现（无 nav.capabilities），但其他 base 入口仍在", async () => {
    const { wrapper } = await mountHome("teacher");
    expect(wrapper.find(cardSelector("capabilities-skills")).exists()).toBe(false);
    expect(wrapper.find(cardSelector("capabilities-mcp")).exists()).toBe(false);
    expect(wrapper.find(cardSelector("templates-list")).exists()).toBe(false);
    // teacher 仍有 base 入口
    expect(wrapper.find(cardSelector("knowledge")).exists()).toBe(true);
    expect(wrapper.find(cardSelector("resource")).exists()).toBe(true);
    expect(wrapper.find(cardSelector("ai-chat")).exists()).toBe(true);
    wrapper.unmount();
  });

  it("super_admin: 知识与数据 + 能力中心 + 应用区共多入口全部出现", async () => {
    const { wrapper } = await mountHome("super_admin", {
      flags: { system_management: true },
    });
    const expected = [
      "knowledge",
      "resource",
      "database",
      "templates-list",
      "ai-chat",
      "capabilities-skills",
      "capabilities-mcp",
      "AiAppsMarketplace",
    ];
    for (const name of expected) {
      expect(wrapper.find(cardSelector(name)).exists(), `card ${name} missing`).toBe(true);
    }
    // system hiddenInNav → 不出现在 home cards（即使 flag on）
    expect(wrapper.find(cardSelector("system")).exists()).toBe(false);
    wrapper.unmount();
  });

  it("HOME_CARD_SPECS 引用的是 routeName（presentation-only），不含 path/permission", async () => {
    // 直接断言：所有渲染卡片的 data-card-name 都是 RouterName（symbol-free 字符串），
    // 不出现 path、permission key、feature flag key
    const { wrapper } = await mountHome("admin");
    const names = wrapper.findAll(".home-card").map((c) => c.attributes("data-card-name") ?? "");
    expect(names.length).toBeGreaterThan(0);
    for (const n of names) {
      expect(n.startsWith("/"), `card name should not be a path: ${n}`).toBe(false);
      expect(n.includes("nav."), `card name should not be a permission key: ${n}`).toBe(false);
      expect(n.includes("_management"), `card name should not be a feature flag: ${n}`).toBe(false);
    }
    wrapper.unmount();
  });

  it("unknown role fail-closed: cards empty", async () => {
    const { wrapper } = await mountHome("unknown_role");
    expect(wrapper.findAll(".home-card").length).toBe(0);
    wrapper.unmount();
  });

  it("null role fail-closed: cards empty", async () => {
    const { wrapper } = await mountHome(null);
    expect(wrapper.findAll(".home-card").length).toBe(0);
    wrapper.unmount();
  });

  it("skill-editor 旧入口未出现在 HOME_CARD_SPECS（plan 下线技能编排）", async () => {
    // 直接断言：所有渲染卡片的 data-card-name 集合不含 skill-editor
    const { wrapper } = await mountHome("super_admin", { flags: { system_management: true } });
    const names = wrapper.findAll(".home-card").map((c) => c.attributes("data-card-name") ?? "");
    expect(names).not.toContain("skill-editor");
    // 整页文本也不含"技能编排"文案
    expect(wrapper.text().includes("技能编排")).toBe(false);
    wrapper.unmount();
  });
});

describe("HomeView: shortcuts via projectNavigation", () => {
  it("admin: shortcuts include knowledge + ai-chat + resource", async () => {
    const { wrapper } = await mountHome("admin");
    // shortcuts 用 data-shortcut-name 选择器（稳定）
    expect(wrapper.find('.home-shortcut[data-shortcut-name="knowledge"]').exists()).toBe(true);
    expect(wrapper.find('.home-shortcut[data-shortcut-name="ai-chat"]').exists()).toBe(true);
    expect(wrapper.find('.home-shortcut[data-shortcut-name="resource"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("teacher: capabilities/system templates shortcuts hidden (权限缺失自动过滤)", async () => {
    const { wrapper } = await mountHome("teacher");
    expect(wrapper.find('.home-shortcut[data-shortcut-name="knowledge"]').exists()).toBe(true);
    expect(wrapper.find('.home-shortcut[data-shortcut-name="ai-chat"]').exists()).toBe(true);
    expect(wrapper.find('.home-shortcut[data-shortcut-name="resource"]').exists()).toBe(true);
    wrapper.unmount();
  });

  it("unknown role fail-closed: shortcuts empty", async () => {
    const { wrapper } = await mountHome("unknown_role");
    expect(wrapper.findAll(".home-shortcut").length).toBe(0);
    wrapper.unmount();
  });
});

describe("HomeView: smoke render", () => {
  it("mounts without throwing for known role", async () => {
    const { wrapper } = await mountHome("admin");
    expect(wrapper.text()).toContain("元知职教基座");
    wrapper.unmount();
  });

  it("renders greeting line with roleLabel", async () => {
    const { wrapper } = await mountHome("admin");
    expect(wrapper.text()).toMatch(/(早上好|上午好|中午好|下午好|晚上好|夜深了)/);
    wrapper.unmount();
  });
});
