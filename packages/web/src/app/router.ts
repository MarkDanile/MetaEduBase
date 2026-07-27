import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import type { FeatureFlagKey, NavSection, PermissionKey } from "./nav";
import {
  canAccess,
  type AccessContext,
  type FeatureFlags,
} from "./nav";

// REQ-060 Slice 1: RouteMeta augmentation -- route record 是 path/name/meta
// 唯一事实源；sidebar/breadcrumb/guard 从 meta 派生（nav.ts projectNavigation）。
declare module "vue-router" {
  interface RouteMeta {
    title?: string;
    section?: NavSection;
    order?: number;
    permission?: PermissionKey;
    hiddenInNav?: boolean;
    featureFlag?: FeatureFlagKey;
    activeNav?: string;
    icon?: unknown;
    guest?: boolean;
    requiresAuth?: boolean;
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/auth/LoginView.vue"),
    meta: { guest: true },
  },
  {
    path: "/share/:token",
    name: "share",
    component: () => import("@/views/share/ShareView.vue"),
    meta: { guest: true },
  },
  // REQ-060 Slice 2: /403 无权限页（不嵌套 Layout，独立全屏）
  {
    path: "/403",
    name: "forbidden",
    component: () => import("@/views/ForbiddenView.vue"),
    meta: { guest: true },
  },
  {
    path: "/",
    component: () => import("@/views/LayoutView.vue"),
    children: [
      {
        path: "",
        name: "home",
        component: () => import("@/views/HomeView.vue"),
        meta: { section: "overview", title: "总览", permission: "nav.overview", activeNav: "home", order: 1 },
      },
      {
        path: "knowledge",
        name: "knowledge",
        component: () => import("@/views/knowledge/KnowledgeBaseView.vue"),
        meta: { section: "knowledge_data", title: "知识库", permission: "nav.knowledge", activeNav: "knowledge", order: 1 },
      },
      {
        path: "resource",
        name: "resource",
        component: () => import("@/views/resource/ResourceLibraryView.vue"),
        meta: { section: "knowledge_data", title: "资源库", permission: "nav.knowledge", activeNav: "resource", order: 2 },
      },
      {
        path: "resource/:id",
        name: "file-detail",
        component: () => import("@/views/resource/FileDetailView.vue"),
        meta: { section: "knowledge_data", title: "文件详情", permission: "nav.knowledge", hiddenInNav: true, activeNav: "resource" },
      },
      {
        path: "database",
        name: "database",
        component: () => import("@/views/database/DatabaseView.vue"),
        meta: { section: "knowledge_data", title: "数据库", permission: "nav.data", activeNav: "database", order: 1 },
      },
      {
        path: "database/:catalogCode",
        name: "catalog-detail",
        component: () => import("@/views/database/CatalogDetailPage.vue"),
        meta: { section: "knowledge_data", title: "目录详情", permission: "nav.data", hiddenInNav: true, activeNav: "database" },
      },
      {
        path: "ai-chat",
        name: "ai-chat",
        component: () => import("@/views/ai-chat/AiChatView.vue"),
        meta: { section: "ai_work", title: "AI 问答", permission: "nav.ai_work", activeNav: "ai-chat", order: 1 },
      },
      // REQ-060 Slice 2: 新建目标路由（复用既有页面组件）
      {
        path: "data/templates",
        name: "templates-list",
        component: () => import("@/views/admin/TemplateListView.vue"),
        meta: { section: "knowledge_data", title: "数据要素模板", permission: "nav.data.templates", activeNav: "templates-list", order: 3, requiresAuth: true },
      },
      {
        path: "data/templates/:id",
        name: "template-detail",
        component: () => import("@/views/admin/TemplateEditorView.vue"),
        meta: { section: "knowledge_data", title: "模板详情", permission: "nav.data.templates", hiddenInNav: true, activeNav: "templates-list", requiresAuth: true },
      },
      {
        path: "capabilities/skills",
        name: "capabilities-skills",
        component: () => import("@/views/skill-registry/SkillListView.vue"),
        meta: { section: "capabilities", title: "Skill 库", permission: "nav.capabilities", activeNav: "capabilities-skills", order: 1, requiresAuth: true },
      },
      {
        path: "capabilities/mcp",
        name: "capabilities-mcp",
        component: () => import("@/views/mcp-registry/McpServerListView.vue"),
        meta: { section: "capabilities", title: "MCP 工具", permission: "nav.capabilities", activeNav: "capabilities-mcp", order: 2, requiresAuth: true },
      },
      {
        path: "system",
        name: "system",
        component: () => import("@/views/admin/AdminView.vue"),
        meta: { section: "system", title: "系统管理", permission: "nav.system", hiddenInNav: true, featureFlag: "system_management", requiresAuth: true },
      },
      // REQ-060 Slice 2: 旧链接重定向（1 版本周期后移除）
      {
        path: "skill-editor",
        redirect: { name: "capabilities-skills" },
      },
      {
        path: "admin",
        redirect: { name: "system" },
      },
      {
        path: "admin/template",
        redirect: { name: "templates-list" },
      },
      {
        path: "admin/template/:id",
        redirect: (to) => ({ name: "template-detail", params: { id: to.params.id } }),
      },
      {
        path: "admin/mcp-servers",
        redirect: { name: "capabilities-mcp" },
      },
      {
        path: "admin/skills",
        redirect: { name: "capabilities-skills" },
      },
      // AI 应用广场
      {
        path: "ai-apps",
        name: "AiAppsMarketplace",
        component: () => import("@/views/ai-apps/AiAppsMarketplaceView.vue"),
        meta: { section: "apps", title: "AI 应用广场", permission: "nav.apps.marketplace", activeNav: "AiAppsMarketplace", order: 1, requiresAuth: true },
      },
      {
        path: "ai-apps/admin",
        name: "AiAppsAdmin",
        component: () => import("@/views/ai-apps/AiAppsAdminView.vue"),
        meta: { section: "apps", title: "应用管理", permission: "nav.apps.admin", activeNav: "AiAppsAdmin", order: 2, requiresAuth: true },
      },
      {
        path: "ai-apps/admin/:id",
        name: "AiAppEdit",
        component: () => import("@/views/ai-apps/AiAppEditView.vue"),
        meta: { section: "apps", title: "编辑应用", permission: "nav.apps.admin", hiddenInNav: true, activeNav: "AiAppsAdmin", requiresAuth: true },
      },
      {
        path: "ai-apps/:code",
        name: "AiAppDetail",
        component: () => import("@/views/ai-apps/AiAppDetailView.vue"),
        meta: { section: "apps", title: "应用详情", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
      // 独立应用框架页
      {
        path: "apps/course-capability-map",
        name: "AppCourseCapabilityMap",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { section: "apps", title: "课程能力图谱", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
      {
        path: "apps/preview-guide",
        name: "AppPreviewGuide",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { section: "apps", title: "智能预习导学", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
      {
        path: "apps/resource-recommendation",
        name: "AppResourceRecommendation",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { section: "apps", title: "资源推荐", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
      {
        path: "apps/review-planner",
        name: "AppReviewPlanner",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { section: "apps", title: "复习巩固", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
      // REQ-046 / APP-005: 企业 360 背调工作台
      {
        path: "apps/enterprise-360-dd",
        name: "AppEnterprise360Dd",
        component: () => import("@/views/due-diligence/DdTaskListView.vue"),
        meta: { section: "apps", title: "企业 360 背调", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
      {
        path: "apps/enterprise-360-dd/tasks/:id",
        name: "AppEnterprise360DdDetail",
        component: () => import("@/views/due-diligence/DdTaskDetailView.vue"),
        meta: { section: "apps", title: "背调任务", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
      {
        path: "apps/enterprise-360-dd/reports/:reportId",
        name: "AppEnterprise360DdReport",
        component: () => import("@/views/due-diligence/DdReportView.vue"),
        meta: { section: "apps", title: "背调报告", permission: "nav.apps.marketplace", hiddenInNav: true, activeNav: "AiAppsMarketplace", requiresAuth: true },
      },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

// REQ-060 Slice 2: permission/feature guard + 403 + 重定向后重新执行目标 route guard
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem("metaedu_token");

  // 1. guest 路由（login/share/forbidden）：已登录时跳首页
  if (to.meta.guest) {
    if (token && to.name !== "forbidden") {
      next({ name: "home" });
    } else {
      next();
    }
    return;
  }

  // 2. 未认证 -> login
  if (!token) {
    next({ name: "login" });
    return;
  }

  // 3. permission/feature guard（fail-closed）
  const role = localStorage.getItem("metaedu_role");
  const featureFlags: FeatureFlags = {};
  const ctx: AccessContext = { role, featureFlags };

  if (to.meta.permission || to.meta.featureFlag) {
    const meta = to.meta as {
      permission?: PermissionKey;
      featureFlag?: FeatureFlagKey;
      section: NavSection;
      title: string;
    };
    if (!canAccess(meta, ctx)) {
      next({ name: "forbidden" });
      return;
    }
  }

  next();
});

export default router;
