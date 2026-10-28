/**
 * REQ-064 S1b-2：共享组件采用与状态生产者的行为锁。
 *
 * 本切片把已合入的共享层契约落到**真实生产组件**上（S1b-1 建立的 opt-in 入口
 * 与状态类），这里锁定采用点与状态生产者：
 *
 * - `TableRenderer` 采用 `.ui-table` 表格契约（表头 / 单元格 / 行 / 空态行），
 *   长内容以 `title` 暴露完整值；
 * - `ConfirmDialog` 提交中采用 `.ui-dialog-busy`；
 * - `ImportTemplateDialog` 在解析 / 导入失败时给文件输入 `.is-error`；
 * - `ImportTemplateDialog` 导入进行中给文件输入 `.is-loading`。
 *
 * 这些是**真实生产者**（不是只有 CSS 规则没有使用方）。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";

import TableRenderer from "@/components/TableRenderer.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import ImportTemplateDialog from "@/components/ImportTemplateDialog.vue";

/** 导入请求保持 pending，用于观察提交中的加载态。 */
const importMock = vi.fn(() => new Promise<never>(() => {}));

vi.mock("@/services/template", () => ({
  templateApi: {
    import: (...args: unknown[]) => importMock(...(args as [])),
  },
}));


describe("S1b-2 共享组件采用（表格 / 确认弹窗 / 表单状态生产者）", () => {
  beforeEach(() => {
    importMock.mockClear();
  });

  it("TableRenderer 采用共享表格契约类", () => {
    const wrapper = mount(TableRenderer, {
      props: {
        columns: [{ key: "name", label: "名称", type: "text" }],
        rows: [{ name: "甲" }],
      },
    });
    expect(wrapper.find("table").classes()).toContain("ui-table");
    expect(wrapper.find("th").classes()).toContain("ui-table-header-cell");
    expect(wrapper.find("td").classes()).toContain("ui-table-cell");
    expect(wrapper.find("tbody tr").classes()).toContain("ui-table-row");
  });

  it("TableRenderer 空数据渲染共享空态行", () => {
    const wrapper = mount(TableRenderer, {
      props: { columns: [{ key: "name", label: "名称", type: "text" }], rows: [] },
    });
    const empty = wrapper.find(".ui-table-empty-cell");
    expect(empty.exists()).toBe(true);
    expect(empty.text()).toContain("暂无数据");
  });

  it("TableRenderer 长内容以 title 暴露完整值", () => {
    const long = "很长的一段内容".repeat(20);
    const wrapper = mount(TableRenderer, {
      props: {
        columns: [{ key: "name", label: "名称", type: "text" }],
        rows: [{ name: long }],
      },
    });
    const cell = wrapper.find("td");
    expect(cell.attributes("title")).toBe(long);
  });

  it("TableRenderer 空值不设置 title", () => {
    const wrapper = mount(TableRenderer, {
      props: {
        columns: [{ key: "name", label: "名称", type: "text" }],
        rows: [{ name: null }],
      },
    });
    expect(wrapper.find("td").attributes("title")).toBeUndefined();
  });

  it("TableRenderer 对象 / 数组值与 title 共用同一格式化（不出现 [object Object]）", () => {
    const wrapper = mount(TableRenderer, {
      props: {
        columns: [{ key: "meta", label: "元数据", type: "text" }],
        rows: [{ meta: { a: 1 }, other: [1, 2] }],
      },
    });
    const cell = wrapper.find("td");
    const shown = cell.text();
    expect(shown).toContain("{");
    expect(shown).not.toContain("[object Object]");
    expect(cell.attributes("title")).toBe(shown.trim());
  });

  it("ConfirmDialog 提交中采用 .ui-dialog-busy", async () => {
    const wrapper = mount(ConfirmDialog, {
      props: { open: true },
      // 对话框走 Teleport，测试内改为就地渲染才能查询 DOM
      global: { stubs: { teleport: true } },
      attachTo: document.body,
    });
    expect(wrapper.find(".ui-dialog").classes()).not.toContain("ui-dialog-busy");

    await wrapper.findAll("button")[1]?.trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.find(".ui-dialog").classes()).toContain("ui-dialog-busy");
    wrapper.unmount();
  });

  it("ImportTemplateDialog 解析失败时给文件输入 .is-error", async () => {
    const wrapper = mount(ImportTemplateDialog, {
      props: { open: true },
      // 对话框走 Teleport，测试内改为就地渲染才能查询 DOM
      global: { stubs: { teleport: true } },
      attachTo: document.body,
    });
    const fileInput = wrapper.find('input[type="file"]');
    expect(fileInput.classes()).not.toContain("is-error");

    const badFile = new File(["{not-json"], "bad.json", {
      type: "application/json",
    });
    Object.defineProperty(fileInput.element, "files", { value: [badFile] });
    await fileInput.trigger("change");
    await wrapper.vm.$nextTick();

    expect(wrapper.find(".error-box").exists()).toBe(true);
    expect(wrapper.find('input[type="file"]').classes()).toContain("is-error");
    wrapper.unmount();
  });

  it("ImportTemplateDialog 导入进行中给文件输入 .is-loading", async () => {
    const wrapper = mount(ImportTemplateDialog, {
      props: { open: true },
      // 对话框走 Teleport，测试内改为就地渲染才能查询 DOM
      global: { stubs: { teleport: true } },
      attachTo: document.body,
    });

    // 先用合法 JSON 触发预览（payload 就绪后提交按钮才可用）
    const goodFile = new File(
      [JSON.stringify({ format: "metaedu-template-v1", template: { name: "T", doc_types: ["invoice"], fields: [] } })],
      "ok.json",
      { type: "application/json" },
    );
    const fileInput = wrapper.find('input[type="file"]');
    Object.defineProperty(fileInput.element, "files", { value: [goodFile] });
    await fileInput.trigger("change");
    await wrapper.vm.$nextTick();

    const submitBtn = wrapper
      .findAll("button")
      .find((btn) => btn.classes().includes("ui-btn-primary"));
    expect(submitBtn).toBeDefined();
    expect(submitBtn!.attributes("disabled")).toBeUndefined();
    expect(wrapper.find('input[type="file"]').classes()).not.toContain("is-loading");

    await submitBtn!.trigger("click");
    await wrapper.vm.$nextTick();
    expect(wrapper.find('input[type="file"]').classes()).toContain("is-loading");
    wrapper.unmount();
  });
});
