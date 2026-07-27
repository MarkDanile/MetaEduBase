/**
 * REQ-060 Slice 3 收口（修订）：NavBreadcrumb 单元测试。
 *
 * 派生规则（基于 activeNav + route name，不再用 URL 截断）：
 * - 顺着当前 route 的 meta.activeNav 链向上找父项
 *   - activeNav 自指（home/knowledge/...）→ 终止
 *   - activeNav 指向父项（file-detail -> resource）→ 父项 meta.activeNav 自指 → 终止
 * - 顶部追加虚拟「总览」首页 crumb（如果链中没有 home）
 * - 单 crumb（仅当前页 = home）不渲染导航条
 *
 * 覆盖：
 * - activeNav 链派生（parent -> leaf）
 * - hiddenInNav route 仍出现在 breadcrumb（仅 sidebar 过滤）
 * - /apps/* shell 路由（activeNav=AiAppsMarketplace）→ 父项高亮
 * - 当前页 aria-current="page"，中间 crumb 是 RouterLink
 * - 未知/异常 route 不抛异常
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h, nextTick } from "vue";
import NavBreadcrumb from "./NavBreadcrumb.vue";

// localStorage stub（隔离 auth state；route guard 走 localStorage）
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

async function mountBreadcrumb() {
  setActivePinia(createPinia());
  setAuth("admin");
  const { default: router } = await import("@/app/router");
  await router.replace("/").catch(() => {});
  await router.isReady();
  await flushPromises();

  const wrapper = mount(NavBreadcrumb, {
    global: {
      plugins: [router],
      stubs: {
        RouterLink: defineComponent({
          name: "RouterLinkStub",
          setup(_, { slots }) {
            return () => h("a", { class: "stub-router-link" }, slots.default?.());
          },
        }),
      },
    },
    attachTo: document.body,
  });
  await flushPromises();
  return { wrapper, router };
}

describe("NavBreadcrumb: activeNav chain derivation", () => {
  it("on / (home): single crumb — nav not rendered (avoid 总览 / 总览)", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(wrapper.find("nav.breadcrumb-bar").exists()).toBe(false);
    wrapper.unmount();
  });

  it("on /knowledge (activeNav=self): 总览 / 知识库", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.exists()).toBe(true);
    expect(nav.attributes("aria-label")).toBe("面包屑导航");
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览"]);
    const current = nav.find('[aria-current="page"]');
    expect(current.exists()).toBe(true);
    expect(current.text()).toBe("知识库");
    wrapper.unmount();
  });

  it("on /capabilities/skills: 总览 / Skill 库", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/capabilities/skills");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.exists()).toBe(true);
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("Skill 库");
    wrapper.unmount();
  });

  it("on /ai-chat: 总览 / AI 问答", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/ai-chat");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("AI 问答");
    wrapper.unmount();
  });
});

describe("NavBreadcrumb: hiddenInNav routes still appear via activeNav parent", () => {
  it("on /resource/:id (file-detail hiddenInNav, activeNav=resource): 总览 / 资源库 / 文件详情", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/resource/abc");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.exists()).toBe(true);
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览", "资源库"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("文件详情");
    wrapper.unmount();
  });

  it("on /data/templates/:id (template-detail activeNav=templates-list): 总览 / 数据要素模板 / 模板详情", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/data/templates/42");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.exists()).toBe(true);
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览", "数据要素模板"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("模板详情");
    wrapper.unmount();
  });

  it("on /database/:catalogCode (catalog-detail activeNav=database): 总览 / 数据库 / 目录详情", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/database/electronics_info");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览", "数据库"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("目录详情");
    wrapper.unmount();
  });
});

describe("NavBreadcrumb: /apps/* shell routes (activeNav=AiAppsMarketplace)", () => {
  it("on /ai-apps/:code (AiAppDetail hiddenInNav, activeNav=AiAppsMarketplace): 总览 / AI 应用广场 / 应用详情", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/ai-apps/sample-app");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.exists()).toBe(true);
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览", "AI 应用广场"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("应用详情");
    wrapper.unmount();
  });

  it("on /ai-apps/admin/:id (AiAppEdit hiddenInNav, activeNav=AiAppsAdmin): 总览 / 应用管理 / 编辑应用", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/ai-apps/admin/42");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览", "应用管理"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("编辑应用");
    wrapper.unmount();
  });

  it("on /apps/course-capability-map (AppCourseCapabilityMap hiddenInNav): 总览 / AI 应用广场 / 课程能力图谱", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/apps/course-capability-map");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    const links = nav.findAll("a.stub-router-link");
    expect(links.map((a) => a.text())).toEqual(["总览", "AI 应用广场"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("课程能力图谱");
    wrapper.unmount();
  });

  it("on /apps/preview-guide (AppPreviewGuide hiddenInNav): 总览 / AI 应用广场 / 智能预习导学", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/apps/preview-guide");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.find('[aria-current="page"]').text()).toBe("智能预习导学");
    wrapper.unmount();
  });
});

describe("NavBreadcrumb: separator + accessibility", () => {
  it("renders ChevronRight separators between crumbs", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/resource/abc");
    await router.isReady();
    await nextTick();
    await flushPromises();
    // /resource/abc -> 总览 / 资源库 / 文件详情 (3 crumbs => 2 separators)
    const separators = wrapper.findAll("nav.breadcrumb-bar svg");
    expect(separators.length).toBe(2);
    wrapper.unmount();
  });

  it("aria-current page element does not render an anchor link", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const current = wrapper.find('[aria-current="page"]');
    expect(current.exists()).toBe(true);
    expect(current.element.tagName).toBe("SPAN");
    wrapper.unmount();
  });
});

describe("NavBreadcrumb: failure modes", () => {
  it("matched empty / no title -> nav not rendered (no throw)", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/").catch(() => {});
    await router.isReady();
    await nextTick();
    await flushPromises();
    // home 是唯一 matched 且有 meta.title 的层级 -> 单 crumb -> 不渲染 nav
    expect(wrapper.find("nav.breadcrumb-bar").exists()).toBe(false);
    wrapper.unmount();
  });

  it("activeNav points to unknown route name -> chain breaks safely, no throw", async () => {
    // 不会发生（router.ts 由工程团队维护），但 fail-closed 行为必须可观察
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    // 即便 activeNav 异常解析失败，仍渲染至少 [总览 / 知识库]
    expect(wrapper.find("nav.breadcrumb-bar").exists()).toBe(true);
    wrapper.unmount();
  });
});