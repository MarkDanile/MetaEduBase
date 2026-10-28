import { defineComponent, nextTick, ref } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import { useChatScroll } from "../useChatScroll";

function mountScroll() {
  let api: ReturnType<typeof useChatScroll>;
  const Host = defineComponent({
    setup() {
      const container = ref<HTMLElement | null>(null);
      api = useChatScroll(container);
      return { container, showBackToLatest: api.showBackToLatest, scrollToLatest: api.scrollToLatest };
    },
    template: `
      <div ref="container">
        <button v-if="showBackToLatest" class="back" @click="scrollToLatest(true)">回到最新</button>
      </div>
    `,
  });
  const wrapper = mount(Host);
  const element = wrapper.element as HTMLElement;
  Object.defineProperty(element, "scrollHeight", { configurable: true, value: 1000, writable: true });
  Object.defineProperty(element, "clientHeight", { configurable: true, value: 200, writable: true });
  return { wrapper, element, api: api! };
}

describe("useChatScroll (DB-03)", () => {
  it("贴近底部时跟随新增内容", async () => {
    const { element, api } = mountScroll();
    element.scrollTop = 760;
    api.updateScrollState();
    api.notifyContentChanged();
    await nextTick();
    expect(element.scrollTop).toBe(1000);
    expect(api.showBackToLatest.value).toBe(false);
  });

  it("向上阅读后保持位置并显示回到最新", async () => {
    const { element, api } = mountScroll();
    element.scrollTop = 240;
    api.updateScrollState();
    api.notifyContentChanged();
    await nextTick();
    expect(element.scrollTop).toBe(240);
    expect(api.showBackToLatest.value).toBe(true);
  });

  it("回到最新恢复跟随并隐藏控制", async () => {
    const { wrapper, element, api } = mountScroll();
    element.scrollTop = 100;
    api.updateScrollState();
    await nextTick();
    await wrapper.find("button.back").trigger("click");
    await nextTick();
    expect(element.scrollTop).toBe(1000);
    expect(api.showBackToLatest.value).toBe(false);
  });
});
