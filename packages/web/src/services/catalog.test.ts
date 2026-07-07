/**
 * REQ-054 Task 7: catalog service 函数级 mock 测试。
 *
 * axios `api` 通过 vi.mock 替换成 stub；每个测试只断言函数按 endpoint + payload 调用 axios。
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const { mockGet, mockPost, mockPatch, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockPatch: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  default: {
    get: mockGet,
    post: mockPost,
    patch: mockPatch,
    delete: mockDelete,
  },
}));

import {
  listCatalogs,
  createCatalog,
  getCatalog,
  updateCatalog,
  deleteCatalog,
} from "./catalog";

describe("services/catalog (REQ-054 Task 7)", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockPatch.mockReset();
    mockDelete.mockReset();
  });

  it("listCatalogs GET /catalogs and unwraps res.data", async () => {
    const payload = [
      {
        id: "c-1",
        tenant_id: "t-1",
        code: "finance",
        name: "财务",
        description: null,
        icon: null,
        color: null,
        entity_types: ["bill"],
        default_business_purpose: null,
        is_active: true,
        created_by: "u-1",
        created_at: "2026-01-01T00:00:00",
        updated_at: "2026-01-01T00:00:00",
      },
    ];
    mockGet.mockResolvedValue({ data: payload });

    const result = await listCatalogs();

    expect(mockGet).toHaveBeenCalledWith("/catalogs");
    expect(result).toEqual(payload);
  });

  it("createCatalog POST /catalogs with payload and unwraps res.data", async () => {
    const dto = {
      id: "c-2",
      tenant_id: "t-1",
      code: "hr",
      name: "人力资源",
      description: "desc",
      icon: "User",
      color: "#abc123",
      entity_types: ["employee"],
      default_business_purpose: null,
      is_active: true,
      created_by: "u-1",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
    };
    mockPost.mockResolvedValue({ data: dto });

    const req = {
      code: "hr",
      name: "人力资源",
      entity_types: ["employee"],
      description: "desc",
    };
    const result = await createCatalog(req);

    expect(mockPost).toHaveBeenCalledWith("/catalogs", req);
    expect(result).toEqual(dto);
  });

  it("getCatalog GET /catalogs/{id}", async () => {
    const dto = { id: "c-3", code: "auto_repair", name: "汽修" };
    mockGet.mockResolvedValue({ data: dto });

    const result = await getCatalog("c-3");

    expect(mockGet).toHaveBeenCalledWith("/catalogs/c-3");
    expect(result).toEqual(dto);
  });

  it("updateCatalog PATCH /catalogs/{id} with payload", async () => {
    const dto = { id: "c-1", name: "新名" };
    mockPatch.mockResolvedValue({ data: dto });

    const result = await updateCatalog("c-1", { name: "新名" });

    expect(mockPatch).toHaveBeenCalledWith("/catalogs/c-1", { name: "新名" });
    expect(result).toEqual(dto);
  });

  it("deleteCatalog DELETE /catalogs/{id}", async () => {
    mockDelete.mockResolvedValue({});

    await deleteCatalog("c-1");

    expect(mockDelete).toHaveBeenCalledWith("/catalogs/c-1");
  });
});