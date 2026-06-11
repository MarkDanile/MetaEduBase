/**
 * REQ-010 AC-4: `EvidenceRefLink.vue` 样式 + 类型契约锁。
 *
 * 组件本身不通过 v-html mount（v-html 上下文无法 mount Vue 组件），
 * 真正渲染由 AiChatView.renderMarkdown() 后处理完成。本 spec 锁住：
 * 1. 组件 props 契约 (index + hasFile)
 * 2. 组件 class 契约 (.evidence-ref + ui-tag + ui-tag-blue)
 * 3. data-ref 与 href 同步
 * 4. hasFile=false 时降级为 span 不可点击
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import EvidenceRefLink from "./EvidenceRefLink.vue";

describe("EvidenceRefLink.vue (REQ-010 AC-4)", () => {
  it("hasFile=true 渲染可点击 a + .evidence-ref + ui-tag", () => {
    const wrapper = mount(EvidenceRefLink, {
      props: { index: 1, hasFile: true },
    });
    const a = wrapper.find("a.evidence-ref");
    expect(a.exists()).toBe(true);
    expect(a.attributes("data-ref")).toBe("1");
    expect(a.attributes("href")).toBe("#evidence-1");
    expect(a.text()).toBe("[1]");
    expect(a.classes()).toContain("ui-tag-blue");
  });

  it("hasFile=false 降级为 span + opacity-60", () => {
    const wrapper = mount(EvidenceRefLink, {
      props: { index: 2, hasFile: false },
    });
    const a = wrapper.find("a");
    expect(a.exists()).toBe(false);
    const span = wrapper.find("span.evidence-ref");
    expect(span.exists()).toBe(true);
    expect(span.attributes("data-ref")).toBe("2");
    expect(span.text()).toBe("[2]");
    expect(span.classes()).toContain("opacity-60");
  });

  it("index > 1 时 data-ref / href 同步", () => {
    const wrapper = mount(EvidenceRefLink, {
      props: { index: 5, hasFile: true },
    });
    const a = wrapper.find("a.evidence-ref");
    expect(a.attributes("data-ref")).toBe("5");
    expect(a.attributes("href")).toBe("#evidence-5");
    expect(a.text()).toBe("[5]");
  });

  it("v-html 注入契约：class 名必须包含 evidence-ref", () => {
    // 这条用例锁住"样式契约"：renderMarkdown 注入的 HTML 字符串的
    // class 名必须与本组件 .evidence-ref 一致，否则全局 click 委托
    // 会拿不到引用编号元素。
    const wrapper = mount(EvidenceRefLink, {
      props: { index: 1, hasFile: true },
    });
    expect(wrapper.find(".evidence-ref").exists()).toBe(true);
  });
});