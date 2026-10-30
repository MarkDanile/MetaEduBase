import { defineComponent, nextTick, ref } from "vue";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useChatScroll } from "../useChatScroll";

/** jsdom 没有 ResizeObserver；用可控替身驱动尺寸变化分支。 */
let resizeCallbacks: Array<() => void> = [];

beforeEach(() => {
  resizeCallbacks = [];
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        resizeCallbacks.push(callback);
      }
      observe(): void {}
      disconnect(): void {}
    },
  );
});

function mountScroll() {
  let api: ReturnType<typeof useChatScroll>;
  const Host = defineComponent({
    setup() {
      const container = ref<HTMLElement | null>(null);
      const content = ref<HTMLElement | null>(null);
      api = useChatScroll(container, content);
      return {
        container,
        content,
        showBackToLatest: api.showBackToLatest,
        following: api.following,
        scrollToLatest: api.scrollToLatest,
        updateScrollState: api.updateScrollState,
      };
    },
    template: `
      <div ref="container">
        <div ref="content"></div>
        <button v-if="showBackToLatest" class="back" @click="scrollToLatest(true)">回到最新</button>
      </div>
    `,
  });
  const wrapper = mount(Host);
  const element = wrapper.element as HTMLElement;
  const contentElement = wrapper.find("div div").element as HTMLElement;

  let scrollHeight = 1000;
  let clientHeight = 400;
  Object.defineProperty(element, "scrollHeight", {
    configurable: true,
    get: () => scrollHeight,
  });
  Object.defineProperty(element, "clientHeight", {
    configurable: true,
    get: () => clientHeight,
  });

  return {
    wrapper,
    element,
    contentElement,
    api: api!,
    resize(): void {
      scrollHeight = Number(scrollHeight);
    },
    setSize(nextScrollHeight: number, nextClientHeight: number): void {
      scrollHeight = nextScrollHeight;
      clientHeight = nextClientHeight;
    },
    fireResize(): void {
      resizeCallbacks.forEach((callback) => callback());
    },
    remaining(): number {
      return scrollHeight - element.scrollTop - clientHeight;
    },
  };
}

describe("useChatScroll (DB-03 跟随状态)", () => {
  it("用户主动上滑时暂停跟随、保留位置并显示回到最新", async () => {
    const harness = mountScroll();
    harness.element.scrollTop = 600;
    harness.api.updateScrollState();
    expect(harness.api.following.value).toBe(true);
    expect(harness.api.showBackToLatest.value).toBe(false);

    harness.element.scrollTop = 120;
    harness.api.updateScrollState();
    expect(harness.api.following.value).toBe(false);
    expect(harness.api.showBackToLatest.value).toBe(true);
    expect(harness.element.scrollTop).toBe(120);
  });

  it("Composer 增高导致的可见高度变化不被误判为用户上滑，并保持贴底", () => {
    const harness = mountScroll();
    harness.element.scrollTop = 600;
    harness.api.updateScrollState();
    expect(harness.api.following.value).toBe(true);

    // Composer 增高 → 容器变矮（clientHeight 400 → 260），内容高度不变
    harness.setSize(1000, 260);
    harness.fireResize();

    expect(harness.element.scrollTop).toBe(740);
    expect(harness.remaining()).toBe(0);
    expect(harness.api.following.value).toBe(true);
    expect(harness.api.showBackToLatest.value).toBe(false);
  });

  it("可见视口收缩（移动键盘）后仍贴底，消息尾部保持可见", () => {
    const harness = mountScroll();
    harness.element.scrollTop = 600;
    harness.api.updateScrollState();

    harness.setSize(1000, 120);
    harness.fireResize();

    expect(harness.element.scrollTop).toBe(880);
    expect(harness.remaining()).toBe(0);
    expect(harness.api.showBackToLatest.value).toBe(false);
  });

  it("内容增高时贴底用户跟随到最新，已上滑用户保持阅读位置", () => {
    const harness = mountScroll();
    harness.element.scrollTop = 600;
    harness.api.updateScrollState();
    harness.setSize(1400, 400);
    harness.fireResize();
    expect(harness.element.scrollTop).toBe(1000);
    expect(harness.remaining()).toBe(0);

    harness.element.scrollTop = 150;
    harness.api.updateScrollState();
    harness.setSize(1800, 400);
    harness.fireResize();
    expect(harness.element.scrollTop).toBe(150);
    expect(harness.api.following.value).toBe(false);
    expect(harness.api.showBackToLatest.value).toBe(true);
  });

  it("容器高度变化引起的 scroll 事件不会把跟随状态误判为用户上滑", () => {
    const harness = mountScroll();
    harness.element.scrollTop = 600;
    harness.api.updateScrollState();
    expect(harness.api.following.value).toBe(true);

    // Composer 增高 → 容器变矮：浏览器可能派发 scroll 事件（scrollTop 不变）
    harness.setSize(1000, 260);
    harness.api.updateScrollState();
    expect(harness.api.following.value).toBe(true);
    expect(harness.api.showBackToLatest.value).toBe(false);

    // 随后的尺寸回调重新贴底，尾部回到可视区
    harness.fireResize();
    expect(harness.remaining()).toBe(0);
    expect(harness.api.following.value).toBe(true);
  });

  it("回到最新恢复贴底并隐藏控件", async () => {
    const harness = mountScroll();
    harness.element.scrollTop = 600;
    harness.api.updateScrollState();
    harness.element.scrollTop = 120;
    harness.api.updateScrollState();
    await nextTick();
    await harness.wrapper.find("button.back").trigger("click");
    await nextTick();

    expect(harness.element.scrollTop).toBe(600);
    expect(harness.remaining()).toBe(0);
    expect(harness.api.following.value).toBe(true);
    expect(harness.api.showBackToLatest.value).toBe(false);
  });
});
