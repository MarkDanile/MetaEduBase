/**
 * REQ-046 / APP-005 Slice 5: DdTaskListView 入口 smoke。
 *
 * 覆盖：
 * 1. 渲染任务列表（listTasks -> 行，含状态 tag 与已确认主体）
 * 2. 新建任务提交调用 createTask 并跳转详情页
 * 3. 必填校验：标题 / 主体查询为空不提交
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises, DOMWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

const pushMock = vi.fn();
vi.mock("vue-router", () => ({
  useRouter: () => ({ push: pushMock }),
  useRoute: () => ({ params: {} }),
}));

vi.mock("@/services/dueDiligence", () => ({
  listTasks: vi.fn(),
  createTask: vi.fn(),
}));

vi.mock("@/composables/useToast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

import DdTaskListView from "./DdTaskListView.vue";
import { listTasks, createTask } from "@/services/dueDiligence";

const SAMPLE_TASKS = [
  {
    id: "task-1",
    tenant_id: "t-1",
    title: "某科技公司入驻背调",
    subject_query: "某科技有限公司",
    status: "subject_pending",
    confirmed_subject: null,
    created_by: "u-1",
  },
  {
    id: "task-2",
    tenant_id: "t-1",
    title: "另一家企业背调",
    subject_query: "另一家企业",
    status: "review",
    confirmed_subject: { company_name: "另一家企业有限公司", credit_code: "91XX" },
    created_by: "u-1",
  },
];

let currentWrapper: ReturnType<typeof mount> | undefined;

async function mountView() {
  localStorage.setItem("metaedu_token", "test-token");
  localStorage.setItem("metaedu_role", "admin");
  setActivePinia(createPinia());
  const w = mount(DdTaskListView);
  currentWrapper = w;
  await flushPromises();
  return w;
}

function body(selector: string): DOMWrapper<Element> {
  const el = document.body.querySelector(selector);
  if (!el) throw new Error(`body: not found: ${selector}`);
  return new DOMWrapper(el);
}

describe("DdTaskListView.vue (REQ-046 / APP-005)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listTasks).mockResolvedValue(SAMPLE_TASKS as never);
  });

  afterEach(() => {
    currentWrapper?.unmount();
    currentWrapper = undefined;
    localStorage.clear();
  });

  it("renders task rows with status tags and confirmed subject", async () => {
    const wrapper = await mountView();
    expect(wrapper.findAll('[data-testid="task-row"]')).toHaveLength(2);
    expect(wrapper.text()).toContain("某科技公司入驻背调");
    expect(wrapper.text()).toContain("待确认主体");
    expect(wrapper.text()).toContain("待人工复核");
    // 已确认主体在第二行
    expect(wrapper.findAll('[data-testid="task-subject"]')).toHaveLength(1);
    expect(wrapper.text()).toContain("另一家企业有限公司");
  });

  it("create submit calls createTask and navigates to detail", async () => {
    vi.mocked(createTask).mockResolvedValue(SAMPLE_TASKS[0] as never);

    const wrapper = await mountView();
    await wrapper.find('[data-testid="create-task-btn"]').trigger("click");
    await flushPromises();

    await body('[data-testid="input-title"]').setValue("新背调任务");
    await body('[data-testid="input-subject-query"]').setValue("目标企业");
    await body('[data-testid="submit-create"]').trigger("click");
    await flushPromises();

    expect(createTask).toHaveBeenCalledTimes(1);
    expect(createTask).toHaveBeenCalledWith({ title: "新背调任务", subject_query: "目标企业" });
    expect(pushMock).toHaveBeenCalledWith({
      name: "AppEnterprise360DdDetail",
      params: { id: "task-1" },
    });
  });

  it("create rejects empty title / subject_query without calling API", async () => {
    const wrapper = await mountView();
    await wrapper.find('[data-testid="create-task-btn"]').trigger("click");
    await flushPromises();

    // 两个必填都为空 -> submit 禁用，不调用
    expect(body('[data-testid="submit-create"]').attributes("disabled")).toBeDefined();
    await body('[data-testid="submit-create"]').trigger("click");
    await flushPromises();
    expect(createTask).not.toHaveBeenCalled();
  });
});
