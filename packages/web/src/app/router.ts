import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

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
      },
      {
        path: "knowledge",
        name: "knowledge",
        component: () => import("@/views/knowledge/KnowledgeBaseView.vue"),
      },
      {
        path: "resource",
        name: "resource",
        component: () => import("@/views/resource/ResourceLibraryView.vue"),
      },
      {
        path: "resource/:id",
        name: "file-detail",
        component: () => import("@/views/resource/FileDetailView.vue"),
      },
      {
        path: "database",
        name: "database",
        component: () => import("@/views/database/DatabaseView.vue"),
      },
      {
        path: "database/:catalogCode",
        name: "catalog-detail",
        component: () => import("@/views/database/CatalogDetailPage.vue"),
      },
      {
        path: "ai-chat",
        name: "ai-chat",
        component: () => import("@/views/ai-chat/AiChatView.vue"),
      },
      {
        path: "skill-editor",
        name: "skill-editor",
        component: () => import("@/views/skill/SkillEditorView.vue"),
      },
      {
        path: "admin",
        name: "admin",
        component: () => import("@/views/admin/AdminView.vue"),
      },
      {
        path: "admin/template",
        name: "TemplateManagement",
        component: () => import("@/views/admin/TemplateListView.vue"),
        meta: { title: "数据要素模板", requiresAuth: true },
      },
      {
        path: "admin/template/:id",
        name: "TemplateDetail",
        component: () => import("@/views/admin/TemplateEditorView.vue"),
        meta: { title: "模板详情", requiresAuth: true },
      },
      // REQ-044: MCP 服务最小管理页
      {
        path: "admin/mcp-servers",
        name: "McpServerList",
        component: () => import("@/views/mcp-registry/McpServerListView.vue"),
        meta: { title: "MCP 服务", requiresAuth: true },
      },
      // REQ-045: Skill 服务最小管理页
      {
        path: "admin/skills",
        name: "SkillList",
        component: () => import("@/views/skill-registry/SkillListView.vue"),
        meta: { title: "Skill 服务", requiresAuth: true },
      },
      // AI 应用广场
      {
        path: "ai-apps",
        name: "AiAppsMarketplace",
        component: () => import("@/views/ai-apps/AiAppsMarketplaceView.vue"),
        meta: { title: "AI 应用广场", requiresAuth: true },
      },
      {
        path: "ai-apps/admin",
        name: "AiAppsAdmin",
        component: () => import("@/views/ai-apps/AiAppsAdminView.vue"),
        meta: { title: "应用管理", requiresAuth: true },
      },
      {
        path: "ai-apps/admin/:id",
        name: "AiAppEdit",
        component: () => import("@/views/ai-apps/AiAppEditView.vue"),
        meta: { title: "编辑应用", requiresAuth: true },
      },
      {
        path: "ai-apps/:code",
        name: "AiAppDetail",
        component: () => import("@/views/ai-apps/AiAppDetailView.vue"),
        meta: { title: "应用详情", requiresAuth: true },
      },
      // 独立应用框架页
      {
        path: "apps/course-capability-map",
        name: "AppCourseCapabilityMap",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { title: "课程能力图谱", requiresAuth: true },
      },
      {
        path: "apps/preview-guide",
        name: "AppPreviewGuide",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { title: "智能预习导学", requiresAuth: true },
      },
      {
        path: "apps/resource-recommendation",
        name: "AppResourceRecommendation",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { title: "资源推荐", requiresAuth: true },
      },
      {
        path: "apps/review-planner",
        name: "AppReviewPlanner",
        component: () => import("@/views/apps/AppPlaceholderView.vue"),
        meta: { title: "复习巩固", requiresAuth: true },
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
