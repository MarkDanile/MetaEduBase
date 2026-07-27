/**
 * REQ-060 Slice 3 收口（修订-2）：NavBreadcrumb 单元测试。
 *
 * 派生规则：
 * - 沿当前 route 的 meta.activeNav 链向上追溯，每步校验父项 section 必须与
 *   当前 route 同 section（防误配 activeNav 跳出当前 IA 区域；fail-closed）。
 * - 链以 home 终止；顶部虚拟「总览」首页 crumb 自动 prepend。
 * - hiddenInNav route 仍出现 crumb（仅 sidebar 过滤）。
 * - activeNav 自指（home/knowledge/...）→ 终止。
 * - activeNav 指向未知 route → fail-closed（不在链中插入假 crumb）。
 *
 * 覆盖：
 * - activeNav 链派生（base 业务 leaf、hiddenInNav 详情页、/apps/* shell）
 * - 父子 section 不一致 → 不跨 section（fail-closed）
 * - activeNav 指向未知 route → 链在错配点终止（fail-closed）
 * - aria-current + separator + accessibility
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { defineComponent, h, nextTick } from "vue";
import NavBreadcrumb from "./NavBreadcrumb.vue";

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
          props: { to: { type: Object, default: () => ({}) } },
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
        }),
      },
    },
    attachTo: document.body,
  });
  await flushPromises();
  return { wrapper, router };
}

function linkNames(wrapper: ReturnType<typeof mount>): string[] {
  return wrapper
    .findAll("a.stub-router-link")
    .map((a) => a.attributes("data-name") ?? "");
}

describe("NavBreadcrumb: activeNav chain derivation", () => {
  it("on / (home): single crumb — nav not rendered", async () => {
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
    expect(linkNames(wrapper)).toEqual(["home"]);
    expect(nav.find('[aria-current="page"]').text()).toBe("知识库");
    wrapper.unmount();
  });

  it("on /capabilities/skills: 总览 / Skill 库", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/capabilities/skills");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(linkNames(wrapper)).toEqual(["home"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("Skill 库");
    wrapper.unmount();
  });

  it("on /ai-chat: 总览 / AI 问答", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/ai-chat");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(linkNames(wrapper)).toEqual(["home"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("AI 问答");
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
    expect(linkNames(wrapper)).toEqual(["home", "resource"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("文件详情");
    wrapper.unmount();
  });

  it("on /data/templates/:id (template-detail activeNav=templates-list): 总览 / 数据要素模板 / 模板详情", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/data/templates/42");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(linkNames(wrapper)).toEqual(["home", "templates-list"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("模板详情");
    wrapper.unmount();
  });

  it("on /database/:catalogCode (catalog-detail activeNav=database): 总览 / 数据库 / 目录详情", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/database/electronics_info");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(linkNames(wrapper)).toEqual(["home", "database"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("目录详情");
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
    expect(linkNames(wrapper)).toEqual(["home", "AiAppsMarketplace"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("应用详情");
    wrapper.unmount();
  });

  it("on /ai-apps/admin/:id (AiAppEdit hiddenInNav, activeNav=AiAppsAdmin): 总览 / 应用管理 / 编辑应用", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/ai-apps/admin/42");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(linkNames(wrapper)).toEqual(["home", "AiAppsAdmin"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("编辑应用");
    wrapper.unmount();
  });

  it("on /apps/course-capability-map (AppCourseCapabilityMap hiddenInNav): 总览 / AI 应用广场 / 课程能力图谱", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/apps/course-capability-map");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(linkNames(wrapper)).toEqual(["home", "AiAppsMarketplace"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("课程能力图谱");
    wrapper.unmount();
  });

  it("on /apps/preview-guide (AppPreviewGuide hiddenInNav): 总览 / AI 应用广场 / 智能预习导学", async () => {
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/apps/preview-guide");
    await router.isReady();
    await nextTick();
    await flushPromises();
    expect(linkNames(wrapper)).toEqual(["home", "AiAppsMarketplace"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("智能预习导学");
    wrapper.unmount();
  });
});

describe("NavBreadcrumb: section-consistency fail-closed", () => {
  // 独立 router per case：避免污染共享 singleton router（route meta 不可写）。
  // 本 block 用 createMemoryHistory + 自定义 routes 直接 mount，断言 parentRouteName
  // 等价行为：缺失 section 一律 fail-closed。
  function buildIsolatedRouter(
    routeOverrides: Array<{
      path: string;
      name: string;
      meta: Record<string, unknown>;
    }>,
  ) {
    return createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", name: "home", component: { template: "<div/>" }, meta: { title: "总览", section: "overview", activeNav: "home" } },
        ...routeOverrides.map((r) => ({
          path: r.path,
          name: r.name,
          component: { template: "<div/>" },
          meta: r.meta,
        })),
      ],
    });
  }

  async function mountBreadcrumbIsolated(router: ReturnType<typeof createRouter>) {
    await router.isReady();
    await flushPromises();
    const wrapper = mount(NavBreadcrumb, {
      global: {
        plugins: [router],
        stubs: {
          RouterLink: defineComponent({
            name: "RouterLinkStub",
            props: { to: { type: Object, default: () => ({}) } },
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
          }),
        },
      },
      attachTo: document.body,
    });
    await flushPromises();
    return wrapper;
  }

  it("activeNav 指向未知 route name: chain 终止在当前 route，不插入假 crumb", async () => {
    const router = buildIsolatedRouter([
      {
        path: "/x",
        name: "x",
        meta: { title: "X", section: "overview", activeNav: "ghost_route_xyz" },
      },
    ]);
    setActivePinia(createPinia());
    setAuth("admin");
    await router.push("/x");
    await router.isReady();
    await nextTick();
    const wrapper = await mountBreadcrumbIsolated(router);
    // activeNav 找不到对应 route → parentRouteName 返回 null → chain = [x]
    // prepend home → [总览 / X]，linkNames = [home]
    expect(linkNames(wrapper)).toEqual(["home"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("X");
    wrapper.unmount();
  });

  it("activeNav 跨 section: 拒绝跳转，链仅自身 + 顶部 home", async () => {
    const router = buildIsolatedRouter([
      {
        path: "/a",
        name: "a",
        meta: { title: "A", section: "section_a", activeNav: "b" },
      },
      {
        path: "/b",
        name: "b",
        meta: { title: "B", section: "section_b" },
      },
    ]);
    setActivePinia(createPinia());
    setAuth("admin");
    await router.push("/a");
    await router.isReady();
    await nextTick();
    const wrapper = await mountBreadcrumbIsolated(router);
    // a (section_a) 的 activeNav = b (section_b)，跨 section 拒绝
    // chain = [a]，prepend home → [home, a]，linkNames = [home]
    const names = linkNames(wrapper);
    expect(names).not.toContain("b");
    expect(names).toEqual(["home"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("A");
    wrapper.unmount();
  });

  it("当前 route 缺 meta.section: 拒绝向上追溯（fail-closed），链仅自身", async () => {
    const router = buildIsolatedRouter([
      {
        path: "/a",
        name: "a",
        meta: { title: "A", activeNav: "b" }, // 缺 section
      },
      {
        path: "/b",
        name: "b",
        meta: { title: "B", section: "section_b" },
      },
    ]);
    setActivePinia(createPinia());
    setAuth("admin");
    await router.push("/a");
    await router.isReady();
    await nextTick();
    const wrapper = await mountBreadcrumbIsolated(router);
    // a 缺 section → cursorSection = undefined → parentRouteName 拒绝
    expect(linkNames(wrapper)).toEqual(["home"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("A");
    wrapper.unmount();
  });

  it("父 route 缺 meta.section: 拒绝跳转（即使 currentSection 存在）", async () => {
    const router = buildIsolatedRouter([
      {
        path: "/a",
        name: "a",
        meta: { title: "A", section: "section_a", activeNav: "b" },
      },
      {
        path: "/b",
        name: "b",
        meta: { title: "B" }, // 缺 section
      },
    ]);
    setActivePinia(createPinia());
    setAuth("admin");
    await router.push("/a");
    await router.isReady();
    await nextTick();
    const wrapper = await mountBreadcrumbIsolated(router);
    // parent b 缺 section → parentRouteName 拒绝
    const names = linkNames(wrapper);
    expect(names).not.toContain("b");
    expect(names).toEqual(["home"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("A");
    wrapper.unmount();
  });

  it("正常 activeNav（同 section）：链派生通过校验", async () => {
    const router = buildIsolatedRouter([
      {
        path: "/parent",
        name: "parent",
        meta: { title: "Parent", section: "section_a", activeNav: "parent" },
      },
      {
        path: "/child",
        name: "child",
        meta: { title: "Child", section: "section_a", activeNav: "parent" },
      },
    ]);
    setActivePinia(createPinia());
    setAuth("admin");
    await router.push("/child");
    await router.isReady();
    await nextTick();
    const wrapper = await mountBreadcrumbIsolated(router);
    // child 同 section activeNav=parent，parent 又 activeNav=parent（自指）→ chain = [child, parent]
    // prepend home → [home, parent, child]，linkNames = [home, parent]
    expect(linkNames(wrapper)).toEqual(["home", "parent"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("Child");
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
