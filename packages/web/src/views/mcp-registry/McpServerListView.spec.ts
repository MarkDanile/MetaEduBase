/**
 * REQ-044 Task 4: McpServerListView 行为锁（AC-10）。
 *
 * 覆盖：
 * 1. 渲染列表（mock listMcpServers 返回 2 条 -> 2 行）
 * 2. 注册提交调用 createMcpServer（填表单 -> 提交 -> 断言 createMcpServer 被调）
 * 3. 启停切换调用 enableMcpServer / disableMcpServer
 * 4. 越权角色（teacher）注册 / 启停 / 删除 / 审计按钮不渲染（只读列表）
 * 5. 删除确认调用 deleteMcpServer
 *
 * 说明：管理操作（注册 / 启停 / 删除 / 审计）按钮仅 admin / data_admin /
 * super_admin 可见；审计查询端点后端为 admin-only（spec §4.5 第 8 行），
 * 故审计按钮同样按角色显隐，避免非管理员点击后 403。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises, DOMWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";

vi.mock("@/services/mcpRegistry", () => ({
  listMcpServers: vi.fn(),
  createMcpServer: vi.fn(),
  enableMcpServer: vi.fn(),
  disableMcpServer: vi.fn(),
  deleteMcpServer: vi.fn(),
  listInvocations: vi.fn(),
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

import McpServerListView from "./McpServerListView.vue";
import {
  listMcpServers,
  createMcpServer,
  enableMcpServer,
  disableMcpServer,
  deleteMcpServer,
} from "@/services/mcpRegistry";

const SAMPLE_SERVERS = [
  {
    id: "srv-qcc",
    tenant_id: "t-1",
    code: "qcc",
    name: "企查查",
    description: null,
    transport: "streamable_http",
    server_url: "https://mcp.qcc.com/mcp",
    credential_ref: "QCC_MCP_TOKEN",
    allowed_roles: ["admin", "data_admin"],
    enabled: true,
    timeout_ms: 30000,
    created_by: "u-1",
    created_at: "2026-07-01T00:00:00",
    updated_at: "2026-07-01T00:00:00",
  },
  {
    id: "srv-other",
    tenant_id: "t-1",
    code: "internal_hr",
    name: "内部 HR",
    description: "demo",
    transport: "sse",
    server_url: "https://hr.example.com/sse",
    credential_ref: null,
    allowed_roles: [],
    enabled: false,
    timeout_ms: 15000,
    created_by: "u-1",
    created_at: "2026-07-10T00:00:00",
    updated_at: "2026-07-10T00:00:00",
  },
];

let currentWrapper: ReturnType<typeof mount> | undefined;

async function mountView(role = "admin") {
  localStorage.setItem("metaedu_token", "test-token");
  localStorage.setItem("metaedu_role", role);
  setActivePinia(createPinia());
  const w = mount(McpServerListView);
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

describe("McpServerListView.vue (REQ-044 Task 4 / AC-10)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listMcpServers).mockResolvedValue(SAMPLE_SERVERS as never);
  });

  afterEach(() => {
    currentWrapper?.unmount();
    currentWrapper = undefined;
    localStorage.clear();
  });

  it("renders 2 server rows from listMcpServers", async () => {
    const wrapper = await mountView("admin");
    expect(wrapper.findAll('[data-testid="server-row"]')).toHaveLength(2);
    expect(wrapper.text()).toContain("qcc");
    expect(wrapper.text()).toContain("internal_hr");
  });

  it("register submit calls createMcpServer with form payload", async () => {
    vi.mocked(listMcpServers).mockResolvedValue([] as never);
    vi.mocked(createMcpServer).mockResolvedValue(SAMPLE_SERVERS[0] as never);

    const wrapper = await mountView("admin");
    await wrapper.find('[data-testid="register-btn"]').trigger("click");
    await flushPromises();

    // modal teleported to body
    expect(body('[data-testid="create-modal"]').exists()).toBe(true);
    await body('[data-testid="input-code"]').setValue("qcc");
    await body('[data-testid="input-name"]').setValue("企查查");
    await body('[data-testid="input-url"]').setValue("https://mcp.qcc.com/mcp");
    await body('[data-testid="input-transport"]').setValue("sse");
    await body('[data-testid="input-credential-ref"]').setValue("QCC_MCP_TOKEN");
    await body('[data-testid="input-roles"]').setValue("admin,data_admin");
    await body('[data-testid="submit-create"]').trigger("click");
    await flushPromises();

    expect(createMcpServer).toHaveBeenCalledTimes(1);
    expect(createMcpServer).toHaveBeenCalledWith(
      expect.objectContaining({
        code: "qcc",
        name: "企查查",
        server_url: "https://mcp.qcc.com/mcp",
        transport: "sse",
        credential_ref: "QCC_MCP_TOKEN",
        allowed_roles: ["admin", "data_admin"],
        timeout_ms: 30000,
      }),
    );
  });

  it("toggling enabled calls enableMcpServer / disableMcpServer", async () => {
    vi.mocked(disableMcpServer).mockResolvedValue({ ...SAMPLE_SERVERS[0], enabled: false } as never);
    vi.mocked(enableMcpServer).mockResolvedValue({
      ...SAMPLE_SERVERS[1],
      enabled: true,
      warning: null,
    } as never);

    const wrapper = await mountView("admin");
    // server 0 (srv-qcc) is enabled -> click disables
    await wrapper.findAll('[data-testid="toggle-enabled"]')[0].trigger("click");
    await flushPromises();
    expect(disableMcpServer).toHaveBeenCalledWith("srv-qcc");

    // server 1 (srv-other) is disabled -> click enables (probe=true)
    await wrapper.findAll('[data-testid="toggle-enabled"]')[1].trigger("click");
    await flushPromises();
    expect(enableMcpServer).toHaveBeenCalledWith("srv-other", true);
  });

  it("non-admin role: register/toggle/delete/audit buttons hidden, list read-only", async () => {
    const wrapper = await mountView("teacher");
    expect(wrapper.find('[data-testid="register-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="toggle-enabled"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="delete-btn"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="audit-btn"]').exists()).toBe(false);
    // 列表本身对非管理员可见（只读）
    expect(wrapper.findAll('[data-testid="server-row"]')).toHaveLength(2);
    // 启用状态以只读 tag 呈现
    expect(wrapper.find(".ui-tag-green").exists()).toBe(true);
  });

  it("delete confirm calls deleteMcpServer", async () => {
    vi.mocked(deleteMcpServer).mockResolvedValue(undefined as never);

    const wrapper = await mountView("admin");
    await wrapper.find('[data-testid="delete-btn"]').trigger("click");
    await flushPromises();
    // ConfirmDialog 被内联 mock，confirm 按钮在 wrapper 内
    await wrapper.find('[data-testid="confirm-confirm"]').trigger("click");
    await flushPromises();

    expect(deleteMcpServer).toHaveBeenCalledTimes(1);
    expect(deleteMcpServer).toHaveBeenCalledWith("srv-qcc");
  });
});
