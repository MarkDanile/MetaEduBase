/**
 * REQ-052 + REQ-054 Task 8 + review fix: UploadDatasetDialog 行为锁。
 *
 * - REQ-054: 数据库 select（catalog store 加载）。
 * - entity_type 自由输入（datalist 提示已发现类型，不再校验白名单）。
 * - preSelectedCatalogId prop 锁定 catalog select。
 * - 表单合法性：catalog_id + entity_type + name + file 均必填，canUpload 联动。
 * - 上传时 FormData 必带 catalog_id + entity_type。
 * - review fix: warning prop 展示后端返回的新实体类型提示。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/services/catalog", () => ({
  listCatalogs: vi.fn(),
}));

import UploadDatasetDialog, {
  type UploadForm,
} from "./UploadDatasetDialog.vue";
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

function emptyForm(): UploadForm {
  return {
    name: "",
    description: "",
    tags: "",
    file: null,
    catalog_id: "",
    entity_type: "",
  };
}

async function mountDialog(props: {
  open?: boolean;
  form?: UploadForm;
  uploading?: boolean;
  preSelectedCatalogId?: string | null;
  warning?: string | null;
} = {}) {
  setActivePinia(createPinia());
  const catalogStore = useCatalogStore();
  catalogStore.catalogs = SAMPLE_CATALOGS;
  catalogStore.loading = false;

  const wrapper = mount(UploadDatasetDialog, {
    props: {
      open: props.open ?? true,
      form: props.form ?? emptyForm(),
      uploading: props.uploading ?? false,
      preSelectedCatalogId: props.preSelectedCatalogId ?? null,
      warning: props.warning ?? null,
    },
  });
  await flushPromises();
  return wrapper;
}

describe("UploadDatasetDialog.vue (REQ-052 + REQ-054 Task 8 + review fix)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders catalog select and entity_type input", async () => {
    const wrapper = await mountDialog();
    expect(wrapper.find('[data-testid="upload-catalog-select"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="upload-entity-type-input"]').exists()).toBe(true);
  });

  it("renders catalog options from catalog store", async () => {
    const wrapper = await mountDialog();
    const catalogSelect = wrapper.find('[data-testid="upload-catalog-select"]');
    const options = catalogSelect.findAll("option");
    const labels = options.map((o) => o.text());
    expect(labels.some((l) => l.includes("财务数据库"))).toBe(true);
    expect(labels.some((l) => l.includes("人力资源"))).toBe(true);
  });

  it("entity_type datalist shows discovered types as suggestions", async () => {
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin" },
    });
    const datalist = wrapper.find("#upload-entity-type-suggestions");
    expect(datalist.exists()).toBe(true);
    const values = datalist.findAll("option").map((o) => o.attributes("value"));
    expect(values).toContain("bill");
    expect(values).toContain("invoice");
    expect(values).not.toContain("employee");
  });

  it("entity_type input is free-text (not disabled) even with empty catalog types", async () => {
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin", entity_type: "custom_new_type" },
    });
    const input = wrapper.find('[data-testid="upload-entity-type-input"]');
    expect(input.exists()).toBe(true);
    expect(input.attributes("disabled")).toBeUndefined();
    expect((input.element as HTMLInputElement).value).toBe("custom_new_type");
  });

  it("switching catalog resets entity_type (parent emits new form)", async () => {
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin", entity_type: "bill" },
    });
    const catalogSelect = wrapper.find('[data-testid="upload-catalog-select"]');
    await catalogSelect.setValue("cat-hr");
    const updates = wrapper.emitted("update:form");
    expect(updates).toBeTruthy();
    const last = updates![updates!.length - 1][0] as UploadForm;
    expect(last.catalog_id).toBe("cat-hr");
    expect(last.entity_type).toBe("");
  });

  it("emits update:form when entity_type input changes", async () => {
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin" },
    });
    const input = wrapper.find('[data-testid="upload-entity-type-input"]');
    await input.setValue("new_type");
    const updates = wrapper.emitted("update:form");
    expect(updates).toBeTruthy();
    const last = updates![updates!.length - 1][0] as UploadForm;
    expect(last.entity_type).toBe("new_type");
  });

  it("preSelectedCatalogId prop disables catalog select", async () => {
    const wrapper = await mountDialog({
      open: true,
      preSelectedCatalogId: "cat-hr",
    });
    const select = wrapper.find('[data-testid="upload-catalog-select"]');
    expect(select.attributes("disabled")).toBeDefined();
  });

  it("upload button disabled when catalog_id missing", async () => {
    const wrapper = await mountDialog();
    const submit = wrapper.find('[data-testid="upload-submit"]');
    expect(submit.attributes("disabled")).toBeDefined();
  });

  it("upload button disabled when entity_type missing but catalog_id present", async () => {
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin" },
    });
    const submit = wrapper.find('[data-testid="upload-submit"]');
    expect(submit.attributes("disabled")).toBeDefined();
  });

  it("upload button enabled when all required fields present", async () => {
    const file = new File(["x"], "test.xlsx");
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin", entity_type: "bill", name: "账单", file },
    });
    const submit = wrapper.find('[data-testid="upload-submit"]');
    expect(submit.attributes("disabled")).toBeUndefined();
  });

  it("emits upload event when submit clicked", async () => {
    const file = new File(["x"], "test.xlsx");
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin", entity_type: "bill", name: "账单", file },
    });
    await wrapper.find('[data-testid="upload-submit"]').trigger("click");
    expect(wrapper.emitted("upload")).toBeTruthy();
    expect(wrapper.emitted("upload")!.length).toBe(1);
  });

  it("emits update:form when fields change (name, description, tags)", async () => {
    const wrapper = await mountDialog({
      form: { ...emptyForm(), catalog_id: "cat-fin", entity_type: "bill" },
    });
    const nameInput = wrapper.find('input[placeholder="输入数据集名称"]');
    await nameInput.setValue("新名字");
    expect(wrapper.emitted("update:form")).toBeTruthy();
    const last = wrapper.emitted("update:form")!.slice(-1)[0][0] as UploadForm;
    expect(last.name).toBe("新名字");
    expect(last.catalog_id).toBe("cat-fin");
    expect(last.entity_type).toBe("bill");
  });

  it("renders warning when warning prop is set", async () => {
    const wrapper = await mountDialog({
      warning: "发现新实体类型 ticket，请确认是否属于本主题",
    });
    const warning = wrapper.find('[data-testid="upload-warning"]');
    expect(warning.exists()).toBe(true);
    expect(warning.text()).toContain("发现新实体类型 ticket");
  });

  it("does not render warning when warning prop is null", async () => {
    const wrapper = await mountDialog({ warning: null });
    expect(wrapper.find('[data-testid="upload-warning"]').exists()).toBe(false);
  });
});
