/**
 * REQ-046 / APP-005 Slice 5: DdReportView 报告展示 smoke（AC-6/7）。
 *
 * 覆盖：
 * 1. 渲染 §4.6 七键结构化报告（摘要 / 外部事实 / 内部事实 / 风险 / 待人工确认 + 正文分区）
 * 2. 空分区渲染「无」（AC-7）
 * 3. 草案可确认锁版（confirmReport）；确认后状态变为已确认
 * 4. 归档经 ConfirmDialog 确认后调用 archiveReport
 * 5. 证据来源抽屉加载并渲染证据行（listEvidence）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises, DOMWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";

const pushMock = vi.fn();
vi.mock("vue-router", () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => ({ params: { reportId: "report-1" } }),
}));

vi.mock("@/services/dueDiligence", () => ({
  getReport: vi.fn(),
  confirmReport: vi.fn(),
  archiveReport: vi.fn(),
  listEvidence: vi.fn(),
}));

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

// ConfirmDialog 默认 Teleport 到 body，测试里内联渲染便于查找。
vi.mock("@/components/ConfirmDialog.vue", () => ({
  default: defineComponent({
    name: "ConfirmDialog",
    props: {
      open: { type: Boolean, default: false },
      title: { type: String, default: "" },
      message: { type: String, default: "" },
    },
    emits: ["confirm", "cancel", "update:open"],
    setup(props, { emit }) {
      return () =>
        props.open
          ? h("div", { "data-testid": "confirm-dialog" }, [
              h("button", { "data-testid": "confirm-confirm", onClick: () => emit("confirm") }, "确认"),
            ])
          : null;
    },
  }),
}));

import DdReportView from "./DdReportView.vue";
import { getReport, confirmReport, archiveReport, listEvidence } from "@/services/dueDiligence";

const DRAFT_REPORT = {
  id: "report-1",
  task_id: "task-1",
  version: 1,
  status: "draft",
  report_json: {
    summary: ["整体经营稳定"],
    external_facts: ["工商登记正常"],
    internal_facts: ["在租合同 2 份"],
    risk_watch_items: ["存在一起被执行记录"],
    human_review_items: ["核对经营范围与招商准入"],
    evidence_refs: [],
    report_sections: [{ title: "综合评估", content: "建议准入，关注被执行风险。" }],
  },
  report_markdown: "# 报告",
  skill_execution_audit_id: "audit-uuid-12345678",
  confirmed_by: null,
  confirmed_at: null,
};

const CONFIRMED_REPORT = { ...DRAFT_REPORT, status: "confirmed", confirmed_by: "u-1", confirmed_at: "2026-07-22T00:00:00" };

const SAMPLE_EVIDENCE = [
  { id: "ev-1", evidence_type: "mcp_invocation", ref_id: "ref-mcp-1", section: "外部/内部客户事实", summary: "外部工商核验" },
  { id: "ev-2", evidence_type: "data_query", ref_id: "ref-q-1", section: "内部问数", summary: "欠费金额查询" },
];

let currentWrapper: ReturnType<typeof mount> | undefined;

async function mountView() {
  localStorage.setItem("metaedu_token", "test-token");
  localStorage.setItem("metaedu_role", "admin");
  setActivePinia(createPinia());
  const w = mount(DdReportView);
  currentWrapper = w;
  await flushPromises();
  return w;
}

function body(selector: string): DOMWrapper<Element> {
  const el = document.body.querySelector(selector);
  if (!el) throw new Error(`body: not found: ${selector}`);
  return new DOMWrapper(el);
}

describe("DdReportView.vue (REQ-046 / APP-005)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getReport).mockResolvedValue(DRAFT_REPORT as never);
    vi.mocked(listEvidence).mockResolvedValue(SAMPLE_EVIDENCE as never);
  });

  afterEach(() => {
    currentWrapper?.unmount();
    currentWrapper = undefined;
    localStorage.clear();
    // 清理 Teleport 到 body 的抽屉
    document.body.innerHTML = "";
  });

  it("renders seven-key structured report sections", async () => {
    const wrapper = await mountView();
    expect(wrapper.find('[data-testid="report-grid"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="sec-summary"]').text()).toContain("整体经营稳定");
    expect(wrapper.find('[data-testid="sec-external"]').text()).toContain("工商登记正常");
    expect(wrapper.find('[data-testid="sec-internal"]').text()).toContain("在租合同 2 份");
    expect(wrapper.find('[data-testid="sec-risk"]').text()).toContain("被执行记录");
    expect(wrapper.find('[data-testid="sec-review"]').text()).toContain("核对经营范围");
    expect(wrapper.find('[data-testid="sec-sections"]').text()).toContain("综合评估");
    // 草案状态 + 可确认
    expect(wrapper.find('[data-testid="report-status"]').text()).toContain("草案");
    expect(wrapper.find('[data-testid="confirm-report-btn"]').exists()).toBe(true);
  });

  it("renders 无 for empty partitions (AC-7)", async () => {
    vi.mocked(getReport).mockResolvedValue({
      ...DRAFT_REPORT,
      report_json: { summary: [], risk_watch_items: [], human_review_items: [] },
    } as never);
    const wrapper = await mountView();
    expect(wrapper.find('[data-testid="sec-summary-empty"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="sec-risk-empty"]').exists()).toBe(true);
  });

  it("confirm locks the report version", async () => {
    vi.mocked(confirmReport).mockResolvedValue(CONFIRMED_REPORT as never);
    const wrapper = await mountView();
    await wrapper.find('[data-testid="confirm-report-btn"]').trigger("click");
    await flushPromises();
    expect(confirmReport).toHaveBeenCalledWith("report-1");
    // 确认后状态变为已确认，确认按钮消失
    expect(wrapper.find('[data-testid="report-status"]').text()).toContain("已确认");
    expect(wrapper.find('[data-testid="confirm-report-btn"]').exists()).toBe(false);
  });

  it("archive goes through ConfirmDialog then calls archiveReport", async () => {
    vi.mocked(archiveReport).mockResolvedValue({ ...DRAFT_REPORT, status: "archived" } as never);
    const wrapper = await mountView();
    await wrapper.find('[data-testid="archive-report-btn"]').trigger("click");
    await flushPromises();
    await wrapper.find('[data-testid="confirm-confirm"]').trigger("click");
    await flushPromises();
    expect(archiveReport).toHaveBeenCalledWith("report-1");
  });

  it("evidence drawer loads and renders evidence rows", async () => {
    const wrapper = await mountView();
    await wrapper.find('[data-testid="evidence-btn"]').trigger("click");
    await flushPromises();
    expect(listEvidence).toHaveBeenCalledWith("report-1");
    const rows = body('[data-testid="evidence-drawer"]').findAll('[data-testid="evidence-row"]');
    expect(rows).toHaveLength(2);
    expect(body('[data-testid="evidence-drawer"]').text()).toContain("内部问数");
    expect(body('[data-testid="evidence-drawer"]').text()).toContain("外部工具");
    expect(body('[data-testid="evidence-drawer"]').text()).toContain("ref-mcp-1");
  });
});
