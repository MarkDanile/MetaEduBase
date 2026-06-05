<template>
  <div class="p-[var(--spacing-page)] max-w-[1000px] mx-auto">
    <PageHeader title="元知职教基座" subtitle="构建 · 管理 · 探索 职业教育知识体系">
      <template #greeting>
        <p class="text-[var(--color-ink-tertiary)] mb-1">{{ greeting }}，{{ roleLabel }}</p>
      </template>
    </PageHeader>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-[var(--spacing-page)] animate-slide-up stagger-1">
      <div v-for="(stat, i) in stats" :key="stat.label" class="ui-panel liquid-card-scan p-4" :style="{ animationDelay: (i * 1.5 + 6) + 's' }">
        <div class="flex items-center gap-2.5 mb-2">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center" :class="stat.bgClass">
            <component :is="stat.icon" :size="16" :stroke-width="1.5" :class="stat.iconClass" />
          </div>
        </div>
        <p class="text-[var(--text-page-title)] font-semibold tracking-tight tabular-nums">{{ stat.value }}</p>
        <p class="text-[var(--color-ink-tertiary)] mt-0.5">{{ stat.label }}</p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div class="lg:col-span-3 space-y-5 animate-slide-up stagger-2">
        <div class="flex items-center justify-between">
          <h2 class="text-[var(--text-subtitle)] font-semibold">功能模块</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <RouterLink
            v-for="item in navItems"
            :key="item.route"
            :to="item.route"
            class="ui-panel p-4 group"
          >
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" :class="item.bgClass">
                <component :is="item.icon" :size="18" :stroke-width="1.5" :class="item.iconClass" />
              </div>
              <div class="flex-1 min-w-0">
                <h3 class="text-[var(--text-body)] font-semibold group-hover:text-[var(--color-accent)] transition-colors duration-200">{{ item.title }}</h3>
                <p class="text-[var(--color-ink-tertiary)] mt-0.5 truncate">{{ item.desc }}</p>
              </div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-[var(--color-ink-tertiary)] flex-shrink-0 transition-transform duration-200 group-hover:translate-x-1.5 group-hover:text-[var(--color-accent)]">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          </RouterLink>
        </div>
      </div>

      <div class="lg:col-span-2 animate-slide-up stagger-3">
        <div class="ui-panel p-5 space-y-5">
          <div>
            <h2 class="text-[var(--text-subtitle)] font-semibold mb-3">快捷操作</h2>
            <div class="space-y-1.5">
              <button
                v-for="shortcut in shortcuts"
                :key="shortcut.label"
                @click="$router.push(shortcut.route)"
                class="w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] hover:bg-[var(--color-bg-hover)] transition-colors group text-left"
              >
                <div class="w-8 h-8 rounded-md bg-[var(--color-accent-bg)] flex items-center justify-center flex-shrink-0">
                  <component :is="shortcut.icon" :size="14" :stroke-width="1.5" class="text-[var(--color-accent)]" />
                </div>
                <div class="flex-1 min-w-0">
                  <p class="font-medium group-hover:text-[var(--color-accent)] transition-colors">{{ shortcut.label }}</p>
                  <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">{{ shortcut.hint }}</p>
                </div>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="text-[var(--color-ink-tertiary)] flex-shrink-0 transition-transform group-hover:translate-x-1"><polyline points="9 18 15 12 9 6"/></svg>
              </button>
            </div>
          </div>

          <div class="border-t border-[var(--color-border-subtle)] pt-5">
            <h2 class="text-[var(--text-subtitle)] font-semibold mb-3">最近动态</h2>
            <div class="space-y-0">
              <div v-for="(activity, i) in recentActivities" :key="activity.text">
                <div class="flex items-start gap-3 py-2.5">
                  <div class="relative flex flex-col items-center">
                    <div class="w-2 h-2 rounded-full mt-1.5 flex-shrink-0" :class="activity.dotClass"></div>
                    <div v-if="i < recentActivities.length - 1" class="w-px flex-1 min-h-[12px] bg-[var(--color-border-subtle)] mt-1"></div>
                  </div>
                  <div class="flex-1 min-w-0">
                    <p class="text-[var(--color-ink)]">{{ activity.text }}</p>
                    <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-0.5">{{ activity.time }}</p>
                  </div>
                </div>
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
import { RouterLink } from "vue-router";
import {
  BookOpen,
  Database,
  FolderOpen,
  Globe2,
  MessageSquare,
  Settings,
  Upload,
} from "lucide-vue-next";
import { useAuthStore } from "@/stores/auth";
import { roleShortMap } from "@/constants/maps";
import PageHeader from "@/components/PageHeader.vue";
import api from "@/services/api";

const authStore = useAuthStore();

const roleLabel = computed(() => roleShortMap[authStore.userRole ?? ""] ?? "用户");

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 12) return "早上好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
});

const knowledgeCount = ref<number | null>(null);
const resourceCount = ref<number | null>(null);

const stats = computed(() => [
  {
    label: "知识节点",
    value: knowledgeCount.value ?? "—",
    bgClass: "bg-[var(--color-accent-bg)]",
    icon: BookOpen,
    iconClass: "text-[var(--color-accent)]",
  },
  {
    label: "资源库",
    value: resourceCount.value ?? "—",
    bgClass: "bg-[var(--color-tag-green)]",
    icon: FolderOpen,
    iconClass: "text-[var(--color-tag-green-text)]",
  },
  {
    label: "AI 问答",
    value: "—",
    bgClass: "bg-[var(--color-highlight-bg)]",
    icon: MessageSquare,
    iconClass: "text-[var(--color-highlight)]",
  },
  {
    label: "专业域覆盖",
    value: 10,
    bgClass: "bg-[var(--color-tag-purple)]",
    icon: Globe2,
    iconClass: "text-[var(--color-tag-purple-text)]",
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
    icon: BookOpen,
    iconClass: "text-[var(--color-accent)]",
  },
  {
    title: "资源库",
    desc: "上传和管理教学文档、视频等多媒体资源",
    route: "/resource",
    bgClass: "bg-[var(--color-tag-green)]",
    icon: FolderOpen,
    iconClass: "text-[var(--color-tag-green-text)]",
  },
  {
    title: "数据库",
    desc: "管理结构化数据集与知识图谱构建",
    route: "/database",
    bgClass: "bg-[var(--color-tag-amber)]",
    icon: Database,
    iconClass: "text-[var(--color-tag-amber-text)]",
  },
  {
    title: "AI 问答",
    desc: "基于知识库的智能问答，精准检索课程内容",
    route: "/ai-chat",
    bgClass: "bg-[var(--color-highlight-bg)]",
    icon: MessageSquare,
    iconClass: "text-[var(--color-highlight)]",
  },
  {
    title: "技能编排",
    desc: "可视化编排 AI 技能流程与自动化工作流",
    route: "/skill-editor",
    bgClass: "bg-[var(--color-tag-purple)]",
    icon: Settings,
    iconClass: "text-[var(--color-tag-purple-text)]",
  },
];

const shortcuts = [
  {
    label: "浏览知识目录",
    hint: "查看专业和课程层级",
    route: "/knowledge",
    icon: BookOpen,
  },
  {
    label: "AI 智能问答",
    hint: "提问职教相关问题",
    route: "/ai-chat",
    icon: MessageSquare,
  },
  {
    label: "上传教学资源",
    hint: "添加文档、视频等",
    route: "/resource",
    icon: Upload,
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
  } catch {
    // 首页统计失败不阻塞页面展示。
  }
}

onMounted(() => {
  loadStats();
});
</script>
