/**
 * REQ-052 Task 6 + REQ-054 Task 8 + review fix + BUG-015: QueryPanel 行为锁。
 *
 * - 渲染表单 (catalog select + entity_type select + question)。
 * - BUG-015: business_purpose 与 companyName 输入框已移除 — ask()
 *   直接发送 catalog_id + entity_type + question 即可。
 * - submit 时调用 ask()，并把结果写入 Pinia history store。
 * - datasetId 作为 informational prop 渲染（不影响请求体）。
 * - REQ-054: 提交请求体必须含 catalog_id；切换 catalog 后 entity_type 重置。
 * - REQ-054: preSelectedCatalogId 锁定 catalog select。
 * - review fix #5: entity_type 下拉从 datasets 动态聚合（不再 hardcoded）。
 * - BUG-015: entity_type 为空的提示文案新增 "上传 CSV" 指引。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

const { mockAsk, mockListCatalogs, mockListDatasets } = vi.hoisted(() => ({
  mockAsk: vi.fn(),
  mockListCatalogs: vi.fn(),
  mockListDatasets: vi.fn(),
}));

vi.mock("@/services/data-query", () => ({
  ask: mockAsk,
}));

vi.mock("@/services/catalog", () => ({
  listCatalogs: mockListCatalogs,
}));

vi.mock("@/services/structured-data", () => ({
  structuredDataApi: {
    listDatasets: mockListDatasets,
  },
}));

import QueryPanel from "./QueryPanel.vue";
import { useQueryHistory } from "@/stores/query-history";
import { useCatalogStore } from "@/stores/catalog";

const SAMPLE_CATALOGS = [
  {
    id: "cat-fin",
    tenant_id: "t-1",
    code: "finance",
    name: "财务数据库",
    description: null,
    icon: null,
    color: null,
    entity_types: ["bill", "invoice"],
    default_business_purpose: null,
    is_active: true,
    created_by: "u-1",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
  },
  {
    id: "cat-hr",
    tenant_id: "t-1",
    code: "hr",
    name: "人力资源",
    description: null,
    icon: null,
    color: null,
    entity_types: ["employee"],
    default_business_purpose: null,
    is_active: true,
    created_by: "u-1",
    created_at: "2026-01-02T00:00:00",
    updated_at: "2026-01-02T00:00:00",
  },
];

// Datasets returned by listDatasets({ catalog_id }). entity_type is the
// discovered attribute the panel aggregates into the dropdown.
const DATASETS_BY_CATALOG: Record<string, { id: string; entity_type: string }[]> = {
  "cat-fin": [
    { id: "ds-1", entity_type: "bill" },
    { id: "ds-2", entity_type: "invoice" },
  ],
  "cat-hr": [
    { id: "ds-3", entity_type: "employee" },
  ],
};

async function mountPanel(props: { datasetId?: string; preSelectedCatalogId?: string | null } = {}) {
  setActivePinia(createPinia());
  const catalogStore = useCatalogStore();
  catalogStore.catalogs = SAMPLE_CATALOGS;
  catalogStore.loading = false;

  const wrapper = mount(QueryPanel, { props });
  await flushPromises();
  return wrapper;
}

describe("QueryPanel.vue (REQ-052 Task 6 + REQ-054 Task 8 + review fix + BUG-015)", () => {
  beforeEach(() => {
    mockAsk.mockReset();
    mockListCatalogs.mockReset().mockResolvedValue(SAMPLE_CATALOGS);
    mockListDatasets.mockReset().mockImplementation((params?: { catalog_id?: string }) => {
      const catId = params?.catalog_id ?? "";
      return Promise.resolve({ data: DATASETS_BY_CATALOG[catId] ?? [] });
    });
  });

  it("renders form (catalog select + entity_type select + question)", async () => {
    const wrapper = await mountPanel();
    expect(wrapper.find('[data-testid="catalog-select"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="entity-type-select"]').exists()).toBe(true);
    expect(wrapper.find('input[placeholder*="自然语言"]').exists()).toBe(true);
    // BUG-015: business_purpose / company_name inputs are gone.
    expect(wrapper.find('input[placeholder*="查询背景"]').exists()).toBe(false);
    expect(wrapper.find('input[placeholder*="企业全称"]').exists()).toBe(false);
  });

  it("shows datasetId badge when datasetId prop is provided", async () => {
    const wrapper = await mountPanel({ datasetId: "ds-abc-123" });
    expect(wrapper.find('[data-testid="dataset-id-badge"]').exists()).toBe(true);
    expect(wrapper.text()).toContain("ds-abc-123");
  });

  it("omits datasetId badge when datasetId prop is absent", async () => {
    const wrapper = await mountPanel();
    expect(wrapper.find('[data-testid="dataset-id-badge"]').exists()).toBe(false);
  });

  it("catalog select defaults to first catalog", async () => {
    const wrapper = await mountPanel();
    const catalogSelect = wrapper.find('[data-testid="catalog-select"]');
    expect((catalogSelect.element as HTMLSelectElement).value).toBe("cat-fin");
  });

  it("entity_type options are aggregated from selected catalog's datasets", async () => {
    const wrapper = await mountPanel();
    await flushPromises();
    const entitySelect = wrapper.find('[data-testid="entity-type-select"]');
    const options = entitySelect.findAll("option");
    const values = options.map((o) => o.attributes("value"));
    expect(values).toContain("bill");
    expect(values).toContain("invoice");
    expect(values).not.toContain("employee");
  });

  it("switching catalog re-fetches datasets and resets entity_type", async () => {
    const wrapper = await mountPanel();
    // Start with finance: bill/invoice
    await flushPromises();
    const catalogSelect = wrapper.find('[data-testid="catalog-select"]');
    await catalogSelect.setValue("cat-hr");
    await flushPromises();

    const entitySelect = wrapper.find('[data-testid="entity-type-select"]');
    const options = entitySelect.findAll("option");
    const values = options.map((o) => o.attributes("value"));
    expect(values).toContain("employee");
    expect(values).not.toContain("bill");
  });

  it("preSelectedCatalogId prop locks catalog select", async () => {
    const wrapper = await mountPanel({
      preSelectedCatalogId: "cat-hr",
    });
    const catalogSelect = wrapper.find('[data-testid="catalog-select"]');
    expect(catalogSelect.attributes("disabled")).toBeDefined();
    expect((catalogSelect.element as HTMLSelectElement).value).toBe("cat-hr");
  });

  it("calls ask() with catalog_id on submit (BUG-015: no business_purpose / company_name)", async () => {
    mockAsk.mockResolvedValue({
      ok: true,
      result_rows: [{ id: 1 }],
      result_count: 1,
      summary: "ok",
      duration_ms: 12,
      confidence: "high",
    });

    const wrapper = await mountPanel();
    await flushPromises();
    await wrapper.find('input[placeholder*="自然语言"]').setValue("这企业欠费多少");
    await wrapper.find("form").trigger("submit");

    expect(mockAsk).toHaveBeenCalledTimes(1);
    const callArg = mockAsk.mock.calls[0][0];
    expect(callArg.catalog_id).toBe("cat-fin"); // default first
    expect(callArg.entity_type).toBe("bill"); // first discovered in cat-fin datasets
    expect(callArg.question).toBe("这企业欠费多少");
    // BUG-015: business_purpose / confirmed_company_name 不再随请求体发送。
    expect("business_purpose" in callArg).toBe(false);
    expect("confirmed_company_name" in callArg).toBe(false);

    const history = useQueryHistory();
    expect(history.entries.length).toBe(1);
    expect(history.entries[0].request.catalog_id).toBe("cat-fin");
  });

  it("preSelectedCatalogId propagates to ask() request body", async () => {
    mockAsk.mockResolvedValue({ ok: true });

    const wrapper = await mountPanel({ preSelectedCatalogId: "cat-hr" });
    await flushPromises();
    await wrapper.find('input[placeholder*="自然语言"]').setValue("员工数");
    await wrapper.find("form").trigger("submit");

    expect(mockAsk).toHaveBeenCalledTimes(1);
    const callArg = mockAsk.mock.calls[0][0];
    expect(callArg.catalog_id).toBe("cat-hr");
    expect(callArg.entity_type).toBe("employee");
  });

  it("skips ask() when question is empty", async () => {
    const wrapper = await mountPanel();
    await flushPromises();
    await wrapper.find('input[placeholder*="自然语言"]').setValue("");
    await wrapper.find("form").trigger("submit");

    expect(mockAsk).not.toHaveBeenCalled();
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

    const wrapper = await mountPanel();
    await flushPromises();
    await wrapper.find('input[placeholder*="自然语言"]').setValue("测试问题");
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

    const wrapper = await mountPanel();
    await flushPromises();
    await wrapper.find('input[placeholder*="自然语言"]').setValue("测试问题");
    await wrapper.find("form").trigger("submit");
    await vi.waitFor(() => expect(wrapper.text()).toContain("查询失败"));
    expect(wrapper.text()).toContain("缺少必要权限");
    expect(wrapper.text()).toContain("company 不存在");
    expect(wrapper.text()).toContain("请先上传企业认证材料");
  });

  it("surfaces HTTP errors via in-panel error UI", async () => {
    mockAsk.mockRejectedValue({
      response: { data: { ok: false, errors: ["entity_type not found"], suggestion: "请尝试 bill" } },
    });

    const wrapper = await mountPanel();
    await flushPromises();
    await wrapper.find('input[placeholder*="自然语言"]').setValue("这企业欠费多少");
    await wrapper.find("form").trigger("submit");
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("查询失败");
      expect(wrapper.text()).toContain("entity_type not found");
      expect(wrapper.text()).toContain("请尝试 bill");
    });
  });

  it("surfaces generic network errors", async () => {
    mockAsk.mockRejectedValue(new Error("Network Error"));

    const wrapper = await mountPanel();
    await flushPromises();
    await wrapper.find('input[placeholder*="自然语言"]').setValue("这企业欠费多少");
    await wrapper.find("form").trigger("submit");
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("查询失败");
      expect(wrapper.text()).toContain("Network Error");
      expect(wrapper.text()).toContain("请检查网络连接或稍后重试");
    });
  });

  it("shows upload-CSV hint when catalog has no datasets (no entity_types)", async () => {
    // cat-fin returns [] -> empty hint visible
    mockListDatasets.mockReset().mockResolvedValue({ data: [] });

    const wrapper = await mountPanel();
    await flushPromises();
    expect(wrapper.find('[data-testid="entity-type-empty-hint"]').exists()).toBe(true);
    // BUG-015: 空数据集文案升级为"如何上传"——告诉用户去「数据集」tab上传 CSV。
    expect(wrapper.find('[data-testid="entity-type-empty-hint"]').text()).toContain("尚未上传数据集");
    expect(wrapper.find('[data-testid="entity-type-empty-hint"]').text()).toContain("上传 CSV");
  });

  it("shows assign-entity-type hint when datasets exist but entity_type all NULL", async () => {
    // Legacy datasets (pre-migration-019) have entity_type NULL. The panel
    // must NOT say "尚未上传数据集"; it should tell the user to assign
    // entity_type in the datasets tab.
    mockListDatasets.mockReset().mockResolvedValue({
      data: [
        { id: "ds-null-1", entity_type: null },
        { id: "ds-null-2", entity_type: null },
      ],
    });

    const wrapper = await mountPanel();
    await flushPromises();
    const hint = wrapper.find('[data-testid="entity-type-empty-hint"]');
    expect(hint.exists()).toBe(true);
    expect(hint.text()).not.toContain("尚未上传数据集");
    expect(hint.text()).toContain("未指定 entity_type");
    expect(hint.text()).toContain("2");
    // Select placeholder reflects "needs entity_type" not "needs upload".
    const select = wrapper.find('[data-testid="entity-type-select"]');
    const placeholderOption = select.find("option");
    expect(placeholderOption.text()).toContain("请先指定实体类型");
  });
});
