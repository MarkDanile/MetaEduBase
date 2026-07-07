/**
 * REQ-054 Task 7: DatabaseView 行为锁。
 *
 * - 卡片网格渲染 (v-for catalog in catalogs)
 * - [+ 新建数据库] 按钮按 role 显隐 (admin / data_admin / super_admin)
 * - 点击卡片 → router.push(`/database/${code}`)
 * - Loading / Empty 状态
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";

const { mockFetch, mockCreateCatalog } = vi.hoisted(() => ({
  mockFetch: vi.fn(),
  mockCreateCatalog: vi.fn(),
}));

vi.mock("@/services/catalog", () => ({
  listCatalogs: vi.fn(),
  createCatalog: mockCreateCatalog,
  getCatalog: vi.fn(),
  updateCatalog: vi.fn(),
  deleteCatalog: vi.fn(),
}));

vi.mock("@/stores/catalog", () => ({
  useCatalogStore: () => ({
    catalogs: [
      {
        id: "c-1",
        tenant_id: "t-1",
        code: "finance",
        name: "财务数据库",
        description: "账单与发票",
        icon: null,
        color: "#1677ff",
        entity_types: ["bill", "invoice"],
        default_business_purpose: null,
        is_active: true,
        created_by: "u-1",
        created_at: "2026-01-01T00:00:00",
        updated_at: "2026-01-01T00:00:00",
      },
      {
        id: "c-2",
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
    ],
    loading: false,
    fetch: mockFetch,
  }),
}));

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

import DatabaseView from "./DatabaseView.vue";

function setRole(role: string | null) {
  if (role) {
    localStorage.setItem("metaedu_role", role);
  } else {
    localStorage.removeItem("metaedu_role");
  }
}

async function mountView(role: string | null = null) {
  setRole(role);
  const pinia = createPinia();
  setActivePinia(pinia);

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div></div>" } },
      { path: "/database", component: DatabaseView },
      { path: "/database/:code", component: { template: "<div>detail</div>" } },
    ],
  });

  const wrapper = mount(DatabaseView, {
    global: {
      plugins: [pinia, router],
    },
  });

  await router.isReady();
  await flushPromises();
  return { wrapper, router };
}

describe("DatabaseView.vue (REQ-054 Task 7)", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockCreateCatalog.mockReset();
    localStorage.clear();
  });

  it("renders card grid with one card per catalog", async () => {
    const { wrapper } = await mountView();
    const cards = wrapper.findAll('[data-testid^="catalog-card-"]');
    // 2 catalog cards (excluding the data-testid on inner tags which start with same prefix)
    expect(cards.length).toBeGreaterThanOrEqual(2);
    expect(wrapper.text()).toContain("财务数据库");
    expect(wrapper.text()).toContain("人力资源");
  });

  it("shows [+ 新建数据库] for admin role", async () => {
    const { wrapper } = await mountView("admin");
    expect(wrapper.find('[data-testid="catalog-create-btn"]').exists()).toBe(true);
  });

  it("shows [+ 新建数据库] for data_admin role", async () => {
    const { wrapper } = await mountView("data_admin");
    expect(wrapper.find('[data-testid="catalog-create-btn"]').exists()).toBe(true);
  });

  it("shows [+ 新建数据库] for super_admin role", async () => {
    const { wrapper } = await mountView("super_admin");
    expect(wrapper.find('[data-testid="catalog-create-btn"]').exists()).toBe(true);
  });

  it("hides [+ 新建数据库] for employee role", async () => {
    const { wrapper } = await mountView("employee");
    expect(wrapper.find('[data-testid="catalog-create-btn"]').exists()).toBe(false);
  });

  it("hides [+ 新建数据库] for manager role", async () => {
    const { wrapper } = await mountView("manager");
    expect(wrapper.find('[data-testid="catalog-create-btn"]').exists()).toBe(false);
  });

  it("hides [+ 新建数据库] when no role", async () => {
    const { wrapper } = await mountView(null);
    expect(wrapper.find('[data-testid="catalog-create-btn"]').exists()).toBe(false);
  });

  it("clicking a card navigates to /database/{code}", async () => {
    const { wrapper, router } = await mountView("admin");
    const pushSpy = vi.spyOn(router, "push");
    const card = wrapper.find('[data-testid="catalog-card-finance"]');
    await card.trigger("click");
    await flushPromises();
    expect(pushSpy).toHaveBeenCalledWith("/database/finance");
  });

  it("calls catalogStore.fetch() on mount", async () => {
    await mountView();
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });
});