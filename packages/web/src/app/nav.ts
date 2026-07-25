/**
 * REQ-060 Slice 1: 导航事实源 + permission resolver（纯函数，不导入 Router 实例）。
 *
 * 单一事实源：route record 的 meta 派生 section/order/permission/hiddenInNav/
 * featureFlag。Sidebar/breadcrumb/route guard/首页快捷入口都从此派生。
 *
 * V1 permission 由已验证角色映射；API 始终是授权事实源。后续切换后端下发
 * permission grants 时不重写页面结构（只改 resolver）。
 *
 * fail-closed 原则：unknown/null role、未知 permission、关闭/未定义 feature flag
 * 一律拒绝。无 permission 的基础路由只要求已认证。
 */

/** 后端 RoleEnum 全集（BUG-017 冻结，D-1 统一）。 */
export type Role =
  | "super_admin"
  | "data_admin"
  | "admin"
  | "leader"
  | "teacher"
  | "employee"
  | "student";

/** HIGH_PRIVILEGE_ROLES（后端 role.py 一致）。 */
const HIGH_PRIVILEGE_ROLES: ReadonlySet<Role> = new Set([
  "super_admin",
  "data_admin",
  "admin",
]);

/** 一级导航区域枚举（spec §4 Target IA）。 */
export type NavSection =
  | "overview"
  | "ai_work"
  | "apps"
  | "knowledge"
  | "data"
  | "capabilities"
  | "system";

/** Permission key（spec §5.3 矩阵 9 个，独立校验，子 key 不蕴含父 key）。 */
export type PermissionKey =
  | "nav.overview"
  | "nav.ai_work"
  | "nav.apps.marketplace"
  | "nav.apps.admin"
  | "nav.knowledge"
  | "nav.data"
  | "nav.data.templates"
  | "nav.capabilities"
  | "nav.system";

export const PERMISSION_KEYS: PermissionKey[] = [
  "nav.overview",
  "nav.ai_work",
  "nav.apps.marketplace",
  "nav.apps.admin",
  "nav.knowledge",
  "nav.data",
  "nav.data.templates",
  "nav.capabilities",
  "nav.system",
];

/** Feature flag key（未交付功能 hidden until flag on）。 */
export type FeatureFlagKey =
  | "system_management"
  | "agent_workspace"
  | "agent_runtime"
  | "agent_run_center";

export type FeatureFlags = Partial<Record<FeatureFlagKey, boolean>>;

/** Route nav meta（Vue Router RouteMeta augmentation，见 router.ts/env.d.ts）。 */
export interface RouteNavMeta {
  title: string;
  section: NavSection;
  order?: number;
  permission?: PermissionKey;
  hiddenInNav?: boolean;
  featureFlag?: FeatureFlagKey;
  activeNav?: string;
  icon?: unknown;
}

/** 访问上下文（resolver 输入）。 */
export interface AccessContext {
  role: string | null;
  featureFlags: FeatureFlags;
}

/** section 排序权重（NavSection 枚举顺序）。 */
const SECTION_ORDER: Record<NavSection, number> = {
  overview: 1,
  ai_work: 2,
  apps: 3,
  knowledge: 4,
  data: 5,
  capabilities: 6,
  system: 7,
};

/**
 * 角色 -> permission 集合（spec §5.3 矩阵）。
 *
 * fail-closed：
 * - null role -> 空集合
 * - unknown role -> 5 base keys（同低权，不泄露管理入口）
 * - HIGH_PRIVILEGE (admin/data_admin) -> 8 keys（无 system）
 * - super_admin -> 全部 9 keys
 */
export function resolvePermissions(ctx: AccessContext): Set<PermissionKey> {
  if (ctx.role === null) {
    return new Set();
  }
  const base: PermissionKey[] = [
    "nav.overview",
    "nav.ai_work",
    "nav.apps.marketplace",
    "nav.knowledge",
    "nav.data",
  ];
  const role = ctx.role as Role;
  if (!isKnownRole(role)) {
    // unknown role fail-closed -> base only
    return new Set(base);
  }
  if (role === "super_admin") {
    return new Set(PERMISSION_KEYS);
  }
  if (HIGH_PRIVILEGE_ROLES.has(role)) {
    return new Set([
      ...base,
      "nav.apps.admin",
      "nav.data.templates",
      "nav.capabilities",
    ]);
  }
  // low privilege (leader/teacher/employee/student) -> base only
  return new Set(base);
}

function isKnownRole(role: string): role is Role {
  return (
    role === "super_admin" ||
    role === "data_admin" ||
    role === "admin" ||
    role === "leader" ||
    role === "teacher" ||
    role === "employee" ||
    role === "student"
  );
}

/**
 * 单 route 访问判定（fail-closed）。
 *
 * - null role + 有 permission -> 拒绝
 * - 无 permission key -> 仅要求已认证（role != null）
 * - feature flag 未定义/关闭 -> 拒绝（fail-closed）
 */
export function canAccess(meta: RouteNavMeta, ctx: AccessContext): boolean {
  if (ctx.role === null) {
    return false;
  }
  if (meta.permission !== undefined) {
    const perms = resolvePermissions(ctx);
    if (!perms.has(meta.permission)) {
      return false;
    }
  }
  if (meta.featureFlag !== undefined) {
    // fail-closed: flag 必须显式 true
    if (ctx.featureFlags[meta.featureFlag] !== true) {
      return false;
    }
  }
  return true;
}

/** 投影后的导航项。 */
export interface NavItem {
  name: string;
  path: string;
  title: string;
  section: NavSection;
  order: number;
  icon?: unknown;
}

/** 投影后的 section。 */
export interface NavSectionProjection {
  id: NavSection;
  order: number;
  items: NavItem[];
}

/**
 * 从 route records 投影可见导航（按 section 分组 + permission/hidden/flag 过滤）。
 *
 * 输入是 Vue Router RouteRecordRaw[]（只读 meta），不导入 Router 实例。
 * hiddenInNav=true 的 route 不出现在菜单（但 route 仍可达 + 守卫独立判定）。
 */
export function projectNavigation(
  routes: ReadonlyArray<{
    name?: string;
    path: string;
    meta?: Partial<RouteNavMeta>;
  }>,
  ctx: AccessContext,
): NavSectionProjection[] {
  const sectionsMap = new Map<NavSection, NavSectionProjection>();

  for (const route of routes) {
    const meta = route.meta as RouteNavMeta | undefined;
    if (!meta || !meta.section || !meta.title) {
      continue;
    }
    if (meta.hiddenInNav === true) {
      continue;
    }
    if (!canAccess(meta, ctx)) {
      continue;
    }
    if (!route.name) {
      continue;
    }
    const section = meta.section;
    let sectionProj = sectionsMap.get(section);
    if (!sectionProj) {
      sectionProj = {
        id: section,
        order: SECTION_ORDER[section],
        items: [],
      };
      sectionsMap.set(section, sectionProj);
    }
    sectionProj.items.push({
      name: route.name,
      path: route.path,
      title: meta.title,
      section,
      order: meta.order ?? 100,
      icon: meta.icon,
    });
  }

  // section 按 SECTION_ORDER 排序；item 按 meta.order 排序
  const sections = Array.from(sectionsMap.values());
  sections.sort((a, b) => a.order - b.order);
  for (const s of sections) {
    s.items.sort((a, b) => a.order - b.order);
  }
  return sections;
}
