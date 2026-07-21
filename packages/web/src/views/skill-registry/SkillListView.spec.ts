/**
 * REQ-045 Task 4: SkillListView 行为锁（AC-10）。
 *
 * 覆盖：
 * 1. 渲染列表（mock listSkills 返回 3 条 -> 3 行，含同 code 多版本）
 * 2. 注册提交调用 createSkill（含 code/version 格式校验：非法不提交）
 * 3. 启停切换调用 enableSkill / disableSkill
 * 4. 版本展示（行内 version）+ 同 code 多版本筛选
 * 5. 越权角色（employee / teacher / student）管理按钮隐藏（只读列表）
 * 6. 删除确认调用 deleteSkill
 * 7. 审计分页查询调用 listExecutions（limit/offset）
 * 8. 试运行调用 runSkill 并展示结构化产物（report 分区 + steps 摘要）
 *
 * 说明：管理操作（注册 / 启停 / 删除 / 审计 / 试运行）按钮仅 admin /
 * data_admin / super_admin 可见；审计与试运行端点后端为 admin-only
 * （spec §4.5），故对应按钮同样按角色显隐，避免非管理员点击后 403。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises, DOMWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";

vi.mock("@/services/skillRegistry", () => ({
  listSkills: vi.fn(),
  createSkill: vi.fn(),
  enableSkill: vi.fn(),
  disableSkill: vi.fn(),
  deleteSkill: vi.fn(),
  listExecutions: vi.fn(),
  runSkill: vi.fn(),
}));

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

// ConfirmDialog 默认 Teleport 到 body，测试里改为内联渲染便于在 wrapper 内查找。
vi.mock("@/components/ConfirmDialog.vue", () => ({
  default: defineComponent({
    name: "ConfirmDialog",
    props: {
      open: { type: Boolean, default: false },
      title: { type: String, default: "" },
      message: { type: String, default: "" },
      danger: { type: Boolean, default: false },
      confirmText: { type: String, default: "" },
      cancelText: { type: String, default: "" },
    },
    emits: ["confirm", "cancel", "update:open"],
    setup(props, { emit }) {
      return () =>
        props.open
          ? h("div", { "data-testid": "confirm-dialog" }, [
              h("p", {}, String(props.message)),
              h(
                "button",
                { "data-testid": "confirm-confirm", onClick: () => emit("confirm") },
                "确认",
              ),
            ])
          : null;
    },
  }),
}));

import SkillListView from "./SkillListView.vue";
import {
  listSkills,
  createSkill,
  enableSkill,
  disableSkill,
  deleteSkill,
  listExecutions,
  runSkill,
} from "@/services/skillRegistry";

const SAMPLE_SKILLS = [
  {
    id: "skill-dd-1",
    tenant_id: "t-1",
    code: "enterprise_360_dd",
    version: "1.0.0",
    name: "企业 360 背调",
    description: "入驻/投决前核验",
    sop_template: "name: enterprise-360-dd\nsteps:\n  - id: s1\n    server: qcc\n    tool: t1\n",
    source_ref: "企查查官方 skill",
    allowed_roles: ["admin", "data_admin"],
    enabled: true,
    created_by: "u-1",
    created_at: "2026-07-01T00:00:00",
    updated_at: "2026-07-01T00:00:00",
  },
  {
    id: "skill-dd-2",
    tenant_id: "t-1",
    code: "enterprise_360_dd",
    version: "1.1.0",
    name: "企业 360 背调",
    description: "迭代版",
    sop_template: "name: enterprise-360-dd\nsteps:\n  - id: s1\n    server: qcc\n    tool: t1\n",
    source_ref: null,
    allowed_roles: ["admin"],
    enabled: false,
    created_by: "u-1",
    created_at: "2026-07-10T00:00:00",
    updated_at: "2026-07-10T00:00:00",
  },
  {
    id: "skill-onb",
    tenant_id: "t-1",
    code: "tenant_onboarding",
    version: "0.9.0",
    name: "租户入驻核验",
    description: null,
    sop_template: "name: tenant-onboarding\nsteps:\n  - id: s1\n    server: hr\n    tool: t1\n",
    source_ref: null,
    allowed_roles: ["super_admin"],
    enabled: true,
    created_by: "u-1",
    created_at: "2026-07-15T00:00:00",
    updated_at: "2026-07-15T00:00:00",
  },
];

let currentWrapper: ReturnType<typeof mount> | undefined;

async function mountView(role = "admin") {
  localStorage.setItem("metaedu_token", "test-token");
  localStorage.setItem("metaedu_role", role);
  setActivePinia(createPinia());
  const w = mount(SkillListView);
  currentWrapper = w;
  await flushPromises();
  return w;
}

// Teleport 到 body 的 modal 内容无法用 wrapper.find 直接查找，包一层 DOMWrapper。
function body(selector: string): DOMWrapper<Element> {
  const el = document.body.querySelector(selector);
  if (!el) throw new Error(`body: not found: ${selector}`);
  return new DOMWrapper(el);
}

describe("SkillListView.vue (REQ-045 Task 4 / AC-10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listSkills).mockResolvedValue(SAMPLE_SKILLS as never);
  });

  afterEach(() => {
    currentWrapper?.unmount();
    currentWrapper = undefined;
    localStorage.clear();
  });

  it("renders skill rows from listSkills (incl. same-code multi-version)", async () => {
    const wrapper = await mountView("admin");
    expect(wrapper.findAll('[data-testid="skill-row"]')).toHaveLength(3);
    expect(wrapper.text()).toContain("enterprise_360_dd");
    expect(wrapper.text()).toContain("tenant_onboarding");
    // 版本展示：1.0.0 / 1.1.0 / 0.9.0 都在
    expect(wrapper.findAll('[data-testid="skill-version"]')).toHaveLength(3);
    expect(wrapper.text()).toContain("1.0.0");
    expect(wrapper.text()).toContain("1.1.0");
    expect(wrapper.text()).toContain("0.9.0");
  });

  it("code filter narrows to same-code versions", async () => {
    const wrapper = await mountView("admin");
    // 初始 3 行
    expect(wrapper.findAll('[data-testid="skill-row"]')).toHaveLength(3);
    // 筛选 enterprise_360_dd -> 2 个版本
    await wrapper.find('[data-testid="code-filter"]').setValue("enterprise_360_dd");
    await flushPromises();
    expect(wrapper.findAll('[data-testid="skill-row"]')).toHaveLength(2);
    expect(wrapper.text()).toContain("1.0.0");
    expect(wrapper.text()).toContain("1.1.0");
    expect(wrapper.text()).not.toContain("0.9.0");
  });

  it("register submit calls createSkill with form payload", async () => {
    vi.mocked(listSkills).mockResolvedValue([] as never);
    vi.mocked(createSkill).mockResolvedValue(SAMPLE_SKILLS[0] as never);

    const wrapper = await mountView("admin");
    await wrapper.find('[data-testid="register-btn"]').trigger("click");
    await flushPromises();

    expect(body('[data-testid="create-modal"]').exists()).toBe(true);
    await body('[data-testid="input-code"]').setValue("enterprise_360_dd");
    await body('[data-testid="input-version"]').setValue("1.0.0");
    await body('[data-testid="input-name"]').setValue("企业 360 背调");
    await body('[data-testid="input-sop-template"]').setValue(
      "name: enterprise-360-dd\nsteps:\n  - id: s1\n    server: qcc\n    tool: t1\n",
    );
    await body('[data-testid="input-roles"]').setValue("admin,data_admin");
    await body('[data-testid="submit-create"]').trigger("click");
    await flushPromises();

    expect(createSkill).toHaveBeenCalledTimes(1);
    expect(createSkill).toHaveBeenCalledWith(
      expect.objectContaining({
        code: "enterprise_360_dd",
        version: "1.0.0",
        name: "企业 360 背调",
        sop_template: expect.stringContaining("name: enterprise-360-dd"),
        allowed_roles: ["admin", "data_admin"],
      }),
    );
  });

  it("register rejects invalid code / version format without calling API", async () => {
    vi.mocked(listSkills).mockResolvedValue([] as never);

    const wrapper = await mountView("admin");
    await wrapper.find('[data-testid="register-btn"]').trigger("click");
    await flushPromises();

    // 非法 code（含连字符 + 大写）
    await body('[data-testid="input-code"]').setValue("Invalid-Code");
    await body('[data-testid="input-version"]').setValue("1.0.0");
    await body('[data-testid="input-name"]').setValue("x");
    await body('[data-testid="input-sop-template"]').setValue("name: x\nsteps:\n  - id: s1\n    server: qcc\n    tool: t1\n");
    await body('[data-testid="submit-create"]').trigger("click");
    await flushPromises();
    expect(createSkill).not.toHaveBeenCalled();

    // 合法 code + 非法 version（非 x.y.z）
    await body('[data-testid="input-code"]').setValue("valid_code");
    await body('[data-testid="input-version"]').setValue("1.0");
    await body('[data-testid="submit-create"]').trigger("click");
    await flushPromises();
    expect(createSkill).not.toHaveBeenCalled();
  });

  it("toggling enabled calls enableSkill / disableSkill", async () => {
    vi.mocked(disableSkill).mockResolvedValue({ ...SAMPLE_SKILLS[0], enabled: false } as never);
    vi.mocked(enableSkill).mockResolvedValue({ ...SAMPLE_SKILLS[1], enabled: true } as never);

    const wrapper = await mountView("admin");
    // skill 0 (enterprise_360_dd v1.0.0) enabled -> click disables
    await wrapper.findAll('[data-testid="toggle-enabled"]')[0].trigger("click");
    await flushPromises();
    expect(disableSkill).toHaveBeenCalledWith("skill-dd-1");

    // skill 1 (enterprise_360_dd v1.1.0) disabled -> click enables
    await wrapper.findAll('[data-testid="toggle-enabled"]')[1].trigger("click");
    await flushPromises();
    expect(enableSkill).toHaveBeenCalledWith("skill-dd-2");
  });

  it("non-admin roles: register/toggle/delete/audit/run buttons hidden, list read-only", async () => {
    for (const role of ["employee", "teacher", "student"]) {
      const wrapper = await mountView(role);
      expect(wrapper.find('[data-testid="register-btn"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="toggle-enabled"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="delete-btn"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="audit-btn"]').exists()).toBe(false);
      expect(wrapper.find('[data-testid="run-btn"]').exists()).toBe(false);
      // 列表本身对非管理员可见（只读）
      expect(wrapper.findAll('[data-testid="skill-row"]')).toHaveLength(3);
      // 启用状态以只读 tag 呈现
      expect(wrapper.find(".ui-tag-green").exists()).toBe(true);
      currentWrapper?.unmount();
      currentWrapper = undefined;
    }
  });

  it("delete confirm calls deleteSkill", async () => {
    vi.mocked(deleteSkill).mockResolvedValue(undefined as never);

    const wrapper = await mountView("admin");
    await wrapper.find('[data-testid="delete-btn"]').trigger("click");
    await flushPromises();
    // ConfirmDialog 被内联 mock，confirm 按钮在 wrapper 内
    await wrapper.find('[data-testid="confirm-confirm"]').trigger("click");
    await flushPromises();

    expect(deleteSkill).toHaveBeenCalledTimes(1);
    expect(deleteSkill).toHaveBeenCalledWith("skill-dd-1");
  });

  it("audit modal paginates executions with limit/offset", async () => {
    // page 1: 10 items, total 11 -> hasNext true
    vi.mocked(listExecutions).mockResolvedValueOnce({
      items: Array.from({ length: 10 }, (_, i) => ({
        id: `ex-${i}`,
        skill_id: "skill-dd-1",
        skill_code: "enterprise_360_dd",
        skill_version: "1.0.0",
        caller_type: "http_api",
        caller_user_id: null,
        subject_digest: "d".repeat(64),
        steps_digest: "s".repeat(64),
        report_digest: "r".repeat(64),
        ok: true,
        error_code: null,
        error_message: null,
        duration_ms: 1200,
        created_at: "2026-07-01T00:00:00",
      })),
      total: 11,
      limit: 10,
      offset: 0,
    } as never);
    // page 2: 1 item, total 11 -> hasNext false
    vi.mocked(listExecutions).mockResolvedValueOnce({
      items: [
        {
          id: "ex-10",
          skill_id: "skill-dd-1",
          skill_code: "enterprise_360_dd",
          skill_version: "1.0.0",
          caller_type: "http_api",
          caller_user_id: null,
          subject_digest: "d".repeat(64),
          steps_digest: "s".repeat(64),
          report_digest: "r".repeat(64),
          ok: false,
          error_code: "tool_error",
          error_message: "step s1 调用失败",
          duration_ms: 30000,
          created_at: "2026-07-02T00:00:00",
        },
      ],
      total: 11,
      limit: 10,
      offset: 10,
    } as never);

    const wrapper = await mountView("admin");
    // open audit on first skill (skill-dd-1)
    await wrapper.find('[data-testid="audit-btn"]').trigger("click");
    await flushPromises();

    expect(listExecutions).toHaveBeenCalledWith("skill-dd-1", { limit: 10, offset: 0 });
    const modal = body('[data-testid="audit-modal"]');
    expect(modal.findAll(".audit-row")).toHaveLength(10);
    expect(body('[data-testid="audit-page-info"]').text()).toContain("1-10");
    expect(body('[data-testid="audit-page-info"]').text()).toContain("共 11");
    expect(body('[data-testid="audit-prev"]').attributes("disabled")).toBeDefined();
    expect(body('[data-testid="audit-next"]').attributes("disabled")).toBeUndefined();

    // next page -> offset 10
    await body('[data-testid="audit-next"]').trigger("click");
    await flushPromises();
    expect(listExecutions).toHaveBeenCalledWith("skill-dd-1", { limit: 10, offset: 10 });
    expect(body('[data-testid="audit-modal"]').findAll(".audit-row")).toHaveLength(1);
    expect(body('[data-testid="audit-page-info"]').text()).toContain("11-11");
    expect(body('[data-testid="audit-next"]').attributes("disabled")).toBeDefined();
  });

  it("trial run calls runSkill and renders structured report + steps", async () => {
    vi.mocked(runSkill).mockResolvedValue({
      report:
        "## 事实数据\ncompany: 示例企业\n## AI 分析\nrisk: low\n## 待人工确认项\n- 核对营业执照",
      execution_audit_id: "audit-uuid-1234",
      duration_ms: 5420,
      steps: [
        { id: "subject_verify", ok: true, digest: "a".repeat(64) },
        { id: "risk_scan", ok: true, digest: "b".repeat(64) },
      ],
    } as never);

    const wrapper = await mountView("admin");
    // open run on first skill (skill-dd-1, version 1.0.0)
    await wrapper.find('[data-testid="run-btn"]').trigger("click");
    await flushPromises();

    const modal = body('[data-testid="run-modal"]');
    expect(modal.exists()).toBe(true);
    // version 预填本行版本
    expect((modal.find('[data-testid="run-input-version"]').element as HTMLInputElement).value).toBe("1.0.0");
    // 填 subject
    await modal.find('[data-testid="run-input-subject"]').setValue('{"company_name":"示例企业"}');
    await modal.find('[data-testid="run-submit"]').trigger("click");
    await flushPromises();

    expect(runSkill).toHaveBeenCalledTimes(1);
    expect(runSkill).toHaveBeenCalledWith("skill-dd-1", {
      version: "1.0.0",
      subject: { company_name: "示例企业" },
    });

    // 产物展示
    const result = body('[data-testid="run-result"]');
    expect(result.exists()).toBe(true);
    expect(body('[data-testid="run-report"]').text()).toContain("事实数据");
    expect(body('[data-testid="run-report"]').text()).toContain("AI 分析");
    expect(body('[data-testid="run-report"]').text()).toContain("待人工确认项");
    // 三分区
    expect(body('[data-testid="run-report"]').findAll(".report-section")).toHaveLength(3);
    // steps 摘要
    expect(body('[data-testid="run-steps"]').findAll(".run-step")).toHaveLength(2);
    expect(body('[data-testid="run-steps"]').text()).toContain("subject_verify");
    expect(body('[data-testid="run-steps"]').text()).toContain("risk_scan");
    // 耗时
    expect(result.text()).toContain("5420");
  });

  it("trial run rejects empty subject object without calling API", async () => {
    const wrapper = await mountView("admin");
    await wrapper.find('[data-testid="run-btn"]').trigger("click");
    await flushPromises();

    const modal = body('[data-testid="run-modal"]');
    await modal.find('[data-testid="run-input-subject"]').setValue("{}");
    await modal.find('[data-testid="run-submit"]').trigger("click");
    await flushPromises();

    // Empty subject rejected client-side (mirrors backend min_length=1) - no API call.
    expect(runSkill).not.toHaveBeenCalled();
  });
});
