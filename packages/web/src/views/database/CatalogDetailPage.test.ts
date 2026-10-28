/**
 * REQ-054 Task 8 + review fix: CatalogDetailPage 行为锁。
 *
 * - 4 tab 渲染（数据集 / 语义层 / 知识图谱 / 问数）。
 * - 默认显示 数据集 tab，切换 tab 后对应 panel v-show。
 * - 按 URL param :catalogCode 从 store 解析 catalog。
 * - 嵌入 QueryPanel 并传入 preSelectedCatalogId 锁定该库。
 *
 * review fix:
 * - 上传按钮移到 PageHeader #extra（固定右上角）。
 * - 语义层从 datasets 聚合 entity_type（不再读 catalog.entity_types 占位）。
 * - KG tab 嵌入 KgOverviewPanel（mock 为 stub）。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { defineComponent, h } from "vue";

vi.mock("@/services/catalog", () => ({
  listCatalogs: vi.fn(),
  createCatalog: vi.fn(),
  getCatalog: vi.fn(),
  updateCatalog: vi.fn(),
  deleteCatalog: vi.fn(),
}));

const {
  mockListDatasets,
  mockListRows,
  mockGetKnowledgeGraph,
  mockRebuildKg,
  mockReinitializeDataset,
  mockUpdateDataset,
} = vi.hoisted(() => ({
  mockListDatasets: vi.fn(),
  mockListRows: vi.fn(),
  mockGetKnowledgeGraph: vi.fn(),
  mockRebuildKg: vi.fn(),
  mockReinitializeDataset: vi.fn(),
  mockUpdateDataset: vi.fn(),
}));

vi.mock("@/services/structured-data", () => ({
  structuredDataApi: {
    listDatasets: mockListDatasets,
    listRows: mockListRows,
    reinitializeDataset: mockReinitializeDataset,
    uploadDataset: vi.fn(),
    updateDataset: mockUpdateDataset,
    getKnowledgeGraph: mockGetKnowledgeGraph,
    rebuildKnowledgeGraph: mockRebuildKg,
  },
}));

vi.mock("@/services/knowledge", () => ({
  knowledgeApi: {
    listNodes: vi.fn().mockResolvedValue({ data: [] }),
    listEdges: vi.fn().mockResolvedValue({ data: [] }),
  },
}));

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock("@/views/database/DatasetListPanel.vue", () => ({
  default: defineComponent({
    name: "StubList",
    emits: ["select"],
    render() {
      return h("div", { "data-testid": "stub-list" }, "list");
    },
  }),
}));

vi.mock("@/views/database/DatasetDetailMetaBar.vue", () => ({
  default: defineComponent({
    name: "StubMeta",
    emits: ["reinitialize", "delete", "update-entity-type"],
    render() {
      return h("div", { "data-testid": "stub-meta" }, "meta");
    },
  }),
}));

vi.mock("@/views/database/DatasetTabsPanel.vue", () => ({
  default: defineComponent({
    name: "StubTabs",
    props: {
      page: { type: Number, default: 0 },
      hasNextPage: { type: Boolean, default: false },
      canGoPrev: { type: Boolean, default: false },
      rows: { type: Array, default: () => [] },
    },
    emits: ["change-page"],
    render() {
      return h(
        "div",
        {
          "data-testid": "stub-tabs",
          "data-page": String(this.page ?? 0),
          "data-has-next": String(this.hasNextPage ?? false),
          "data-can-go-prev": String(this.canGoPrev ?? false),
          "data-row-count": String(this.rows?.length ?? 0),
        },
        "tabs",
      );
    },
  }),
}));

vi.mock("@/views/database/KgOverviewPanel.vue", () => ({
  default: defineComponent({
    name: "StubKgOverview",
    props: ["nodes", "edges", "loading", "rebuilding"],
    emits: ["rebuild", "node-click"],
    render() {
      return h(
        "div",
        {
          "data-testid": "stub-kg-overview",
          "data-node-count": String(this.nodes?.length ?? 0),
        },
        "kg-overview",
      );
    },
  }),
}));

vi.mock("@/views/database/QueryPanel.vue", () => ({
  default: defineComponent({
    name: "StubQuery",
    props: ["preSelectedCatalogId"],
    render() {
      return h(
        "div",
        { "data-testid": "stub-query", "data-pre": String(this.preSelectedCatalogId ?? "") },
        "Query",
      );
    },
  }),
}));

vi.mock("@/views/database/UploadDatasetDialog.vue", () => ({
  default: defineComponent({
    name: "StubUpload",
    props: ["open", "form", "uploading", "preSelectedCatalogId", "warning"],
    render() {
      return h(
        "div",
        {
          "data-testid": "stub-upload",
          "data-warning": String(this.warning ?? ""),
        },
        "upload",
      );
    },
  }),
}));

import CatalogDetailPage from "./CatalogDetailPage.vue";
import { useCatalogStore } from "@/stores/catalog";

const SAMPLE_CATALOG = {
  id: "cat-edu",
  tenant_id: "t-1",
  code: "education",
  name: "中高职教育数据库",
  description: "教育主题域",
  icon: null,
  color: "#1677ff",
  entity_types: ["bill", "contract", "ticket"],
  default_business_purpose: null,
  is_active: true,
  created_by: "u-1",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

// Datasets with entity_type for semantic tab aggregation.
const SAMPLE_DATASETS = [
  {
    id: "ds-bill",
    tenant_id: "t-1",
    name: "账单数据集",
    description: null,
    column_names: ["id", "amount", "due_date"],
    column_types: null,
    row_count: 10,
    source_file: null,
    tags: [],
    status: "ready",
    kg_status: "ready",
    sort_order: 0,
    entity_type: "bill",
    created_by: "u-1",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
  },
  {
    id: "ds-contract",
    tenant_id: "t-1",
    name: "合同数据集",
    description: null,
    column_names: ["id", "party", "signed_at"],
    column_types: null,
    row_count: 5,
    source_file: null,
    tags: [],
    status: "ready",
    kg_status: "ready",
    sort_order: 1,
    entity_type: "contract",
    created_by: "u-1",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
  },
  {
    id: "ds-ticket",
    tenant_id: "t-1",
    name: "工单数据集",
    description: null,
    column_names: ["id", "status"],
    column_types: null,
    row_count: 8,
    source_file: null,
    tags: [],
    status: "ready",
    kg_status: "ready",
    sort_order: 2,
    entity_type: "ticket",
    created_by: "u-1",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
  },
];

async function mountDetail(catalogs: unknown = [SAMPLE_CATALOG]) {
  setActivePinia(createPinia());
  const catalogStore = useCatalogStore();
  catalogStore.catalogs = catalogs as ReturnType<typeof useCatalogStore>["catalogs"];
  catalogStore.loading = false;

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        staleTime: 0,
      },
    },
  });

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div></div>" } },
      { path: "/database", component: { template: "<div></div>" } },
      {
        path: "/database/:catalogCode",
        name: "catalog-detail",
        component: CatalogDetailPage,
      },
    ],
  });
  await router.push("/database/education");
  await router.isReady();

  const wrapper = mount(CatalogDetailPage, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient }]] },
  });
  await flushPromises();
  return { wrapper, router, catalogStore };
}

describe("CatalogDetailPage.vue (REQ-054 Task 8 + review fix)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListDatasets.mockReset().mockResolvedValue({ data: SAMPLE_DATASETS });
    mockListRows.mockReset().mockResolvedValue({ data: [] });
    mockGetKnowledgeGraph.mockReset().mockResolvedValue({ data: { nodes: [], edges: [] } });
    mockRebuildKg.mockReset().mockResolvedValue({ data: { status: "ok", dataset_count: 3 } });
    mockUpdateDataset.mockReset().mockResolvedValue({ data: SAMPLE_DATASETS[0] });
  });

  it("renders 4 tabs (数据集 / 语义层 / 知识图谱 / 问数)", async () => {
    const { wrapper } = await mountDetail();
    const tabButtons = wrapper.findAll('[data-testid^="tab-"]');
    const keys = tabButtons.map((b) => String(b.attributes("data-testid")));
    expect(keys).toContain("tab-datasets");
    expect(keys).toContain("tab-semantic");
    expect(keys).toContain("tab-kg");
    expect(keys).toContain("tab-ask");
  });

  it("defaults to datasets tab on mount", async () => {
    const { wrapper } = await mountDetail();
    const datasetsPanel = wrapper.find('[data-testid="tab-panel-datasets"]');
    const semanticPanel = wrapper.find('[data-testid="tab-panel-semantic"]');
    expect(datasetsPanel.exists()).toBe(true);
    // Datasets panel should be visible by default (no display:none)
    expect(semanticPanel.attributes("style") || "").toMatch(/display:\s*none|visibility:\s*hidden/);
  });

  it("switches to semantic tab and shows entity_types aggregated from datasets", async () => {
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-semantic"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-testid="semantic-row-bill"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="semantic-row-contract"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="semantic-row-ticket"]').exists()).toBe(true);
    // 列映射可见
    expect(wrapper.find('[data-testid="semantic-columns-bill"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="semantic-columns-bill"]').text()).toContain("amount");
  });

  it("semantic tab shows empty state when catalog has no datasets", async () => {
    mockListDatasets.mockResolvedValue({ data: [] });
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-semantic"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-testid="semantic-empty"]').exists()).toBe(true);
  });

  it("semantic tab shows assign-entity-type hint when datasets exist but entity_type all NULL", async () => {
    // Legacy datasets (pre-migration-019) have entity_type NULL. The semantic
    // tab must NOT say "尚未配置语义层"; it should tell the user to assign
    // entity_type in the datasets tab.
    mockListDatasets.mockResolvedValue({
      data: SAMPLE_DATASETS.map((d) => ({ ...d, entity_type: null })),
    });
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-semantic"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-testid="semantic-empty"]').exists()).toBe(false);
    const hint = wrapper.find('[data-testid="semantic-no-entity-type"]');
    expect(hint.exists()).toBe(true);
    expect(hint.text()).toContain("未指定 entity_type");
    expect(hint.text()).toContain(String(SAMPLE_DATASETS.length));
  });

  it("switches to kg tab and embeds KgOverviewPanel", async () => {
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-kg"]').trigger("click");
    await flushPromises();
    const kgOverview = wrapper.find('[data-testid="stub-kg-overview"]');
    expect(kgOverview.exists()).toBe(true);
  });

  it("lazy-mounts KgOverviewPanel only after KG tab is first opened (avoid 0-width graph)", async () => {
    const { wrapper } = await mountDetail();
    // Before opening KG tab, the panel is not mounted (section is v-show
    // hidden, so a mounted G6 graph would read clientWidth=0).
    expect(wrapper.find('[data-testid="stub-kg-overview"]').exists()).toBe(false);
    // KG section reserves vertical render space.
    const kgSection = wrapper.find('[data-testid="tab-panel-kg"]');
    expect(kgSection.classes()).toContain("min-h-[600px]");
    // After opening KG tab, the panel mounts.
    await wrapper.find('[data-testid="tab-kg"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-testid="stub-kg-overview"]').exists()).toBe(true);
  });

  it("switches to ask tab and embeds QueryPanel with preSelectedCatalogId", async () => {
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-ask"]').trigger("click");
    await flushPromises();
    const queryStub = wrapper.find('[data-testid="stub-query"]');
    expect(queryStub.exists()).toBe(true);
    expect(queryStub.attributes("data-pre")).toBe("cat-edu");
  });

  it("renders upload-dataset button in PageHeader (fixed top-right)", async () => {
    const { wrapper } = await mountDetail();
    const btn = wrapper.find('[data-testid="upload-dataset-btn"]');
    expect(btn.exists()).toBe(true);
    // Button should be outside the scrollable tab panels (in PageHeader extra).
    // Verify it is NOT inside the datasets tab panel section.
    const datasetsPanel = wrapper.find('[data-testid="tab-panel-datasets"]');
    expect(datasetsPanel.find('[data-testid="upload-dataset-btn"]').exists()).toBe(false);
  });

  it("shows not-found hint when code does not match any catalog", async () => {
    const { wrapper, router } = await mountDetail();
    await router.push("/database/unknown_code");
    await flushPromises();
    const notFound = wrapper.find('[data-testid="catalog-not-found"]');
    expect(notFound.exists()).toBe(true);
    expect(notFound.text()).toContain("unknown_code");
  });
});

/**
 * REQ-064 S4 数据预览分页（D-P1=3a 数据预览 + D-P2=B `limit+1` 探测）。
 *
 * - 请求行数 = 页大小 20 + 1 = 21（探测是否存在下一页），不越界端点上限 200。
 * - 取到第 21 行即认为有下一页；只展示前 20 行。
 * - 翻页后 offset = 页码 * 20；首页不可再向前；无下一页时不可再向后。
 * - 切换数据集（条件变化）重置页码。
 * - 不使用 `row_count` 作为分页总数，也不向面板传总数。
 */
describe("CatalogDetailPage.vue (REQ-064 S4 数据预览分页 D-P1=3a + D-P2=B)", () => {
  const ROWS_PAGE_SIZE = 20;
  const ROWS_PROBE_SIZE = 21;

  function makeRows(count: number, startIndex = 0) {
    return Array.from({ length: count }, (_, i) => ({
      id: `row-${startIndex + i}`,
      dataset_id: "ds-bill",
      row_index: startIndex + i,
      data: { id: startIndex + i },
      created_at: "2026-01-01T00:00:00",
    }));
  }

  async function selectFirstDataset(wrapper: Awaited<ReturnType<typeof mountDetail>>["wrapper"]) {
    wrapper.findComponent({ name: "StubList" }).vm.$emit("select", SAMPLE_DATASETS[0]);
    await flushPromises();
  }

  beforeEach(() => {
    vi.clearAllMocks();
    mockListDatasets.mockReset().mockResolvedValue({ data: SAMPLE_DATASETS });
    mockListRows.mockReset().mockResolvedValue({ data: [] });
    mockGetKnowledgeGraph.mockReset().mockResolvedValue({ data: { nodes: [], edges: [] } });
  });

  it("requests page size + 1 rows to probe the next page", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);

    expect(mockListRows).toHaveBeenCalled();
    const [datasetId, params] = mockListRows.mock.calls[0];
    expect(datasetId).toBe(SAMPLE_DATASETS[0].id);
    expect(params).toEqual({ offset: 0, limit: ROWS_PROBE_SIZE });
    // 探测上限不得越过端点 limit 上限 200
    expect(params.limit).toBeLessThanOrEqual(200);
  });

  it("treats the 21st row as the existence of a next page", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);

    const tabs = wrapper.find('[data-testid="stub-tabs"]');
    expect(tabs.attributes("data-has-next")).toBe("true");
    // 只展示当前页 20 行，第 21 行仅用于探测
    expect(tabs.attributes("data-row-count")).toBe(String(ROWS_PAGE_SIZE));
  });

  it("reports no next page when the probe returns fewer rows than the page size", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PAGE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);

    const tabs = wrapper.find('[data-testid="stub-tabs"]');
    expect(tabs.attributes("data-has-next")).toBe("false");
    expect(tabs.attributes("data-row-count")).toBe(String(ROWS_PAGE_SIZE));
  });

  it("requests the next page with offset = page * page size", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);
    mockListRows.mockClear();

    wrapper.findComponent({ name: "StubTabs" }).vm.$emit("change-page", 1);
    await flushPromises();

    const [, params] = mockListRows.mock.calls[0];
    expect(params).toEqual({ offset: ROWS_PAGE_SIZE, limit: ROWS_PROBE_SIZE });
    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("1");
    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-can-go-prev")).toBe("true");
  });

  it("does not go back from the first page", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);
    mockListRows.mockClear();

    wrapper.findComponent({ name: "StubTabs" }).vm.$emit("change-page", -1);
    await flushPromises();

    expect(mockListRows).not.toHaveBeenCalled();
    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("0");
  });

  it("does not go forward when there is no next page", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(5) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);
    mockListRows.mockClear();

    wrapper.findComponent({ name: "StubTabs" }).vm.$emit("change-page", 1);
    await flushPromises();

    expect(mockListRows).not.toHaveBeenCalled();
    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("0");
  });

  it("resets the page when the selected dataset changes", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);

    wrapper.findComponent({ name: "StubTabs" }).vm.$emit("change-page", 1);
    await flushPromises();
    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("1");

    // 切换到另一个数据集 → 条件变化，页码重置为 0
    mockListRows.mockClear();
    wrapper.findComponent({ name: "StubList" }).vm.$emit("select", SAMPLE_DATASETS[1]);
    await flushPromises();

    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("0");
    const [, params] = mockListRows.mock.calls[0];
    expect(params).toEqual({ offset: 0, limit: ROWS_PROBE_SIZE });
  });

  it("does not pass any total to the panel (row_count is not the pagination total)", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);

    const tabs = wrapper.findComponent({ name: "StubTabs" });
    const props = tabs.props() as Record<string, unknown>;
    // 只传页码与"是否有下一页"，不传总数
    expect(props.page).toBe(0);
    expect(props.hasNextPage).toBe(true);
    expect(props.canGoPrev).toBe(false);
    // 未声明的 prop 会作为 fallthrough attr 渲染到根元素上，
    // 因此断言渲染产物（而不是 props）才能真正锁死
    // "父层没有再传 total-rows / page-size" 这一硬边界。
    expect(tabs.attributes("total-rows")).toBeUndefined();
    expect(tabs.attributes("page-size")).toBeUndefined();
  });
});

/**
 * 第二轮独立复审 findings 的行为锁：
 * - 翻页后空页（末页最后一条被删 / 重新初始化后行数变少）自动回退。
 * - 重新初始化后 rows 查询失效且回到第一页。
 * - 非 onSelectDataset 路径切换数据集时，首个请求的 offset 必须为 0
 *   （依赖 flush:"sync" 的兜底 watch，早于 Vue Query 内部的 pre-flush watcher）。
 */
describe("CatalogDetailPage.vue (S4 分页边界：空页回退 / 重初始化 / 兜底 watch)", () => {
  const ROWS_PAGE_SIZE = 20;
  /** 探测请求 21 行 → 取到第 21 行即存在下一页。 */
  const ROWS_PROBE_SIZE = ROWS_PAGE_SIZE + 1;

  function makeRows(count: number, startIndex = 0) {
    return Array.from({ length: count }, (_, i) => ({
      id: `row-${startIndex + i}`,
      dataset_id: "ds-bill",
      row_index: startIndex + i,
      data: { id: startIndex + i },
      created_at: "2026-01-01T00:00:00",
    }));
  }

  async function selectFirstDataset(wrapper: Awaited<ReturnType<typeof mountDetail>>["wrapper"]) {
    wrapper.findComponent({ name: "StubList" }).vm.$emit("select", SAMPLE_DATASETS[0]);
    await flushPromises();
  }

  beforeEach(() => {
    vi.clearAllMocks();
    mockListDatasets.mockReset().mockResolvedValue({ data: SAMPLE_DATASETS });
    mockListRows.mockReset().mockResolvedValue({ data: [] });
    mockGetKnowledgeGraph.mockReset().mockResolvedValue({ data: { nodes: [], edges: [] } });
    mockReinitializeDataset.mockReset().mockResolvedValue({ data: SAMPLE_DATASETS[0] });
  });

  it("翻页后空页自动回退到上一页", async () => {
    // 第 1 页返回 21 行（探测到第 21 行 → 有下一页），第 2 页起返回 0 行（模拟末页最后一条被删）
    mockListRows.mockImplementation((_id: string, params: { offset: number }) =>
      Promise.resolve({
        data: params.offset === 0 ? makeRows(ROWS_PROBE_SIZE) : [],
      }),
    );
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);
    mockListRows.mockClear();

    wrapper.findComponent({ name: "StubTabs" }).vm.$emit("change-page", 1);
    await flushPromises();
    await flushPromises();

    // 空页被识别并回退到第一页
    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("0");
    const offsets = mockListRows.mock.calls.map((c) => (c[1] as { offset: number }).offset);
    expect(offsets).toContain(0);
  });

  it("重新初始化后 rows 查询失效且回到第一页", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);

    wrapper.findComponent({ name: "StubTabs" }).vm.$emit("change-page", 1);
    await flushPromises();
    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("1");

    mockListRows.mockClear();
    wrapper.findComponent({ name: "StubMeta" }).vm.$emit("reinitialize");
    await flushPromises();
    await flushPromises();

    expect(wrapper.find('[data-testid="stub-tabs"]').attributes("data-page")).toBe("0");
    // rows 查询被 invalidate（offset 0 重新请求）
    const offsets = mockListRows.mock.calls.map((c) => (c[1] as { offset: number }).offset);
    expect(offsets).toContain(0);
  });

  it("非 onSelectDataset 路径切换数据集时首个请求 offset 为 0", async () => {
    mockListRows.mockResolvedValue({ data: makeRows(ROWS_PROBE_SIZE) });
    const { wrapper } = await mountDetail();
    await selectFirstDataset(wrapper);

    wrapper.findComponent({ name: "StubTabs" }).vm.$emit("change-page", 1);
    await flushPromises();
    mockListRows.mockClear();

    // 直接改写组件内部状态（模拟 onSelectDataset 之外的路径）
    (wrapper.vm as unknown as { selectedDatasetId: string | null }).selectedDatasetId =
      SAMPLE_DATASETS[1].id;
    await flushPromises();
    await flushPromises();

    const firstCall = mockListRows.mock.calls[0];
    expect(firstCall).toBeDefined();
    expect((firstCall[1] as { offset: number }).offset).toBe(0);
  });
});
