/**
 * REQ-054 Task 8: CatalogDetailPage 行为锁。
 *
 * - 4 tab 渲染（数据集 / 语义层 / 知识图谱 / 问数）。
 * - 默认显示 数据集 tab，切换 tab 后对应 panel v-show。
 * - 按 URL param :catalogCode 从 store 解析 catalog。
 * - 嵌入 QueryPanel 并传入 preSelectedCatalogId 锁定该库。
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

vi.mock("@/services/structured-data", () => ({
  structuredDataApi: {
    listDatasets: vi.fn().mockResolvedValue({ data: [] }),
    uploadDataset: vi.fn(),
    getKnowledgeGraph: vi.fn().mockResolvedValue({ data: { nodes: [], edges: [] } }),
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
    render() {
      return h("div", { "data-testid": "stub-list" }, "list");
    },
  }),
}));

vi.mock("@/views/database/DatasetDetailMetaBar.vue", () => ({
  default: defineComponent({
    name: "StubMeta",
    render() {
      return h("div", { "data-testid": "stub-meta" }, "meta");
    },
  }),
}));

vi.mock("@/views/database/DatasetTabsPanel.vue", () => ({
  default: defineComponent({
    name: "StubTabs",
    render() {
      return h("div", { "data-testid": "stub-tabs" }, "tabs");
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
    render() {
      return h("div", { "data-testid": "stub-upload" }, "upload");
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

describe("CatalogDetailPage.vue (REQ-054 Task 8)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it("switches to semantic tab and shows entity_types", async () => {
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-semantic"]').trigger("click");
    await flushPromises();
    expect(wrapper.find('[data-testid="semantic-row-bill"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="semantic-row-contract"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="semantic-row-ticket"]').exists()).toBe(true);
  });

  it("switches to kg tab and shows KG count badge", async () => {
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-kg"]').trigger("click");
    await flushPromises();
    const count = wrapper.find('[data-testid="kg-node-count"]');
    expect(count.exists()).toBe(true);
    expect(count.text()).toContain("0 节点");
  });

  it("switches to ask tab and embeds QueryPanel with preSelectedCatalogId", async () => {
    const { wrapper } = await mountDetail();
    await wrapper.find('[data-testid="tab-ask"]').trigger("click");
    await flushPromises();
    const queryStub = wrapper.find('[data-testid="stub-query"]');
    expect(queryStub.exists()).toBe(true);
    expect(queryStub.attributes("data-pre")).toBe("cat-edu");
  });

  it("renders upload-dataset button inside datasets tab", async () => {
    const { wrapper } = await mountDetail();
    const btn = wrapper.find('[data-testid="upload-dataset-btn"]');
    expect(btn.exists()).toBe(true);
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
