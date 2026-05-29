import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/auth/LoginView.vue"),
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
