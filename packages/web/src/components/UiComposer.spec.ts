/**
 * REQ-064 S1b-2：共享 `UiComposer` 行为锁（design spec §3 / roadmap §4.2 G1）。
 *
 * 契约要点（design spec §3 原文约束）：
 * - 受控 `modelValue`；事件**仅** `update:modelValue` / `submit` / `stop`；
 * - 提交必须同时满足 `mode === "ready" && canSubmit && modelValue.trim().length > 0`
 *   且输入法非 composing；按钮与键盘入口共用这一条件；
 * - `ready + canSubmit=false` 仍可编辑草稿；
 * - `readonly` 保留可读取内容但禁止编辑 / 提交；`unavailable` 禁用输入并给出原因；
 * - `busy` 禁止编辑和再次提交；仅 `mode === "busy" && canStop` 时显示并允许停止；
 * - 组件不请求 API、不选择模型、不管理 Conversation，也不推断租户权限。
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";

import UiComposer from "@/components/UiComposer.vue";

type Mode = "ready" | "busy" | "readonly" | "unavailable";

function makeComposer(overrides: Partial<{
  modelValue: string;
  mode: Mode;
  canSubmit: boolean;
  canStop: boolean;
  placeholder: string;
  hint: string;
  inputLabel: string;
}> = {}) {
  return mount(UiComposer, {
    props: {
      modelValue: "",
      mode: "ready" as Mode,
      canSubmit: false,
      canStop: false,
      placeholder: "输入消息",
      hint: undefined,
      inputLabel: "消息输入框",
      ...overrides,
    },
  });
}

describe("UiComposer（design spec §3 契约）", () => {
  it("暴露可访问名称：label 绑定输入框", () => {
    const wrapper = makeComposer({ inputLabel: "消息输入框" });
    const label = wrapper.find("label");
    const textarea = wrapper.find("textarea");
    expect(label.text()).toBe("消息输入框");
    expect(label.attributes("for")).toBe(textarea.attributes("id"));
  });

  it("受控：输入只通过 update:modelValue 回传，文本由父级 prop 驱动", async () => {
    const wrapper = makeComposer({ modelValue: "草稿" });
    const textarea = wrapper.find("textarea");
    expect((textarea.element as HTMLTextAreaElement).value).toBe("草稿");

    await textarea.setValue("新的草稿");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["新的草稿"]);
    // 组件不持有自己的文本副本：父级回传什么，DOM 就显示什么
    await wrapper.setProps({ modelValue: "父级确认的值" });
    expect((textarea.element as HTMLTextAreaElement).value).toBe("父级确认的值");
  });

  it("事件面只声明 update:modelValue / submit / stop", () => {
    const wrapper = makeComposer({ modelValue: "内容", canSubmit: true });
    // 组件声明的 emits 就是契约本身（design spec §3：事件仅为这三个）
    const emits = (wrapper.vm.$options.emits ?? {}) as
      | string[]
      | Record<string, unknown>;
    const declared = Array.isArray(emits)
      ? [...emits].sort()
      : Object.keys(emits).sort();
    expect(declared).toEqual(["stop", "submit", "update:modelValue"]);
  });

  it("点击发送只触发 submit，不触发 stop", async () => {
    const wrapper = makeComposer({ modelValue: "内容", canSubmit: true });
    await wrapper.find(".ui-composer-submit").trigger("click");
    expect(wrapper.emitted("submit")).toHaveLength(1);
    expect(wrapper.emitted("stop")).toBeUndefined();
  });

  it("提交门槛：ready + canSubmit + 非空白三者同时满足才可提交", async () => {
    const enabled = makeComposer({ modelValue: "内容", canSubmit: true });
    expect(enabled.find(".ui-composer-submit").attributes("disabled")).toBeUndefined();

    const blank = makeComposer({ modelValue: "   ", canSubmit: true });
    expect(blank.find(".ui-composer-submit").attributes("disabled")).toBeDefined();

    const notAllowed = makeComposer({ modelValue: "内容", canSubmit: false });
    expect(notAllowed.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
  });

  it("mode 非 ready 时一律不可提交", async () => {
    for (const mode of ["busy", "readonly", "unavailable"] as Mode[]) {
      const wrapper = makeComposer({ modelValue: "内容", canSubmit: true, mode });
      expect(wrapper.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
    }
  });

  it("ready + canSubmit=false 仍可编辑草稿", async () => {
    const wrapper = makeComposer({ modelValue: "草稿", canSubmit: false });
    const textarea = wrapper.find("textarea");
    expect(textarea.attributes("readonly")).toBeUndefined();
    expect(textarea.attributes("disabled")).toBeUndefined();
    await textarea.setValue("继续编辑");
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["继续编辑"]);
  });

  it("readonly：保留可读取内容但禁止编辑与提交", () => {
    const wrapper = makeComposer({ modelValue: "只读内容", mode: "readonly" });
    const textarea = wrapper.find("textarea");
    expect((textarea.element as HTMLTextAreaElement).value).toBe("只读内容");
    expect(textarea.attributes("readonly")).toBeDefined();
    expect(wrapper.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
  });

  it("unavailable：禁用输入并给出原因", () => {
    const wrapper = makeComposer({
      mode: "unavailable",
      hint: "当前空间无提问权限",
    });
    const textarea = wrapper.find("textarea");
    expect(textarea.attributes("disabled")).toBeDefined();
    expect(wrapper.find(".ui-composer-hint").text()).toBe("当前空间无提问权限");
    expect(textarea.attributes("aria-describedby")).toBe(
      wrapper.find(".ui-composer-hint").attributes("id"),
    );
  });

  it("unavailable 未传 hint 时仍给出缺省原因（design spec §3 要求给出原因）", () => {
    const wrapper = makeComposer({ mode: "unavailable" });
    const hint = wrapper.find(".ui-composer-hint");
    expect(hint.exists()).toBe(true);
    expect(hint.text().length).toBeGreaterThan(0);
    expect(wrapper.find("textarea").attributes("aria-describedby")).toBe(
      hint.attributes("id"),
    );
  });

  it("busy：禁止编辑与再次提交；仅 canStop 时显示并允许停止", async () => {
    const withStop = makeComposer({
      modelValue: "内容",
      mode: "busy",
      canStop: true,
    });
    expect(withStop.find("textarea").attributes("disabled")).toBeDefined();
    expect(withStop.find(".ui-composer-submit").attributes("disabled")).toBeDefined();
    expect(withStop.find(".ui-composer-stop").exists()).toBe(true);
    expect(withStop.attributes("aria-busy")).toBe("true");

    await withStop.find(".ui-composer-stop").trigger("click");
    expect(withStop.emitted("stop")).toHaveLength(1);

    const withoutStop = makeComposer({ mode: "busy", canStop: false });
    expect(withoutStop.find(".ui-composer-stop").exists()).toBe(false);
    expect(withoutStop.emitted("stop")).toBeUndefined();
  });

  it("键盘入口与按钮共用同一提交条件", async () => {
    const wrapper = makeComposer({ modelValue: "内容", canSubmit: true });
    const textarea = wrapper.find("textarea");

    await textarea.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("submit")).toHaveLength(1);

    // Shift+Enter 是换行，不提交
    await textarea.trigger("keydown", { key: "Enter", shiftKey: true });
    expect(wrapper.emitted("submit")).toHaveLength(1);

    // 条件不满足时不提交
    const blocked = makeComposer({ modelValue: "   ", canSubmit: true });
    await blocked.find("textarea").trigger("keydown", { key: "Enter" });
    expect(blocked.emitted("submit")).toBeUndefined();
  });

  it("输入法组合中（composing）不得提交", async () => {
    const wrapper = makeComposer({ modelValue: "内容", canSubmit: true });
    const textarea = wrapper.find("textarea");

    await textarea.trigger("compositionstart");
    await textarea.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("submit")).toBeUndefined();

    await textarea.trigger("compositionend");
    await textarea.trigger("keydown", { key: "Enter" });
    expect(wrapper.emitted("submit")).toHaveLength(1);
  });

  it("附件与工具以具名插槽提供", () => {
    const wrapper = mount(UiComposer, {
      props: {
        modelValue: "",
        mode: "ready" as Mode,
        canSubmit: false,
        canStop: false,
        placeholder: "",
        inputLabel: "消息输入框",
      },
      slots: {
        attachments: "<span class=\"slot-attachment\">附件</span>",
        tools: "<button class=\"slot-tool\">工具</button>",
      },
    });
    expect(wrapper.find(".slot-attachment").exists()).toBe(true);
    expect(wrapper.find(".slot-tool").exists()).toBe(true);
    expect(wrapper.find(".ui-composer-attachments").exists()).toBe(true);
  });

  it("hint 缺省时不渲染说明区", () => {
    const wrapper = makeComposer();
    expect(wrapper.find(".ui-composer-hint").exists()).toBe(false);
  });
});
