/**
 * REQ-060 Slice 1: nav foundation -- permission resolver + navigation projection 测试。
 *
 * 覆盖 7 角色 × 9 permission key + unknown/null role fail-closed + feature flag
 * + section 排序 + hiddenInNav 投影。
 */
import { describe, expect, it } from "vitest";
import {
  type AccessContext,
  type FeatureFlags,
  PERMISSION_KEYS,
  type RouteNavMeta,
  canAccess,
  projectNavigation,
  resolvePermissions,
} from "./nav";

const ALL_ROLES = [
  "super_admin",
  "data_admin",
  "admin",
  "leader",
  "teacher",
  "employee",
  "student",
] as const;

const NO_FLAGS: FeatureFlags = {};

function ctx(role: string | null, flags: FeatureFlags = NO_FLAGS): AccessContext {
  return { role, featureFlags: flags };
}

describe("PERMISSION_KEYS", () => {
  it("exposes all 9 permission keys", () => {
    expect(PERMISSION_KEYS).toHaveLength(9);
    expect(PERMISSION_KEYS).toContain("nav.overview");
    expect(PERMISSION_KEYS).toContain("nav.system");
  });
});

// P2-4: 完整 7 角色 × 9 permission key 真值矩阵（防止同数量权限互换）
const TRUTH_TABLE: Record<string, boolean[]> = {
  //              overview ai_work marketplace admin knowledge data templates capabilities system
  super_admin:  [true,    true,    true,       true, true,      true, true,       true,        true],
  data_admin:   [true,    true,    true,       true, true,      true, true,       true,        false],
  admin:        [true,    true,    true,       true, true,      true, true,       true,        false],
  leader:       [true,    true,    true,       false, true,     true, false,      false,       false],
  teacher:      [true,    true,    true,       false, true,     true, false,      false,       false],
  employee:     [true,    true,    true,       false, true,     true, false,      false,       false],
  student:      [true,    true,    true,       false, true,     true, false,      false,       false],
};

describe("7 role × 9 permission truth table", () => {
  for (const role of ALL_ROLES) {
    it(`${role} matches truth table`, () => {
      const perms = resolvePermissions(ctx(role));
      const expected = TRUTH_TABLE[role];
      PERMISSION_KEYS.forEach((key, i) => {
        expect(perms.has(key)).toBe(expected[i]);
      });
    });
  }
});

describe("resolvePermissions", () => {
  it("super_admin gets all 9 permissions", () => {
    const perms = resolvePermissions(ctx("super_admin"));
    expect(perms.size).toBe(9);
    for (const key of PERMISSION_KEYS) {
      expect(perms.has(key)).toBe(true);
    }
  });

  it("data_admin and admin get HIGH_PRIVILEGE set (8 keys, no nav.system)", () => {
    for (const role of ["data_admin", "admin"] as const) {
      const perms = resolvePermissions(ctx(role));
      expect(perms.size).toBe(8);
      expect(perms.has("nav.system")).toBe(false);
      expect(perms.has("nav.capabilities")).toBe(true);
      expect(perms.has("nav.apps.admin")).toBe(true);
    }
  });

  it("leader gets 5 base keys (no admin/capabilities/system/templates)", () => {
    const perms = resolvePermissions(ctx("leader"));
    expect(perms.size).toBe(5);
    expect(perms.has("nav.overview")).toBe(true);
    expect(perms.has("nav.ai_work")).toBe(true);
    expect(perms.has("nav.apps.marketplace")).toBe(true);
    expect(perms.has("nav.knowledge")).toBe(true);
    expect(perms.has("nav.data")).toBe(true);
    expect(perms.has("nav.apps.admin")).toBe(false);
    expect(perms.has("nav.data.templates")).toBe(false);
    expect(perms.has("nav.capabilities")).toBe(false);
    expect(perms.has("nav.system")).toBe(false);
  });

  it("teacher/employee/student get same 5 base keys as leader", () => {
    for (const role of ["teacher", "employee", "student"] as const) {
      const perms = resolvePermissions(ctx(role));
      expect(perms.size).toBe(5);
    }
  });

  it("unknown role fail-closed: empty permissions (no base keys)", () => {
    const perms = resolvePermissions(ctx("unknown_role"));
    expect(perms.size).toBe(0);
  });

  it("null role fail-closed: empty permissions", () => {
    const perms = resolvePermissions(ctx(null));
    expect(perms.size).toBe(0);
  });

  it("unknown role canAccess denied even for permission-less route", () => {
    const meta: RouteNavMeta = { section: "overview", title: "Home" };
    expect(canAccess(meta, ctx("unknown_role"))).toBe(false);
  });
});

describe("canAccess", () => {
  it("route without permission key = only requires authenticated known role", () => {
    const meta: RouteNavMeta = { section: "overview", title: "Home" };
    for (const role of ALL_ROLES) {
      expect(canAccess(meta, ctx(role))).toBe(true);
    }
    // unknown role denied even for permission-less route (fail-closed)
    expect(canAccess(meta, ctx("unknown_role"))).toBe(false);
  });

  it("route with nav.system only super_admin passes", () => {
    const meta: RouteNavMeta = {
      section: "system",
      title: "System",
      permission: "nav.system",
    };
    expect(canAccess(meta, ctx("super_admin"))).toBe(true);
    expect(canAccess(meta, ctx("data_admin"))).toBe(false);
    expect(canAccess(meta, ctx("admin"))).toBe(false);
    expect(canAccess(meta, ctx("leader"))).toBe(false);
  });

  it("route with nav.capabilities HIGH_PRIVILEGE passes, low roles denied", () => {
    const meta: RouteNavMeta = {
      section: "capabilities",
      title: "Skills",
      permission: "nav.capabilities",
    };
    expect(canAccess(meta, ctx("super_admin"))).toBe(true);
    expect(canAccess(meta, ctx("data_admin"))).toBe(true);
    expect(canAccess(meta, ctx("admin"))).toBe(true);
    expect(canAccess(meta, ctx("leader"))).toBe(false);
    expect(canAccess(meta, ctx("student"))).toBe(false);
  });

  it("null role always denied when permission required", () => {
    const meta: RouteNavMeta = {
      section: "overview",
      title: "X",
      permission: "nav.overview",
    };
    expect(canAccess(meta, ctx(null))).toBe(false);
  });

  it("feature flag off -> denied even if role has permission", () => {
    const meta: RouteNavMeta = {
      section: "system",
      title: "System",
      permission: "nav.system",
      featureFlag: "system_management",
    };
    expect(canAccess(meta, ctx("super_admin", { system_management: false }))).toBe(false);
    expect(canAccess(meta, ctx("super_admin", { system_management: true }))).toBe(true);
  });

  it("feature flag undefined -> fail-closed denied", () => {
    const meta: RouteNavMeta = {
      section: "system",
      title: "System",
      permission: "nav.system",
      featureFlag: "system_management",
    };
    expect(canAccess(meta, ctx("super_admin", NO_FLAGS))).toBe(false);
  });
});

describe("projectNavigation", () => {
  const routes: {
    name: string;
    path: string;
    meta: Partial<RouteNavMeta>;
  }[] = [
    {
      name: "home",
      path: "/",
      meta: { section: "overview", title: "总览", order: 1 },
    },
    {
      name: "knowledge",
      path: "/knowledge",
      meta: { section: "knowledge_data", title: "知识库", order: 1 },
    },
    {
      name: "skills",
      path: "/capabilities/skills",
      meta: {
        section: "capabilities",
        title: "Skill 库",
        order: 1,
        permission: "nav.capabilities",
      },
    },
    {
      name: "system",
      path: "/system",
      meta: {
        section: "system",
        title: "系统管理",
        order: 1,
        permission: "nav.system",
        featureFlag: "system_management",
      },
    },
    {
      name: "file-detail",
      path: "/resource/:id",
      meta: { section: "knowledge_data", title: "文件详情", hiddenInNav: true },
    },
  ];

  it("projects visible sections ordered, filters by permission + hiddenInNav", () => {
    const sections = projectNavigation(routes, ctx("super_admin", { system_management: true }));
    const sectionIds = sections.map((s) => s.id);
    expect(sectionIds).toEqual(["overview", "knowledge_data", "capabilities", "system"]);
    // hiddenInNav excluded
    const allItems = sections.flatMap((s) => s.items);
    expect(allItems.find((i) => i.name === "file-detail")).toBeUndefined();
  });

  it("low role (teacher) does not see capabilities/system sections", () => {
    const sections = projectNavigation(routes, ctx("teacher"));
    const sectionIds = sections.map((s) => s.id);
    expect(sectionIds).toContain("overview");
    expect(sectionIds).toContain("knowledge_data");
    expect(sectionIds).not.toContain("capabilities");
    expect(sectionIds).not.toContain("system");
  });

  it("feature flag off hides system section even for super_admin", () => {
    const sections = projectNavigation(
      routes,
      ctx("super_admin", { system_management: false }),
    );
    expect(sections.map((s) => s.id)).not.toContain("system");
  });

  it("null role -> no sections", () => {
    const sections = projectNavigation(routes, ctx(null));
    expect(sections).toEqual([]);
  });

  it("sections ordered by section order, items ordered by route meta order", () => {
    const orderedRoutes = [
      { name: "b", path: "/b", meta: { section: "knowledge_data" as const, title: "B", order: 2 } },
      { name: "a", path: "/a", meta: { section: "knowledge_data" as const, title: "A", order: 1 } },
    ];
    const sections = projectNavigation(orderedRoutes, ctx("super_admin"));
    expect(sections[0].items[0].name).toBe("a");
    expect(sections[0].items[1].name).toBe("b");
  });

  it("P2: illegal section fail-closed skipped (no throw)", () => {
    const illegalRoutes = [
      { name: "bad", path: "/bad", meta: { section: "nonexistent" as never, title: "X" } },
    ];
    // 不应抛异常，非法 section 被跳过
    const sections = projectNavigation(illegalRoutes, ctx("super_admin"));
    expect(sections).toEqual([]);
  });
});
