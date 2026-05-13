<template>
  <div class="p-8 max-w-[1000px] mx-auto">
    <header class="mb-8 animate-slide-up">
      <p class="text-[12px] text-[var(--color-ink-tertiary)] mb-1">{{ greeting }}，{{ roleLabel }}</p>
      <h1 class="text-[24px] font-semibold tracking-tight" style="letter-spacing:-0.5px">元知职教基座</h1>
      <p class="text-[14px] text-[var(--color-ink-secondary)] mt-1">构建 · 管理 · 探索 职业教育知识体系</p>
      <div class="wet-line mt-3" style="width:48px"></div>
    </header>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8 animate-slide-up stagger-1">
      <div v-for="(stat, i) in stats" :key="stat.label" class="liquid-card liquid-card-scan p-4" :style="{ animationDelay: (i * 1.5 + 6) + 's' }">
        <div class="flex items-center gap-2.5 mb-2">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center" :class="stat.bgClass">
            <div v-html="stat.icon" />
          </div>
        </div>
        <p class="text-[20px] font-semibold tracking-tight tabular-nums">{{ stat.value }}</p>
        <p class="text-[12px] text-[var(--color-ink-tertiary)] mt-0.5">{{ stat.label }}</p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-2 space-y-4 animate-slide-up stagger-2">
        <h2 class="text-[16px] font-semibold">功能模块</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <RouterLink
            v-for="(item, i) in navItems"
            :key="item.route"
            :to="item.route"
            class="liquid-card p-4 group"
          >
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" :class="item.bgClass">
                <div v-html="item.icon" />
              </div>
              <div class="flex-1 min-w-0">
                <h3 class="text-[14px] font-semibold group-hover:text-[var(--color-accent)] transition-colors duration-200">{{ item.title }}</h3>
                <p class="text-[12px] text-[var(--color-ink-tertiary)] mt-0.5 truncate">{{ item.desc }}</p>
              </div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-[var(--color-ink-tertiary)] flex-shrink-0 transition-transform duration-200 group-hover:translate-x-1.5 group-hover:text-[var(--color-accent)]">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          </RouterLink>
        </div>
      </div>

      <div class="space-y-4 animate-slide-up stagger-3">
        <h2 class="text-[16px] font-semibold">快速开始</h2>
        <div class="space-y-2">
          <button
            v-for="shortcut in shortcuts"
            :key="shortcut.label"
            @click="$router.push(shortcut.route)"
            class="liquid-card p-3.5 w-full text-left group"
          >
            <div class="flex items-center gap-2.5">
              <div class="w-7 h-7 rounded-md bg-[var(--color-accent-bg)] flex items-center justify-center flex-shrink-0">
                <div v-html="shortcut.icon" />
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-[13px] font-medium group-hover:text-[var(--color-accent)] transition-colors duration-200">{{ shortcut.label }}</p>
                <p class="text-[11px] text-[var(--color-ink-tertiary)]">{{ shortcut.hint }}</p>
              </div>
            </div>
          </button>
        </div>

        <div class="liquid-card p-4 mt-4">
          <h3 class="text-[13px] font-semibold mb-2.5">最近活动</h3>
          <div class="space-y-2.5">
            <div v-for="activity in recentActivities" :key="activity.text" class="flex items-start gap-2">
              <div class="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0" :class="activity.dotClass"></div>
              <div>
                <p class="text-[12px] text-[var(--color-ink)]">{{ activity.text }}</p>
                <p class="text-[10px] text-[var(--color-ink-tertiary)]">{{ activity.time }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import api from "@/services/api";

const authStore = useAuthStore();
const router = useRouter();

const roleMap: Record<string, string> = {
  super_admin: "管理员",
  domain_expert: "领域专家",
  teacher: "老师",
  student: "同学",
  harness_engineer: "工程师",
  system_ops: "运维",
};

const roleLabel = computed(() => roleMap[authStore.userRole ?? ""] ?? "用户");

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 12) return "早上好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
});

const knowledgeCount = ref(0);
const resourceCount = ref(0);
const chatCount = ref(0);

const stats = computed(() => [
  {
    label: "知识节点",
    value: knowledgeCount.value,
    bgClass: "bg-[var(--color-accent-bg)]",
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
  },
  {
    label: "校本资源",
    value: resourceCount.value,
    bgClass: "bg-[var(--color-tag-green)]",
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-tag-green-text)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  },
  {
    label: "AI 问答",
    value: chatCount.value,
    bgClass: "bg-[var(--color-highlight-bg)]",
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-highlight)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    label: "专业域覆盖",
    value: 10,
    bgClass: "bg-[var(--color-tag-purple)]",
    icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-tag-purple-text)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  },
]);

const recentActivities = [
  { text: "新增知识节点「电路基础」", time: "2 小时前", dotClass: "bg-[var(--color-accent)]" },
  { text: "上传资源「实训手册 v2」", time: "5 小时前", dotClass: "bg-[var(--color-tag-green-text)]" },
  { text: "AI 问答处理了 3 个问题", time: "昨天", dotClass: "bg-[var(--color-highlight)]" },
  { text: "知识节点「智能制造」已校验", time: "2 天前", dotClass: "bg-[var(--color-success)]" },
];

const navItems = [
  {
    title: "知识库",
    desc: "构建和管理结构化的职业教育知识体系",
    route: "/knowledge",
    bgClass: "bg-[var(--color-accent-bg)]",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
  },
  {
    title: "校本资源",
    desc: "上传和管理教学文档、视频等多媒体资源",
    route: "/resource",
    bgClass: "bg-[var(--color-tag-green)]",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-tag-green-text)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  },
  {
    title: "AI 问答",
    desc: "基于知识库的智能问答，精准检索课程内容",
    route: "/ai-chat",
    bgClass: "bg-[var(--color-highlight-bg)]",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-highlight)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    title: "技能编排",
    desc: "可视化编排 AI 技能流程与自动化工作流",
    route: "/skill-editor",
    bgClass: "bg-[var(--color-tag-purple)]",
    icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--color-tag-purple-text)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
  },
];

const shortcuts = [
  {
    label: "浏览知识目录",
    hint: "查看专业和课程层级",
    route: "/knowledge",
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
  },
  {
    label: "AI 智能问答",
    hint: "提问职教相关问题",
    route: "/ai-chat",
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    label: "上传教学资源",
    hint: "添加文档、视频等",
    route: "/resource",
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  },
];

async function loadStats() {
  try {
    const [knRes, resRes] = await Promise.allSettled([
      api.get("/knowledge/nodes", { params: { limit: 1 } }),
      api.get("/resources/", { params: { limit: 1 } }),
    ]);
    if (knRes.status === "fulfilled") {
      const d = knRes.value.data;
      knowledgeCount.value = d.total ?? (Array.isArray(d) ? d.length : 0);
    }
    if (resRes.status === "fulfilled") {
      const d = resRes.value.data;
      resourceCount.value = d.total ?? 0;
    }
  } catch {}
}

onMounted(() => {
  loadStats();
});
</script>
