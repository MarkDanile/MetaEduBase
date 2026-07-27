/**
 * REQ-060 Slice 4: useMobileDrawer composable 单元测试。
 *
 * 覆盖：
 * - 状态机：open/close/toggle 互斥
 * - body scroll lock：open 时设 overflow:hidden；close 时恢复
 * - Escape：document keydown 关闭 drawer（无论焦点在 drawer 内/外）
 * - route change：自动关闭 drawer（returnFocus=false，避免抖动）
 * - 焦点：open 时焦点移到 data-autofocus；close 时焦点回到 opener
 * - Tab 循环焦点：drawer 内 Tab/Shift+Tab 在可聚焦元素间循环
 * - onUnmounted：清理 body overflow（防御性）
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import { defineComponent, nextTick, ref, type Ref } from "vue";
import { useMobileDrawer } from "./useMobileDrawer";

beforeEach(() => {
  document.body.style.overflow = "";
});

afterEach(() => {
  document.body.style.overflow = "";
});

describe("useMobileDrawer: 状态机", () => {
  function makeHarness() {
    const openerRef = ref<HTMLElement | null>(null);
    const drawerRef = ref<HTMLElement | null>(null);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", name: "home", component: { template: "<div/>" }, meta: { title: "总览" } },
        { path: "/a", name: "a", component: { template: "<div/>" }, meta: { title: "A" } },
      ],
    });
    const apis: {
      open: Ref<boolean>;
      openDrawer: () => void;
      closeDrawer: (b?: boolean) => void;
      toggleDrawer: () => void;
      onDrawerKeydown: (e: KeyboardEvent) => void;
    } = {
      open: ref(false),
      openDrawer: () => {},
      closeDrawer: () => {},
      toggleDrawer: () => {},
      onDrawerKeydown: () => {},
    };
    const Comp = defineComponent({
      setup() {
        const r = useMobileDrawer({ openerRef, drawerRef, route: router.currentRoute });
        apis.open = r.open;
        apis.openDrawer = r.openDrawer;
        apis.closeDrawer = r.closeDrawer;
        apis.toggleDrawer = r.toggleDrawer;
        apis.onDrawerKeydown = r.onDrawerKeydown;
        return { ...r, openerRef, drawerRef };
      },
      template: `
        <div>
          <button ref="openerRef" data-testid="opener">O</button>
          <aside ref="drawerRef">
            <button data-autofocus data-testid="auto">A</button>
            <button data-testid="b1">B1</button>
            <button data-testid="b2">B2</button>
          </aside>
        </div>
      `,
    });
    return { router, Comp, openerRef, drawerRef, apis };
  }

  async function setupHarness() {
    const h = makeHarness();
    await h.router.push("/");
    await h.router.isReady();
    await flushPromises();
    const wrapper = mount(h.Comp, { attachTo: document.body });
    await flushPromises();
    h.openerRef.value = wrapper.find('[data-testid="opener"]').element as HTMLElement;
    h.drawerRef.value = wrapper.find('aside').element as HTMLElement;
    return { wrapper, ...h.apis };
  }

  it("初始状态：open=false，body 未锁", async () => {
    const { open, closeDrawer } = await setupHarness();
    expect(open.value).toBe(false);
    expect(document.body.style.overflow).toBe("");
    closeDrawer();
  });

  it("openDrawer 切换状态 + body 锁", async () => {
    const { open, openDrawer, closeDrawer } = await setupHarness();
    openDrawer();
    await flushPromises();
    expect(open.value).toBe(true);
    expect(document.body.style.overflow).toBe("hidden");
    closeDrawer();
    await flushPromises();
    expect(open.value).toBe(false);
    expect(document.body.style.overflow).toBe("");
  });

  it("toggleDrawer 切换状态", async () => {
    const { open, toggleDrawer, closeDrawer } = await setupHarness();
    toggleDrawer();
    expect(open.value).toBe(true);
    toggleDrawer();
    expect(open.value).toBe(false);
    closeDrawer();
  });

  it("openDrawer idempotent：连续两次 open 不重复锁 body（overflow 不变）", async () => {
    const { openDrawer, closeDrawer } = await setupHarness();
    openDrawer();
    const overflow1 = document.body.style.overflow;
    openDrawer();
    expect(document.body.style.overflow).toBe(overflow1);
    expect(document.body.style.overflow).toBe("hidden");
    closeDrawer();
  });

  it("closeDrawer idempotent：连续两次 close 不抛错", async () => {
    const { openDrawer, closeDrawer } = await setupHarness();
    openDrawer();
    closeDrawer();
    closeDrawer();
    expect(document.body.style.overflow).toBe("");
  });
});

describe("useMobileDrawer: Escape 键关闭", () => {
  async function mountWithRouter() {
    const openerRef = ref<HTMLElement | null>(null);
    const drawerRef = ref<HTMLElement | null>(null);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", name: "home", component: { template: "<div/>" }, meta: { title: "总览" } },
      ],
    });
    await router.push("/");
    await router.isReady();
    await flushPromises();
    const apis: {
      open: Ref<boolean>;
      openDrawer: () => void;
      closeDrawer: (b?: boolean) => void;
    } = {
      open: ref(false),
      openDrawer: () => {},
      closeDrawer: () => {},
    };
    const Comp = defineComponent({
      setup() {
        const r = useMobileDrawer({ openerRef, drawerRef, route: router.currentRoute });
        apis.open = r.open;
        apis.openDrawer = r.openDrawer;
        apis.closeDrawer = r.closeDrawer;
        return { ...r, openerRef, drawerRef };
      },
      template: `<div><button ref="openerRef">O</button><aside ref="drawerRef"></aside></div>`,
    });
    const wrapper = mount(Comp, { attachTo: document.body });
    await flushPromises();
    openerRef.value = wrapper.find("button").element as HTMLElement;
    drawerRef.value = wrapper.find("aside").element as HTMLElement;
    return { wrapper, router, ...apis };
  }

  it("drawer open 时按 Escape 关闭（document 级监听）", async () => {
    const h = await mountWithRouter();
    h.openDrawer();
    expect(h.open.value).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await flushPromises();
    expect(h.open.value).toBe(false);
    h.closeDrawer();
  });

  it("drawer close 时按 Escape 不抛错（守卫）", async () => {
    const h = await mountWithRouter();
    expect(h.open.value).toBe(false);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(h.open.value).toBe(false);
  });
});

describe("useMobileDrawer: route change 关闭", () => {
  it("drawer open 时 router.push 触发 closeDrawer（returnFocus=false）", async () => {
    const openerRef = ref<HTMLElement | null>(null);
    const drawerRef = ref<HTMLElement | null>(null);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", name: "home", component: { template: "<div/>" }, meta: { title: "总览" } },
        { path: "/a", name: "a", component: { template: "<div/>" }, meta: { title: "A" } },
      ],
    });
    await router.push("/");
    await router.isReady();
    await flushPromises();
    let openRef: Ref<boolean> = ref(false);
    let openDrawerFn: () => void = () => {};
    let closeDrawerFn: (b?: boolean) => void = () => {};
    const Comp = defineComponent({
      setup() {
        const r = useMobileDrawer({ openerRef, drawerRef, route: router.currentRoute });
        // eslint-disable-next-line vue/no-ref-as-operand
        openRef = r.open;
        openDrawerFn = r.openDrawer;
        closeDrawerFn = r.closeDrawer;
        return { ...r, openerRef, drawerRef };
      },
      template: `<div><button ref="openerRef">O</button><aside ref="drawerRef"></aside></div>`,
    });
    const wrapper = mount(Comp, { attachTo: document.body });
    await flushPromises();
    openerRef.value = wrapper.find("button").element as HTMLElement;
    drawerRef.value = wrapper.find("aside").element as HTMLElement;
    openDrawerFn();
    expect(openRef.value).toBe(true);
    await router.push("/a");
    await flushPromises();
    expect(openRef.value).toBe(false);
    closeDrawerFn();
  });
});

describe("useMobileDrawer: 焦点管理", () => {
  async function mountWithFocusables() {
    const openerRef = ref<HTMLElement | null>(null);
    const drawerRef = ref<HTMLElement | null>(null);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: "/", name: "home", component: { template: "<div/>" }, meta: { title: "总览" } },
      ],
    });
    await router.push("/");
    await router.isReady();
    await flushPromises();
    const apis: {
      open: Ref<boolean>;
      openDrawer: () => void;
      closeDrawer: (b?: boolean) => void;
      onDrawerKeydown: (e: KeyboardEvent) => void;
    } = {
      open: ref(false),
      openDrawer: () => {},
      closeDrawer: () => {},
      onDrawerKeydown: () => {},
    };
    const Comp = defineComponent({
      setup() {
        const r = useMobileDrawer({ openerRef, drawerRef, route: router.currentRoute });
        apis.open = r.open;
        apis.openDrawer = r.openDrawer;
        apis.closeDrawer = r.closeDrawer;
        apis.onDrawerKeydown = r.onDrawerKeydown;
        return { ...r, openerRef, drawerRef };
      },
      template: `
        <div>
          <button ref="openerRef" data-testid="opener">O</button>
          <aside ref="drawerRef">
            <button data-autofocus data-testid="auto">A</button>
            <button data-testid="b1">B1</button>
            <button data-testid="b2">B2</button>
          </aside>
        </div>
      `,
    });
    const wrapper = mount(Comp, { attachTo: document.body });
    await flushPromises();
    openerRef.value = wrapper.find('[data-testid="opener"]').element as HTMLElement;
    drawerRef.value = wrapper.find("aside").element as HTMLElement;
    return { wrapper, ...apis, openerRef };
  }

  it("openDrawer 把焦点移到 data-autofocus 元素", async () => {
    const h = await mountWithFocusables();
    h.openDrawer();
    await nextTick();
    await flushPromises();
    const autoEl = document.querySelector('[data-testid="auto"]') as HTMLElement;
    expect(document.activeElement).toEqual(autoEl);
    h.closeDrawer(false);
  });

  it("closeDrawer(returnFocus=true) 把焦点返回 opener", async () => {
    const h = await mountWithFocusables();
    h.openDrawer();
    await flushPromises();
    h.closeDrawer();
    await nextTick();
    await flushPromises();
    const opener = document.querySelector('[data-testid="opener"]') as HTMLElement;
    expect(document.activeElement).toEqual(opener);
  });

  it("closeDrawer(returnFocus=false) 不修改焦点", async () => {
    const h = await mountWithFocusables();
    h.openDrawer();
    await flushPromises();
    // 手动聚焦某非 opener 元素
    const b1 = document.querySelector('[data-testid="b1"]') as HTMLElement;
    b1.focus();
    expect(document.activeElement).toEqual(b1);
    h.closeDrawer(false);
    await flushPromises();
    expect(document.activeElement).toEqual(b1);
  });
});

describe("useMobileDrawer: Tab 焦点循环", () => {
  it("drawer 内 Tab 在最后一个聚焦元素按 Tab 跳到第一个", async () => {
    const openerRef = ref<HTMLElement | null>(null);
    const drawerRef = ref<HTMLElement | null>(null);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", name: "home", component: { template: "<div/>" }, meta: { title: "总览" } }],
    });
    await router.push("/");
    await router.isReady();
    await flushPromises();
    let onDrawerKeydown: (e: KeyboardEvent) => void = () => {};
    let openDrawer: () => void = () => {};
    let closeDrawer: (b?: boolean) => void = () => {};
    const Comp = defineComponent({
      setup() {
        const r = useMobileDrawer({ openerRef, drawerRef, route: router.currentRoute });
        onDrawerKeydown = r.onDrawerKeydown;
        openDrawer = r.openDrawer;
        closeDrawer = r.closeDrawer;
        return { ...r, openerRef, drawerRef };
      },
      template: `
        <div>
          <button ref="openerRef">O</button>
          <aside ref="drawerRef">
            <button data-autofocus>A</button>
            <button>B1</button>
            <button>B2</button>
          </aside>
        </div>
      `,
    });
    const wrapper = mount(Comp, { attachTo: document.body });
    await flushPromises();
    openerRef.value = wrapper.find("button").element as HTMLElement;
    drawerRef.value = wrapper.find("aside").element as HTMLElement;
    openDrawer();
    await flushPromises();
    const aside = wrapper.find("aside").element as HTMLElement;
    const focusables = aside.querySelectorAll<HTMLElement>("button");
    const last = focusables[focusables.length - 1];
    last.focus();
    expect(document.activeElement).toBe(last);
    // 触发 Tab
    onDrawerKeydown(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    expect(document.activeElement).toEqual(focusables[0]);
    closeDrawer(false);
  });
});

describe("useMobileDrawer: onUnmounted 清理 body overflow", () => {
  it("组件卸载时若 drawer 仍 open，恢复 body overflow", async () => {
    const openerRef = ref<HTMLElement | null>(null);
    const drawerRef = ref<HTMLElement | null>(null);
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: "/", name: "home", component: { template: "<div/>" }, meta: { title: "总览" } }],
    });
    await router.push("/");
    await router.isReady();
    await flushPromises();
    let openDrawerFn: () => void = () => {};
    const Comp = defineComponent({
      setup() {
        const r = useMobileDrawer({ openerRef, drawerRef, route: router.currentRoute });
        openDrawerFn = r.openDrawer;
        return { ...r, openerRef, drawerRef };
      },
      template: `<div><button ref="openerRef">O</button><aside ref="drawerRef"></aside></div>`,
    });
    const wrapper = mount(Comp, { attachTo: document.body });
    await flushPromises();
    openerRef.value = wrapper.find("button").element as HTMLElement;
    drawerRef.value = wrapper.find("aside").element as HTMLElement;
    openDrawerFn();
    expect(document.body.style.overflow).toBe("hidden");
    wrapper.unmount();
    expect(document.body.style.overflow).toBe("");
  });
});