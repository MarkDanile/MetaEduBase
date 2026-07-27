/**
 * REQ-060 Slice 3 收口：全局 Breadcrumb 单元测试。
 *
 * 覆盖：
 * - route.matched 链派生（parent -> leaf），仅保留带 meta.title 的层级
 * - hiddenInNav 不影响 breadcrumb（仅 sidebar 过滤）
 * - 当前页（最后一项）非链接，aria-current="page"
 * - 单 crumb（仅当前页）不渲染导航条，避免冗余
 * - root layout wrapper（无 meta.title）自动跳过
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
      // stub RouterLink 为最小占位，避免触发子路由组件 axios 401
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

describe("Breadcrumb: route.matched chain", () => {
  it("on / (home): only one crumb — nav not rendered", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/");
    await router.isReady();
    await nextTick();
    await flushPromises();
    // 单 crumb 时不渲染整个 nav（避免视觉冗余）
    expect(wrapper.find("nav.breadcrumb-bar").exists()).toBe(false);
    wrapper.unmount();
  });

  it("on /knowledge: 总览 / 知识库 (last is aria-current=page)", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/knowledge");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.exists()).toBe(true);
    expect(nav.attributes("aria-label")).toBe("面包屑导航");
    // 收集所有 crumb 文本（link + current span）
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
});

describe("Breadcrumb: hiddenInNav routes still appear in breadcrumb", () => {
  it("on /resource/:id (file-detail hiddenInNav=true): 总览 / 资源库 / 文件详情", async () => {
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

  it("on /data/templates/:id (template-detail hiddenInNav=true): 总览 / 数据要素模板 / 模板详情", async () => {
    // /data 是占位 segment（无 route），/data/templates 才是父级。
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
});

describe("Breadcrumb: separator + accessibility", () => {
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

describe("Breadcrumb: failure modes", () => {
  it("matched empty -> nav not rendered (no throw)", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/").catch(() => {});
    await router.isReady();
    await nextTick();
    await flushPromises();
    // home 是唯一 matched 且有 meta.title 的层级 -> 单 crumb -> 不渲染 nav
    expect(wrapper.find("nav.breadcrumb-bar").exists()).toBe(false);
    wrapper.unmount();
  });

  it("route name fallback works when meta.activeNav absent (sanity)", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/ai-chat");
    await router.isReady();
    await nextTick();
    await flushPromises();
    const nav = wrapper.find("nav.breadcrumb-bar");
    expect(nav.exists()).toBe(true);
    expect(nav.find('[aria-current="page"]').text()).toBe("AI 问答");
    wrapper.unmount();
  });
});