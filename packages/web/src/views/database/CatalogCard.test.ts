/**
 * REQ-054 Task 7: CatalogCard 组件行为锁。
 *
 * - 渲染 icon / name / code / description / entity_types 标签
 * - 点击 emit('click', catalog)
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import CatalogCard from "./CatalogCard.vue";
import type { CatalogDTO } from "@/services/catalog";

const sampleCatalog: CatalogDTO = {
  id: "c-1",
  tenant_id: "t-1",
  code: "finance",
  name: "财务数据库",
  description: "包含账单与发票",
  icon: null,
  color: "#1677ff",
  entity_types: ["bill", "invoice"],
  default_business_purpose: null,
  is_active: true,
  created_by: "u-1",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
};

describe("CatalogCard.vue (REQ-054 Task 7)", () => {
  it("renders name + code + description", () => {
    const wrapper = mount(CatalogCard, { props: { catalog: sampleCatalog } });
    expect(wrapper.text()).toContain("财务数据库");
    expect(wrapper.text()).toContain("finance");
    expect(wrapper.text()).toContain("包含账单与发票");
  });

  it("renders one tag per entity_type", () => {
    const wrapper = mount(CatalogCard, { props: { catalog: sampleCatalog } });
    expect(wrapper.find('[data-testid="catalog-card-finance-tag-bill"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="catalog-card-finance-tag-invoice"]').exists()).toBe(true);
  });

  it("omits description block when description is null", () => {
    const wrapper = mount(CatalogCard, {
      props: {
        catalog: { ...sampleCatalog, description: null },
      },
    });
    expect(wrapper.text()).not.toContain("包含账单与发票");
  });

  it("click emits click with catalog payload", async () => {
    const wrapper = mount(CatalogCard, { props: { catalog: sampleCatalog } });
    await wrapper.trigger("click");

    const emitted = wrapper.emitted("click");
    expect(emitted).toBeTruthy();
    expect(emitted![0][0]).toEqual(sampleCatalog);
  });

  it("renders button with type=button (BUG-006 style guard)", () => {
    const wrapper = mount(CatalogCard, { props: { catalog: sampleCatalog } });
    const btn = wrapper.find("button");
    expect(btn.attributes("type")).toBe("button");
  });
});