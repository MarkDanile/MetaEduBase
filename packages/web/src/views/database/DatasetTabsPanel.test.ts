/**
 * REQ-064 S4 数据预览分页：DatasetTabsPanel 分页控件行为锁（D-P1=3a + D-P2=B）。
 *
 * - 上一页在首页（canGoPrev=false）禁用；下一页在无下一页（hasNextPage=false）禁用。
 * - 点击分别 emit `change-page` 的 -1 / +1。
 * - 加载中两个按钮都禁用。
 * - 只在"可回上一页"或"有下一页"时渲染分页控件。
 * - **不展示总条数/总页数**：只显示当前页序号，不出现 "共 N 行" 一类总数文案。
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import DatasetTabsPanel from "./DatasetTabsPanel.vue";
import type { DatasetDTO } from "@/services/structured-data";

function makeDataset(overrides: Partial<DatasetDTO> = {}): DatasetDTO {
  return {
    id: "ds-1",
    tenant_id: "t-1",
    name: "账单数据集",
    description: null,
    column_names: ["id", "amount"],
    column_types: null,
    row_count: 999,
    source_file: null,
    tags: [],
    status: "ready",
    kg_status: "ready",
    sort_order: 0,
    entity_type: "bill",
    created_by: "u-1",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    ...overrides,
  };
}

function makeRows(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `row-${i}`,
    dataset_id: "ds-1",
    row_index: i,
    data: { id: i, amount: i * 10 },
    created_at: "2026-01-01T00:00:00",
  }));
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(DatasetTabsPanel, {
    props: {
      selected: makeDataset(),
      rows: makeRows(20),
      kgNodes: [],
      kgEdges: [],
      page: 0,
      hasNextPage: true,
      canGoPrev: false,
      loadingRows: false,
      loadingKg: false,
      activeTab: "preview",
      ...props,
    },
  });
}

describe("DatasetTabsPanel.vue (REQ-064 S4 数据预览分页控件)", () => {
  it("renders the rows of the current page", () => {
    const wrapper = mountPanel({ rows: makeRows(3) });
    const bodyRows = wrapper.findAll("tbody tr");
    expect(bodyRows.length).toBe(3);
    expect(bodyRows[0].text()).toContain("0");
  });

  it("disables 上一页 on the first page", () => {
    const wrapper = mountPanel({ page: 0, canGoPrev: false, hasNextPage: true });
    const prev = wrapper.find('[data-testid="dataset-rows-prev"]');
    expect(prev.attributes("disabled")).toBeDefined();
  });

  it("disables 下一页 when there is no next page", () => {
    const wrapper = mountPanel({ page: 1, canGoPrev: true, hasNextPage: false });
    const next = wrapper.find('[data-testid="dataset-rows-next"]');
    expect(next.attributes("disabled")).toBeDefined();
  });

  it("enables 下一页 when the probe found a next page", () => {
    const wrapper = mountPanel({ page: 0, canGoPrev: false, hasNextPage: true });
    const next = wrapper.find('[data-testid="dataset-rows-next"]');
    expect(next.attributes("disabled")).toBeUndefined();
  });

  it("enables 上一页 once the user moved off the first page", () => {
    const wrapper = mountPanel({ page: 1, canGoPrev: true, hasNextPage: true });
    const prev = wrapper.find('[data-testid="dataset-rows-prev"]');
    expect(prev.attributes("disabled")).toBeUndefined();
  });

  it("emits change-page -1 / +1 on click", async () => {
    const wrapper = mountPanel({ page: 1, canGoPrev: true, hasNextPage: true });
    await wrapper.find('[data-testid="dataset-rows-prev"]').trigger("click");
    await wrapper.find('[data-testid="dataset-rows-next"]').trigger("click");
    expect(wrapper.emitted("change-page")).toEqual([[-1], [1]]);
  });

  it("disables both buttons while loading", () => {
    const wrapper = mountPanel({
      page: 1,
      canGoPrev: true,
      hasNextPage: true,
      loadingRows: true,
    });
    expect(wrapper.find('[data-testid="dataset-rows-prev"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-testid="dataset-rows-next"]').attributes("disabled")).toBeDefined();
  });

  it("hides the pagination block when there is nowhere to go", () => {
    const wrapper = mountPanel({ page: 0, canGoPrev: false, hasNextPage: false });
    expect(wrapper.find('[data-testid="dataset-rows-pagination"]').exists()).toBe(false);
  });

  it("shows the current page index but no total rows / total pages", () => {
    const wrapper = mountPanel({ page: 2, canGoPrev: true, hasNextPage: true });
    const indicator = wrapper.find('[data-testid="dataset-rows-page-indicator"]');
    expect(indicator.exists()).toBe(true);
    expect(indicator.text()).toContain("第 3 页");
    // 不得出现总条数 / 总页数文案
    expect(wrapper.text()).not.toContain("共 ");
    expect(wrapper.text()).not.toContain("总页");
    // 分页块内不得出现行数/总页数文案，也不得展示数据集元数据 row_count
    const paginationText = wrapper.find('[data-testid="dataset-rows-pagination"]').text();
    expect(paginationText).not.toContain("行");
    expect(paginationText).not.toContain(String(makeDataset().row_count));
  });
});
