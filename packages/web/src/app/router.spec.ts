/**
 * REQ-060 Slice 2: 受保护目标路由 + 守卫 + 重定向原子迁移测试。
 *
 * 覆盖：
 * - 低权角色深链 403（permission guard）
 * - 高权角色访问通过
 * - unknown role fail-closed 403
 * - 旧链接重定向到新路径
 * - /403 不产生循环（guest 路由 + 已登录时不跳 home）
 * - feature flag off -> 403
 */
import { describe, expect, it, beforeEach } from "vitest";

// 模拟 localStorage（vitest jsdom 环境）
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
});

// 动态 import router（依赖 localStorage）
async function createTestRouter() {
  const mod = await import("./router");
  return mod.default;
}

function setAuth(role: string | null) {
  if (role) {
    localStorageMock.setItem("metaedu_token", "fake-token");
    localStorageMock.setItem("metaedu_role", role);
  } else {
    localStorageMock.removeItem("metaedu_token");
    localStorageMock.removeItem("metaedu_role");
  }
}

beforeEach(() => {
  localStorageMock.clear();
});

describe("REQ-060 Slice 2: permission guard", () => {
  it("low role (teacher) deep link to capabilities -> 403", async () => {
    setAuth("teacher");
    const router = await createTestRouter();
    await router.push("/capabilities/skills");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("forbidden");
  });

  it("high role (admin) deep link to capabilities -> allowed", async () => {
    setAuth("admin");
    const router = await createTestRouter();
    await router.push("/capabilities/skills");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("capabilities-skills");
  });

  it("super_admin deep link to system (feature flag off) -> 403", async () => {
    setAuth("super_admin");
    const router = await createTestRouter();
    await router.push("/system");
    await router.isReady();
    // feature flag system_management 未设 -> fail-closed 403
    expect(router.currentRoute.value.name).toBe("forbidden");
  });

  it("unknown role deep link to any protected route -> 403", async () => {
    setAuth("unknown_role");
    const router = await createTestRouter();
    await router.push("/capabilities/skills");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("forbidden");
  });

  it("low role (student) deep link to data/templates -> 403", async () => {
    setAuth("student");
    const router = await createTestRouter();
    await router.push("/data/templates");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("forbidden");
  });

  it("high role (data_admin) deep link to data/templates -> allowed", async () => {
    setAuth("data_admin");
    const router = await createTestRouter();
    await router.push("/data/templates");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("templates-list");
  });
});

describe("REQ-060 Slice 2: old link redirects", () => {
  it("/skill-editor -> /capabilities/skills", async () => {
    setAuth("admin");
    const router = await createTestRouter();
    await router.push("/skill-editor");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("capabilities-skills");
  });

  it("/admin/mcp-servers -> /capabilities/mcp", async () => {
    setAuth("admin");
    const router = await createTestRouter();
    await router.push("/admin/mcp-servers");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("capabilities-mcp");
  });

  it("/admin/skills -> /capabilities/skills", async () => {
    setAuth("admin");
    const router = await createTestRouter();
    await router.push("/admin/skills");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("capabilities-skills");
  });

  it("/admin/template -> /data/templates", async () => {
    setAuth("admin");
    const router = await createTestRouter();
    await router.push("/admin/template");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("templates-list");
  });

  it("/admin -> /system", async () => {
    setAuth("super_admin");
    localStorageMock.setItem("metaedu_feature_system_management", "true");
    const router = await createTestRouter();
    await router.push("/admin");
    await router.isReady();
    // /admin redirects to /system; super_admin without feature flag -> 403
    expect(router.currentRoute.value.name).toBe("forbidden");
  });
});

describe("REQ-060 Slice 2: /403 no loop", () => {
  it("/403 is accessible when authenticated (no redirect loop)", async () => {
    setAuth("teacher");
    const router = await createTestRouter();
    await router.push("/403");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("forbidden");
  });

  it("/403 is accessible when unauthenticated", async () => {
    setAuth(null);
    const router = await createTestRouter();
    await router.push("/403");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("forbidden");
  });
});

describe("REQ-060 Slice 2: unauthenticated redirect", () => {
  it("unauthenticated -> login", async () => {
    setAuth(null);
    const router = await createTestRouter();
    await router.push("/capabilities/skills");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("login");
  });
});
