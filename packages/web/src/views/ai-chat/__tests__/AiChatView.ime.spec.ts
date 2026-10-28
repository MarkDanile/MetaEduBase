import { beforeEach, describe, expect, it } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import AiChatComposer from "../AiChatComposer.vue";

let wrapper: VueWrapper | undefined;

function mountComposer(props: Partial<{
  modelValue: string;
  mode: "ready" | "busy" | "readonly" | "unavailable";
  canSubmit: boolean;
  canStop: boolean;
  hint: string;
}> = {}) {
  wrapper?.unmount();
  wrapper = mount(AiChatComposer, {
    props: { modelValue: "中文草稿", ...props },
  });
  return wrapper;
}

beforeEach(() => wrapper?.unmount());

describe("AiChatComposer + UiComposer integration", () => {
  it("保留真实 textarea 的 chat-input 定位点并转发受控输入", async () => {
    const chat = mountComposer();
    const input = chat.find('[data-testid="chat-input"]');
    expect(input.element.tagName).toBe("TEXTAREA");
    await input.setValue("新的问题");
    expect(chat.emitted("update:modelValue")?.at(-1)).toEqual(["新的问题"]);
  });

  it("Enter 提交、Shift+Enter 换行，IME composing 不提交", async () => {
    const chat = mountComposer();
    const input = chat.find("textarea");
    await input.trigger("compositionstart");
    await input.trigger("keydown", { key: "Enter" });
    expect(chat.emitted("submit")).toBeUndefined();

    await input.trigger("compositionend");
    await input.trigger("keydown", { key: "Enter", shiftKey: true });
    expect(chat.emitted("submit")).toBeUndefined();

    await input.trigger("keydown", { key: "Enter" });
    expect(chat.emitted("submit")).toHaveLength(1);
  });

  it("busy 禁止编辑和重复提交，只转发停止", async () => {
    const chat = mountComposer({ mode: "busy", canStop: true });
    expect(chat.find("textarea").attributes("disabled")).toBeDefined();
    expect(chat.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
    await chat.find(".ui-composer-stop").trigger("click");
    expect(chat.emitted("stop")).toHaveLength(1);
    expect(chat.emitted("submit")).toBeUndefined();
  });

  it("readonly 保留草稿但禁止编辑和提交", () => {
    const chat = mountComposer({ mode: "readonly" });
    expect(chat.find("textarea").attributes("readonly")).toBeDefined();
    expect(chat.find("textarea").attributes("disabled")).toBeUndefined();
    expect(chat.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
  });

  it("unavailable 禁用输入并展示父级提供的原因", () => {
    const chat = mountComposer({ mode: "unavailable", hint: "当前会话不可提问" });
    expect(chat.find("textarea").attributes("disabled")).toBeDefined();
    expect(chat.find(".ui-composer-hint").text()).toBe("当前会话不可提问");
    expect(chat.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
  });

  it("父级清空草稿后自动回缩，长文本按 scrollHeight 增高", async () => {
    const chat = mountComposer({ modelValue: "" });
    const input = chat.find("textarea");
    const element = input.element as HTMLTextAreaElement;
    Object.defineProperty(element, "scrollHeight", { configurable: true, value: 220 });
    await chat.setProps({ modelValue: "第一行\n第二行\n第三行" });
    expect(element.style.height).toBe("220px");

    Object.defineProperty(element, "scrollHeight", { configurable: true, value: 24 });
    await chat.setProps({ modelValue: "" });
    expect(element.style.height).toBe("24px");
  });
});
