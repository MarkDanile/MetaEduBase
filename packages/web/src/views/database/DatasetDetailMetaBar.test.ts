/**
 * REQ-054 bugfix: DatasetDetailMetaBar inline entity_type edit behavior lock.
 *
 * - Displays the selected dataset's entity_type (or "未指定" when NULL).
 * - Edit button toggles an input prefilled with the current entity_type.
 * - Save emits `update-entity-type` with the trimmed value and closes edit.
 * - Empty input on save is rejected (no emit).
 * - Cancel closes edit without emitting.
 * - Enter saves; Esc cancels.
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import DatasetDetailMetaBar from "./DatasetDetailMetaBar.vue";
import type { DatasetDTO } from "@/services/structured-data";

function makeDataset(overrides: Partial<DatasetDTO> = {}): DatasetDTO {
  return {
    id: "ds-1",
    tenant_id: "t-1",
    name: "账单数据集",
    description: null,
    column_names: ["id", "amount"],
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
    ...overrides,
  };
}

function mountBar(selected: DatasetDTO) {
  return mount(DatasetDetailMetaBar, { props: { selected } });
}

describe("DatasetDetailMetaBar.vue (REQ-054 bugfix: inline entity_type edit)", () => {
  it("displays the current entity_type", () => {
    const wrapper = mountBar(makeDataset({ entity_type: "bill" }));
    expect(wrapper.find('[data-testid="entity-type-display"]').text()).toBe("bill");
  });

  it("displays '未指定' when entity_type is NULL", () => {
    const wrapper = mountBar(makeDataset({ entity_type: null }));
    expect(wrapper.find('[data-testid="entity-type-display"]').text()).toContain("未指定");
  });

  it("edit button opens input prefilled with current entity_type", async () => {
    const wrapper = mountBar(makeDataset({ entity_type: "bill" }));
    await wrapper.find('[data-testid="edit-entity-type-btn"]').trigger("click");
    const input = wrapper.find('[data-testid="entity-type-input"]');
    expect(input.exists()).toBe(true);
    expect((input.element as HTMLInputElement).value).toBe("bill");
  });

  it("save emits update-entity-type with trimmed value and closes edit", async () => {
    const wrapper = mountBar(makeDataset({ entity_type: "bill" }));
    await wrapper.find('[data-testid="edit-entity-type-btn"]').trigger("click");
    await wrapper.find('[data-testid="entity-type-input"]').setValue("  invoice  ");
    await wrapper.find('[data-testid="save-entity-type-btn"]').trigger("click");
    const events = wrapper.emitted("update-entity-type");
    expect(events).toHaveLength(1);
    expect(events![0]).toEqual(["invoice"]);
    // Edit mode closed.
    expect(wrapper.find('[data-testid="entity-type-input"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="save-entity-type-btn"]').exists()).toBe(false);
  });

  it("save rejects empty input (no emit, stays in edit mode)", async () => {
    const wrapper = mountBar(makeDataset({ entity_type: "bill" }));
    await wrapper.find('[data-testid="edit-entity-type-btn"]').trigger("click");
    await wrapper.find('[data-testid="entity-type-input"]').setValue("   ");
    await wrapper.find('[data-testid="save-entity-type-btn"]').trigger("click");
    expect(wrapper.emitted("update-entity-type")).toBeUndefined();
    expect(wrapper.find('[data-testid="entity-type-input"]').exists()).toBe(true);
  });

  it("cancel closes edit without emitting", async () => {
    const wrapper = mountBar(makeDataset({ entity_type: "bill" }));
    await wrapper.find('[data-testid="edit-entity-type-btn"]').trigger("click");
    await wrapper.find('[data-testid="entity-type-input"]').setValue("invoice");
    await wrapper.find('[data-testid="cancel-entity-type-btn"]').trigger("click");
    expect(wrapper.emitted("update-entity-type")).toBeUndefined();
    expect(wrapper.find('[data-testid="entity-type-input"]').exists()).toBe(false);
  });

  it("edit from NULL entity_type starts with empty input", async () => {
    const wrapper = mountBar(makeDataset({ entity_type: null }));
    await wrapper.find('[data-testid="edit-entity-type-btn"]').trigger("click");
    const input = wrapper.find('[data-testid="entity-type-input"]');
    expect((input.element as HTMLInputElement).value).toBe("");
    await input.setValue("contract");
    await wrapper.find('[data-testid="save-entity-type-btn"]').trigger("click");
    expect(wrapper.emitted("update-entity-type")![0]).toEqual(["contract"]);
  });

  it("enter key saves; esc key cancels", async () => {
    const wrapper = mountBar(makeDataset({ entity_type: "bill" }));
    await wrapper.find('[data-testid="edit-entity-type-btn"]').trigger("click");
    await wrapper.find('[data-testid="entity-type-input"]').setValue("invoice");
    await wrapper.find('[data-testid="entity-type-input"]').trigger("keyup.enter");
    expect(wrapper.emitted("update-entity-type")![0]).toEqual(["invoice"]);

    // esc cancels a fresh edit.
    await wrapper.find('[data-testid="edit-entity-type-btn"]').trigger("click");
    await wrapper.find('[data-testid="entity-type-input"]').trigger("keyup.esc");
    expect(wrapper.find('[data-testid="entity-type-input"]').exists()).toBe(false);
    // Only the first save emitted; esc did not add another event.
    expect(wrapper.emitted("update-entity-type")).toHaveLength(1);
  });
});
