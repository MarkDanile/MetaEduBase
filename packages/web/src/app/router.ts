import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import type { FeatureFlagKey, NavSection, PermissionKey } from "./nav";

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
      {
        path: "skill-editor",
        name: "skill-editor",
        component: () => import("@/views/skill/SkillEditorView.vue"),
        meta: { section: "capabilities", title: "技能编排", hiddenInNav: true },
      },
      {
        path: "admin",
        name: "admin",
        component: () => import("@/views/admin/AdminView.vue"),
        meta: { section: "system", title: "系统管理", hiddenInNav: true },
      },
      {
        path: "admin/template",
        name: "TemplateManagement",
        component: () => import("@/views/admin/TemplateListView.vue"),
        meta: { section: "knowledge_data", title: "数据要素模板", permission: "nav.data.templates", hiddenInNav: true, activeNav: "templates-list", requiresAuth: true },
      },
      {
        path: "admin/template/:id",
        name: "TemplateDetail",
        component: () => import("@/views/admin/TemplateEditorView.vue"),
        meta: { section: "knowledge_data", title: "模板详情", permission: "nav.data.templates", hiddenInNav: true, activeNav: "templates-list", requiresAuth: true },
      },
      // REQ-044: MCP 服务最小管理页
      {
        path: "admin/mcp-servers",
        name: "McpServerList",
        component: () => import("@/views/mcp-registry/McpServerListView.vue"),
        meta: { section: "capabilities", title: "MCP 服务", permission: "nav.capabilities", hiddenInNav: true, activeNav: "capabilities-mcp", requiresAuth: true },
      },
      // REQ-045: Skill 服务最小管理页
      {
        path: "admin/skills",
        name: "SkillList",
        component: () => import("@/views/skill-registry/SkillListView.vue"),
        meta: { section: "capabilities", title: "Skill 服务", permission: "nav.capabilities", hiddenInNav: true, activeNav: "capabilities-skills", requiresAuth: true },
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

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem("metaedu_token");
  if (!to.meta.guest && !token) {
    next({ name: "login" });
  } else if (to.meta.guest && token) {
    next({ name: "home" });
  } else {
    next();
  }
});

export default router;
