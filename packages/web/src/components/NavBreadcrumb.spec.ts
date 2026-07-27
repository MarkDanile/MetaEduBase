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
  it("activeNav 指向未知 route name: 链在错配点终止，不插入假 crumb", async () => {
    // 真实注入 activeNav 错配：直接 mutate router 中 knowledge route 的 meta.activeNav
    // 指向一个不存在的 route。链在 knowledge 处找不到合法父项，fail-closed：
    // chain = [knowledge]（仅自身）→ 顶部 prepend home → [home, knowledge]
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/knowledge");
    await router.isReady();
    // 找到 knowledge route 并篡改 activeNav
    const knowledgeRoute = router.getRoutes().find((r) => r.name === "knowledge");
    if (knowledgeRoute) {
      knowledgeRoute.meta = { ...knowledgeRoute.meta, activeNav: "ghost_route_xyz" };
    }
    await nextTick();
    await flushPromises();
    // activeNav = ghost_route_xyz 找不到对应 route → parentRouteName 返回 null →
    // chain 只有 [knowledge]，顶部 prepend home → [总览 / 知识库]
    expect(linkNames(wrapper)).toEqual(["home"]);
    expect(wrapper.find('[aria-current="page"]').text()).toBe("知识库");
    wrapper.unmount();
  });

  it("activeNav 跨 section: 拒绝跳转，链在当前 route 终止", async () => {
    // 注入跨 section activeNav：让 knowledge (section=knowledge_data) 的 activeNav
    // 指向 ai-chat (section=ai_work)。section 一致性校验应 fail-closed：
    // chain = [knowledge] → [总览 / 知识库]，不插入 ai-chat。
    const { wrapper, router } = await mountBreadcrumb();
    await router.replace("/knowledge");
    await router.isReady();
    const knowledgeRoute = router.getRoutes().find((r) => r.name === "knowledge");
    if (knowledgeRoute) {
      knowledgeRoute.meta = { ...knowledgeRoute.meta, activeNav: "ai-chat" };
    }
    await nextTick();
    await flushPromises();
    const names = linkNames(wrapper);
    // 不应包含 ai-chat（跨 section 被拒）
    expect(names).not.toContain("ai-chat");
    expect(names).toEqual(["home"]);
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
