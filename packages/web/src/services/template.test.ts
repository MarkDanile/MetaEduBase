import { beforeEach, describe, expect, it, vi } from "vitest";

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}));

vi.mock("@/services/api", () => ({
  default: {
    get: mockGet,
  },
}));

import { templateApi } from "./template";

describe("services/template management and lookup contracts", () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it("keeps the management list endpoint as the default list contract", () => {
    templateApi.list();

    expect(mockGet).toHaveBeenCalledWith("/templates");
  });

  it("preserves the include_deprecated management query", () => {
    templateApi.list(true);

    expect(mockGet).toHaveBeenCalledWith("/templates?include_deprecated=true");
  });

  it("uses the dedicated authenticated lookup endpoint", () => {
    templateApi.lookup();

    expect(mockGet).toHaveBeenCalledWith("/templates/lookup");
  });
});
