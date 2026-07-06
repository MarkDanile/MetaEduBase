/**
 * REQ-052 Task 6: QueryPanel 行为锁。
 *
 * - 渲染表单 (select + question + business_purpose 输入框)。
 * - business_purpose minlength=5（与后端 pydantic 双重 enforce）。
 * - submit 时调用 ask()，并把结果写入 Pinia history store。
 * - datasetId 作为 informational prop 渲染（不影响请求体）。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

const { mockAsk } = vi.hoisted(() => ({
  mockAsk: vi.fn(),
}));

vi.mock("@/services/data-query", () => ({
  ask: mockAsk,
}));

import QueryPanel from "./QueryPanel.vue";
import { useQueryHistory } from "@/stores/query-history";

describe("QueryPanel.vue (REQ-052 Task 6)", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    mockAsk.mockReset();
  });

  it("renders form (select + question + business_purpose)", () => {
    const wrapper = mount(QueryPanel);
    expect(wrapper.find("select").exists()).toBe(true);
    expect(wrapper.find('input[placeholder*="自然语言"]').exists()).toBe(true);
    expect(wrapper.find('input[placeholder*="查询背景"]').exists()).toBe(true);
  });

  it("requires business_purpose min 5 chars (UI enforce)", () => {
    const wrapper = mount(QueryPanel);
    const input = wrapper.find('input[placeholder*="查询背景"]');
    expect(input.attributes("minlength")).toBe("5");
    expect(input.attributes("required")).toBeDefined();
  });

  it("shows datasetId badge when datasetId prop is provided", () => {
    const wrapper = mount(QueryPanel, {
      props: { datasetId: "ds-abc-123" },
    });
    expect(wrapper.find('[data-testid="dataset-id-badge"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("ds-abc-123");
  });

  it("omits datasetId badge when datasetId prop is absent", () => {
    const wrapper = mount(QueryPanel);
    expect(wrapper.find('[data-testid="dataset-id-badge"]').exists()).toBe(false);
  });

  it("calls ask() on submit and records history entry", async () => {
    mockAsk.mockResolvedValue({
      ok: true,
      result_rows: [{ id: 1 }],
      result_count: 1,
      summary: "ok",
      duration_ms: 12,
      confidence: "high",
    });

    const wrapper = mount(QueryPanel);
    await wrapper.find('input[placeholder*="自然语言"]').setValue("这企业欠费多少");
    await wrapper.find('input[placeholder*="企业全称"]').setValue("江苏神码");
    await wrapper.find('input[placeholder*="查询背景"]').setValue("评估信用风险");
    await wrapper.find("form").trigger("submit");

    expect(mockAsk).toHaveBeenCalledTimes(1);
    const callArg = mockAsk.mock.calls[0][0];
    expect(callArg.entity_type).toBe("bill");
    expect(callArg.question).toBe("这企业欠费多少");
    expect(callArg.business_purpose).toBe("评估信用风险");
    expect(callArg.confirmed_company_name).toBe("江苏神码");

    const history = useQueryHistory();
    expect(history.entries.length).toBe(1);
    expect(history.entries[0].request.question).toBe("这企业欠费多少");
  });

  it("skips ask() when business_purpose is too short", async () => {
    const wrapper = mount(QueryPanel);
    await wrapper.find('input[placeholder*="自然语言"]').setValue("这企业欠费多少");
    await wrapper.find('input[placeholder*="查询背景"]').setValue("1234"); // 4 chars < 5
    await wrapper.find("form").trigger("submit");

    expect(mockAsk).not.toHaveBeenCalled();
  });

  it("omits confirmed_company_name when company name is empty", async () => {
    mockAsk.mockResolvedValue({ ok: true, result_rows: [], result_count: 0 });

    const wrapper = mount(QueryPanel);
    await wrapper.find('input[placeholder*="自然语言"]').setValue("这企业欠费多少");
    await wrapper.find('input[placeholder*="查询背景"]').setValue("评估信用风险");
    // leave company name blank
    await wrapper.find("form").trigger("submit");

    expect(mockAsk).toHaveBeenCalledTimes(1);
    const callArg = mockAsk.mock.calls[0][0];
    expect("confirmed_company_name" in callArg).toBe(false);
  });

  it("renders success summary + result count on ok response", async () => {
    mockAsk.mockResolvedValue({
      ok: true,
      summary: "找到 3 条账单记录",
      result_rows: [{ id: 1, amount: 100 }],
      result_count: 3,
      duration_ms: 42,
      confidence: "high",
    });

    const wrapper = mount(QueryPanel);
    await wrapper.find('input[placeholder*="自然语言"]').setValue("测试问题");
    await wrapper.find('input[placeholder*="查询背景"]').setValue("随便问问背景");
    await wrapper.find("form").trigger("submit");
    await vi.waitFor(() => expect(wrapper.text()).toContain("找到 3 条账单记录"));
    expect(wrapper.text()).toContain("共 3 条记录");
  });

  it("renders error messages + suggestion on failed response", async () => {
    mockAsk.mockResolvedValue({
      ok: false,
      errors: ["缺少必要权限", "company 不存在"],
      suggestion: "请先上传企业认证材料",
    });

    const wrapper = mount(QueryPanel);
    await wrapper.find('input[placeholder*="自然语言"]').setValue("测试问题");
    await wrapper.find('input[placeholder*="查询背景"]').setValue("随便问问背景");
    await wrapper.find("form").trigger("submit");
    await vi.waitFor(() => expect(wrapper.text()).toContain("查询失败"));
    expect(wrapper.text()).toContain("缺少必要权限");
    expect(wrapper.text()).toContain("company 不存在");
    expect(wrapper.text()).toContain("请先上传企业认证材料");
  });
});