/**
 * REQ-042 WS-S1: agentWorkspace service 函数级 mock 测试。
 *
 * axios `api` 经 vi.mock 替换为 stub；断言各函数按契约 endpoint + If-Match 头调用，
 * 并覆盖 parseApiError 的三种 detail 形状（对象 / 字符串 / FastAPI 422 数组）。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, mockPatch, mockPut, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockPut: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  default: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    put: mockPut,
    delete: mockDelete,
  },
}));

import {
  archiveConversation,
  createConversation,
  deleteConversation,
  getConversation,
  getRun,
  listConversations,
  listMessages,
  parseApiError,
  pinConversation,
  renameConversation,
  restoreConversation,
  unpinConversation,
} from "./agentWorkspace";

describe("services/agentWorkspace (REQ-042 WS-S1)", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockPatch.mockReset();
    mockPut.mockReset();
    mockDelete.mockReset();
  });

  it("listConversations GET 默认 state=active，q/cursor/limit 按需带上", async () => {
    mockGet.mockResolvedValue({ data: { items: [], next_cursor: null } });

    await listConversations();
    expect(mockGet).toHaveBeenCalledWith("/agent-workspace/conversations", {
      params: { state: "active" },
    });

    mockGet.mockClear();
    mockGet.mockResolvedValue({ data: { items: [], next_cursor: "cur-2" } });
    await listConversations({ state: "archived", q: "报告", cursor: "cur-1", limit: 20 });
    expect(mockGet).toHaveBeenCalledWith("/agent-workspace/conversations", {
      params: { state: "archived", q: "报告", cursor: "cur-1", limit: 20 },
    });
  });

  it("createConversation POST body", async () => {
    const dto = { id: "c-1" };
    mockPost.mockResolvedValue({ data: dto });

    const result = await createConversation({ title: "标题" });
    expect(mockPost).toHaveBeenCalledWith("/agent-workspace/conversations", {
      title: "标题",
    });
    expect(result).toEqual(dto);
  });

  it("getConversation GET /{id}，includeDeleted -> include_deleted=true", async () => {
    mockGet.mockResolvedValue({ data: { id: "c-1" } });

    await getConversation("c-1");
    expect(mockGet).toHaveBeenCalledWith("/agent-workspace/conversations/c-1", {
      params: {},
    });

    mockGet.mockClear();
    await getConversation("c-1", { includeDeleted: true });
    expect(mockGet).toHaveBeenCalledWith("/agent-workspace/conversations/c-1", {
      params: { include_deleted: true },
    });
  });

  it("renameConversation PATCH 带 If-Match revision 头", async () => {
    mockPatch.mockResolvedValue({ data: { id: "c-1", revision: 3 } });

    await renameConversation("c-1", "新标题", 2);
    expect(mockPatch).toHaveBeenCalledWith(
      "/agent-workspace/conversations/c-1",
      { title: "新标题" },
      { headers: { "If-Match": "2" } },
    );
  });

  it("pin / unpin 使用 PUT / DELETE /{id}/pin（无 If-Match）", async () => {
    mockPut.mockResolvedValue({ data: { id: "c-1", pinned_at: "x" } });
    mockDelete.mockResolvedValue({ data: { id: "c-1", pinned_at: null } });

    await pinConversation("c-1");
    expect(mockPut).toHaveBeenCalledWith("/agent-workspace/conversations/c-1/pin");

    await unpinConversation("c-1");
    expect(mockDelete).toHaveBeenCalledWith("/agent-workspace/conversations/c-1/pin");
  });

  it("archive / restore POST 带 If-Match", async () => {
    mockPost.mockResolvedValue({ data: { id: "c-1" } });

    await archiveConversation("c-1", 5);
    expect(mockPost).toHaveBeenCalledWith(
      "/agent-workspace/conversations/c-1/archive",
      {},
      { headers: { "If-Match": "5" } },
    );

    await restoreConversation("c-1", 6);
    expect(mockPost).toHaveBeenCalledWith(
      "/agent-workspace/conversations/c-1/restore",
      {},
      { headers: { "If-Match": "6" } },
    );
  });

  it("deleteConversation DELETE 带 If-Match", async () => {
    mockDelete.mockResolvedValue({ data: { id: "c-1", state: "deleted" } });

    await deleteConversation("c-1", 7);
    expect(mockDelete).toHaveBeenCalledWith("/agent-workspace/conversations/c-1", {
      headers: { "If-Match": "7" },
    });
  });

  it("listMessages GET /{id}/messages 带 before_seq/after_seq/limit", async () => {
    mockGet.mockResolvedValue({ data: { items: [], has_more: false } });

    await listMessages("c-1", { before_seq: 40, limit: 50 });
    expect(mockGet).toHaveBeenCalledWith("/agent-workspace/conversations/c-1/messages", {
      params: { before_seq: 40, limit: 50 },
    });

    mockGet.mockClear();
    await listMessages("c-1");
    expect(mockGet).toHaveBeenCalledWith("/agent-workspace/conversations/c-1/messages", {
      params: {},
    });
  });

  it("getRun GET /agent-runs/{id}", async () => {
    mockGet.mockResolvedValue({ data: { id: "r-1" } });

    await getRun("r-1");
    expect(mockGet).toHaveBeenCalledWith("/agent-runs/r-1");
  });

  describe("parseApiError", () => {
    it("业务错误 detail 为 {code,message} 对象 -> 读 code", () => {
      const err = {
        response: {
          status: 409,
          data: { detail: { code: "revision_conflict", message: "版本冲突" } },
        },
      };
      expect(parseApiError(err)).toEqual({
        status: 409,
        code: "revision_conflict",
        message: "版本冲突",
      });
    });

    it("detail 为字符串（如 401） -> 直接作为 message，无 code", () => {
      const err = { response: { status: 401, data: { detail: "无效的认证令牌" } } };
      expect(parseApiError(err)).toEqual({ status: 401, code: undefined, message: "无效的认证令牌" });
    });

    it("FastAPI 422 detail 为数组 -> 取首条 msg", () => {
      const err = {
        response: {
          status: 422,
          data: { detail: [{ loc: ["query", "q"], msg: "至少 2 个字符", type: "value_error" }] },
        },
      };
      expect(parseApiError(err)).toEqual({ status: 422, code: undefined, message: "至少 2 个字符" });
    });

    it("网络错误（无 response） -> fallback", () => {
      expect(parseApiError(new Error("Network Error"), "操作失败")).toEqual({
        status: undefined,
        code: undefined,
        message: "Network Error",
      });
      expect(parseApiError({}, "操作失败")).toEqual({
        status: undefined,
        code: undefined,
        message: "操作失败",
      });
    });
  });
});
