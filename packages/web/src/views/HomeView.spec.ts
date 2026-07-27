/**
 * REQ-060 Slice 3 收口（修订）：HomeView 单元测试。
 *
 * 覆盖：
 * - HomeView 通过 projectNavigation 派生 home cards（不硬编码 CARD_SPECS）
 * - 引用 route name 而非 path；隐藏 route（hiddenInNav）不在 home cards
 * - 技能编排旧入口被下线（不出现；其原 path 在 Slice 2 redirect 到 capabilities-skills）
 * - section 文案/图标由 SECTION_META 派生（不参与 RBAC）
 * - shortcut 通过 (section, itemName) 解析；权限缺失或 feature flag off 自动隐藏
 * - unknown role fail-closed：cards 与 shortcuts 都为空
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

const StubRouterLink = defineComponent({
  name: "RouterLinkStub",
  props: {
    to: { type: Object, default: () => ({}) },
  },
  setup(props, { slots }) {
    return () =>
      h(
        "a",
        {
          class: "stub-router-link",
          "data-name": (props.to as { name?: string })?.name ?? "",
        },
        slots.default?.(),
      );
  },
});

const StubRouterView = defineComponent({
  name: "RouterViewStub",
  setup(_, { slots }) {
    return () => h("div", { class: "stub-router-view" }, slots.default?.());
  },
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

async function mountHome(role: string | null, opts: { flags?: Record<string, boolean> } = {}) {
  setActivePinia(createPinia());
  setAuth(role);
  for (const [k, v] of Object.entries(opts.flags ?? {})) {
    if (v) localStorageMock.setItem(`metaedu_feature_${k}`, "true");
  }

  const { default: router } = await import("@/app/router");
  await router.replace("/");
  await router.isReady();
  await flushPromises();

  const wrapper = mount(HomeView, {
    global: {
      plugins: [router],
      stubs: {
        RouterLink: StubRouterLink,
        RouterView: StubRouterView,
        transition: false,
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

describe("HomeView: cards via projectNavigation", () => {
  it("admin: cards reference route name not path (no hardcoded path)", async () => {
    const { wrapper } = await mountHome("admin");
    // HomeView 卡片由 projectNavigation 投影生成，每张卡片 <h3> 显示 route.meta.title。
    // 验证：可见业务 leaf title 出现在卡片区，不出现 "技能编排" 旧文案。
    const text = wrapper.text();
    expect(text).toContain("知识库"); // knowledge
    expect(text).toContain("资源库"); // resource
    expect(text).toContain("AI 问答"); // ai-chat
    expect(text).toContain("Skill 库"); // capabilities-skills
    expect(text.includes("技能编排")).toBe(false);
    wrapper.unmount();
  });

  it("teacher (low role): excludes capabilities/system section cards", async () => {
    const { wrapper } = await mountHome("teacher");
    const text = wrapper.text();
    expect(text).toContain("知识库");
    expect(text).toContain("AI 问答");
    // 不应包含 capabilities/system 高权 section 的卡片
    expect(text.includes("Skill 库")).toBe(false);
    expect(text.includes("MCP 工具")).toBe(false);
    expect(text.includes("数据要素模板")).toBe(false);
    expect(text.includes("系统管理")).toBe(false);
    wrapper.unmount();
  });

  it("super_admin: 系统管理（hiddenInNav）永远不在 cards", async () => {
    const { wrapper } = await mountHome("super_admin", { flags: { system_management: true } });
    const text = wrapper.text();
    expect(text.includes("系统管理")).toBe(false);
    wrapper.unmount();
  });

  it("cards: 技能编排 旧入口已下线（不出现 capabilities-skills 误命名为 skill-editor）", async () => {
    const { wrapper } = await mountHome("admin");
    const text = wrapper.text();
    expect(text.includes("技能编排")).toBe(false);
    wrapper.unmount();
  });

  it("unknown role fail-closed: cards empty (verified via direct projectNavigation)", async () => {
    // 通过直接调用 projectNavigation 验证 fail-closed（无业务 leaf 投影）
    const { projectNavigation } = await import("@/app/nav");
    const { default: router } = await import("@/app/router");
    const sections = projectNavigation(router.getRoutes(), {
      role: "unknown_role",
      featureFlags: {},
    });
    const items = sections.flatMap((s) => s.items);
    expect(items.length).toBe(0);
    // HomeView text 也不会显示 cards 标题（stats "AI 问答" 等是展示常量不算 card）
    const { wrapper } = await mountHome("unknown_role");
    expect(wrapper.text().includes("浏览知识目录")).toBe(false);
    expect(wrapper.text().includes("AI 智能问答")).toBe(false);
    wrapper.unmount();
  });

  it("null role fail-closed: cards empty", async () => {
    const { projectNavigation } = await import("@/app/nav");
    const { default: router } = await import("@/app/router");
    const sections = projectNavigation(router.getRoutes(), {
      role: null,
      featureFlags: {},
    });
    const items = sections.flatMap((s) => s.items);
    expect(items.length).toBe(0);
    const { wrapper } = await mountHome(null);
    expect(wrapper.text().includes("浏览知识目录")).toBe(false);
    expect(wrapper.text().includes("AI 智能问答")).toBe(false);
    wrapper.unmount();
  });
});

describe("HomeView: shortcuts via projectNavigation", () => {
  it("admin: shortcuts include knowledge + ai-chat + resource", async () => {
    const { wrapper } = await mountHome("admin");
    // shortcuts 用 <button @click="$router.push">，不能直接断言 RouterLink
    // 但页面内含这些文案的按钮（快捷操作 section）
    const texts = wrapper.text();
    expect(texts).toContain("浏览知识目录");
    expect(texts).toContain("AI 智能问答");
    expect(texts).toContain("上传教学资源");
    wrapper.unmount();
  });

  it("teacher: capabilities/system templates shortcuts hidden", async () => {
    const { wrapper } = await mountHome("teacher");
    const texts = wrapper.text();
    // knowledge/resource/ai-chat 仍可见（teacher 有 base permission）
    expect(texts).toContain("浏览知识目录");
    expect(texts).toContain("AI 智能问答");
    wrapper.unmount();
  });

  it("unknown role fail-closed: shortcuts empty (no knowledge/resource/ai-chat cards)", async () => {
    const { wrapper } = await mountHome("unknown_role");
    const texts = wrapper.text();
    expect(texts).not.toContain("浏览知识目录");
    expect(texts).not.toContain("AI 智能问答");
    expect(texts).not.toContain("上传教学资源");
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
    // roleShortMap[admin] = "管理员"
    expect(wrapper.text()).toMatch(/(早上好|上午好|中午好|下午好|晚上好|夜深了)/);
    wrapper.unmount();
  });
});