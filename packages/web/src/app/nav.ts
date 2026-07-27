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

/** 一级导航区域枚举（spec §4 Target IA，知识与数据合并为单一区域）。 */
export type NavSection =
  | "overview"
  | "ai_work"
  | "apps"
  | "knowledge_data"
  | "capabilities"
  | "system";

/** Section descriptor（typed，供 Layout 直接渲染 label，不另造配置表）。 */
export interface SectionDescriptor {
  id: NavSection;
  label: string;
  order: number;
}

/** 全部 6 section 的 descriptor（spec §4 Target IA + 排序）。
 * 注：permission key nav.knowledge/nav.data/nav.data.templates 独立校验，
 * 但导航投影合并为单一"知识与数据"一级区域（spec 冻结）。 */
export const SECTION_DESCRIPTORS: Record<NavSection, SectionDescriptor> = {
  overview: { id: "overview", label: "总览", order: 1 },
  ai_work: { id: "ai_work", label: "AI 工作", order: 2 },
  apps: { id: "apps", label: "智能体应用", order: 3 },
  knowledge_data: { id: "knowledge_data", label: "知识与数据", order: 4 },
  capabilities: { id: "capabilities", label: "能力中心", order: 5 },
  system: { id: "system", label: "系统管理", order: 6 },
};

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

/** 已知 feature flag 集合（运行时验证，防同名非法 flag 放行）。 */
const KNOWN_FEATURE_FLAGS: ReadonlySet<string> = new Set<FeatureFlagKey>([
  "system_management",
  "agent_workspace",
  "agent_runtime",
  "agent_run_center",
]);

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


/**
 * 角色 -> permission 集合（spec §5.3 矩阵）。
 *
 * fail-closed：
 * - null role -> 空集合
 * - unknown role -> 空集合（不泄露任何入口，包括基础路由）
 * - HIGH_PRIVILEGE (admin/data_admin) -> 8 keys（无 system）
 * - super_admin -> 全部 9 keys
 * - low privilege (leader/teacher/employee/student) -> 5 base keys
 */
export function resolvePermissions(ctx: AccessContext): Set<PermissionKey> {
  if (ctx.role === null) {
    return new Set();
  }
  const role = ctx.role as Role;
  if (!isKnownRole(role)) {
    // unknown role fail-closed -> 空集合（不获任何权限）
    return new Set();
  }
  const base: PermissionKey[] = [
    "nav.overview",
    "nav.ai_work",
    "nav.apps.marketplace",
    "nav.knowledge",
    "nav.data",
  ];
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
 * - null role -> 拒绝
 * - unknown role -> 拒绝（即使无 permission 的基础路由也拒绝，fail-closed）
 * - 无 permission key -> 仅要求已认证 + 已知角色
 * - feature flag 未定义/关闭 -> 拒绝（fail-closed）
 */
export function canAccess(meta: RouteNavMeta, ctx: AccessContext): boolean {
  if (ctx.role === null) {
    return false;
  }
  const role = ctx.role as Role;
  if (!isKnownRole(role)) {
    // unknown role fail-closed: 拒绝所有路由（包括无 permission 的基础路由）
    return false;
  }
  if (meta.permission !== undefined) {
    const perms = resolvePermissions(ctx);
    if (!perms.has(meta.permission)) {
      return false;
    }
  }
  if (meta.featureFlag !== undefined) {
    // P1: 未知 feature flag fail-closed（运行时同名 true 也不放行）
    if (!KNOWN_FEATURE_FLAGS.has(meta.featureFlag)) {
      return false;
    }
    // fail-closed: flag 必须显式 true
    if (ctx.featureFlags[meta.featureFlag] !== true) {
      return false;
    }
  }
  return true;
}

/**
 * 从 localStorage 加载 feature flags（唯一运行时来源）。
 *
 * key 约定：`metaedu_feature_<flag>`，值 `"true"` 视为开启，其余（含缺失）视为关闭。
 * 仅读取 KNOWN_FEATURE_FLAGS 内的 flag，忽略未知 key（防同名非法 flag 放行）。
 *
 * 注意：system_management 等当前为未交付功能（hidden until flag on），
 * 后端 LoginResponse 暂未下发 flags；功能发布时由登录流程写入对应 key。
 * flag 缺失时 fail-closed（canAccess 拒绝），符合未发布功能的预期行为。
 */
export function loadFeatureFlags(): FeatureFlags {
  const flags: FeatureFlags = {};
  for (const key of KNOWN_FEATURE_FLAGS) {
    if (localStorage.getItem(`metaedu_feature_${key}`) === "true") {
      flags[key as FeatureFlagKey] = true;
    }
  }
  return flags;
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

/** 投影后的 section（descriptor-backed，含 label 供 Layout 渲染）。 */
export interface NavSectionProjection {
  id: NavSection;
  label: string;
  order: number;
  items: NavItem[];
}

/**
 * Route record 的结构化类型（兼容 Vue Router RouteRecordNormalized / RouteRecordRaw，
 * 不导入 vue-router 实例）。name 接受 string | symbol（Vue Router RouteRecordName）。
 */
export interface RouteLike {
  name?: string | symbol;
  path: string;
  meta?: Record<string, unknown>;
}

/**
 * 从 route records 投影可见导航（按 section 分组 + permission/hidden/flag 过滤）。
 *
 * 输入兼容 `router.getRoutes()` 返回的 RouteRecordNormalized[]（不导入 Router 实例）。
 * hiddenInNav=true 的 route 不出现在菜单（但 route 仍可达 + 守卫独立判定）。
 */
export function projectNavigation(
  routes: ReadonlyArray<RouteLike>,
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
    const routeName = String(route.name);
    const section = meta.section;
    const descriptor = SECTION_DESCRIPTORS[section];
    // P2: 非法 section fail-closed -- descriptor 不存在则跳过（不抛异常）
    if (!descriptor) {
      continue;
    }
    let sectionProj = sectionsMap.get(section);
    if (!sectionProj) {
      sectionProj = {
        id: section,
        label: descriptor.label,
        order: descriptor.order,
        items: [],
      };
      sectionsMap.set(section, sectionProj);
    }
    sectionProj.items.push({
      name: routeName,
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
