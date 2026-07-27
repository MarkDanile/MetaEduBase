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
        <p class="text-[var(--text-page-title)] font-semibold tabular-nums">{{ stat.value }}</p>
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
            v-for="item in homeCards"
            :key="item.name"
            :to="{ name: item.name }"
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
                :key="shortcut.name"
                @click="$router.push({ name: shortcut.name })"
                class="w-full flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] hover:bg-[var(--color-bg-hover)] transition-colors group text-left"
              >
                <div class="w-8 h-8 rounded-md bg-[var(--color-accent-bg)] flex items-center justify-center flex-shrink-0">
                  <component :is="shortcut.icon" :size="14" :stroke-width="1.5" class="text-[var(--color-accent)]" />
                </div>
                <div class="flex-1 min-w-0">
                  <p class="font-medium group-hover:text-[var(--color-accent)] transition-colors">{{ shortcut.title }}</p>
                  <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">{{ shortcut.desc }}</p>
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
import { RouterLink, useRouter } from "vue-router";
import {
  BookOpen,
  Database,
  FolderOpen,
  MessageSquare,
  LayoutTemplate,
  Workflow,
  Plug,
  Bot,
  Upload,
  Globe2,
  type LucideIcon,
} from "lucide-vue-next";
import { useAuthStore } from "@/stores/auth";
import { roleShortMap } from "@/constants/maps";
import PageHeader from "@/components/PageHeader.vue";
import api from "@/services/api";
import { canAccess, loadFeatureFlags } from "@/app/nav";

interface HomeCard {
  name: string;
  title: string;
  desc: string;
  icon: LucideIcon;
  bgClass: string;
  iconClass: string;
}

const authStore = useAuthStore();
const router = useRouter();

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

// REQ-060 Slice 3 收口：HomeView 展示配置只引用 route name；path、permission、
// hidden、feature flag 从 Route Record 解析。"技能编排" 旧入口在 Slice 2 已
// 重定向到 capabilities-skills，按 plan "下线技能编排" 不再列在首页。
interface CardSpec {
  name: string;
  title: string;
  desc: string;
  icon: LucideIcon;
  bgClass: string;
  iconClass: string;
}

const CARD_SPECS: CardSpec[] = [
  {
    name: "knowledge",
    title: "知识库",
    desc: "构建和管理结构化的职业教育知识体系",
    icon: BookOpen,
    bgClass: "bg-[var(--color-accent-bg)]",
    iconClass: "text-[var(--color-accent)]",
  },
  {
    name: "resource",
    title: "资源库",
    desc: "上传和管理教学文档、视频等多媒体资源",
    icon: FolderOpen,
    bgClass: "bg-[var(--color-tag-green)]",
    iconClass: "text-[var(--color-tag-green-text)]",
  },
  {
    name: "database",
    title: "数据库",
    desc: "管理结构化数据集与知识图谱构建",
    icon: Database,
    bgClass: "bg-[var(--color-tag-amber)]",
    iconClass: "text-[var(--color-tag-amber-text)]",
  },
  {
    name: "ai-chat",
    title: "AI 问答",
    desc: "基于知识库的智能问答，精准检索课程内容",
    icon: MessageSquare,
    bgClass: "bg-[var(--color-highlight-bg)]",
    iconClass: "text-[var(--color-highlight)]",
  },
  {
    name: "templates-list",
    title: "数据要素模板",
    desc: "配置结构化文档抽取模板与字段定义",
    icon: LayoutTemplate,
    bgClass: "bg-[var(--color-tag-purple)]",
    iconClass: "text-[var(--color-tag-purple-text)]",
  },
  {
    name: "capabilities-skills",
    title: "Skill 库",
    desc: "管理 AI 技能定义与执行流程",
    icon: Workflow,
    bgClass: "bg-[var(--color-tag-blue)]",
    iconClass: "text-[var(--color-tag-blue-text)]",
  },
  {
    name: "capabilities-mcp",
    title: "MCP 工具",
    desc: "注册和管理外部 MCP 数据源",
    icon: Plug,
    bgClass: "bg-[var(--color-tag-blue)]",
    iconClass: "text-[var(--color-tag-blue-text)]",
  },
  {
    name: "AiAppsMarketplace",
    title: "AI 应用广场",
    desc: "浏览与使用已发布的智能体应用",
    icon: Bot,
    bgClass: "bg-[var(--color-accent-bg)]",
    iconClass: "text-[var(--color-accent)]",
  },
];

const SHORTCUT_SPECS: CardSpec[] = [
  {
    name: "knowledge",
    title: "浏览知识目录",
    desc: "查看专业和课程层级",
    icon: BookOpen,
    bgClass: "",
    iconClass: "",
  },
  {
    name: "ai-chat",
    title: "AI 智能问答",
    desc: "提问职教相关问题",
    icon: MessageSquare,
    bgClass: "",
    iconClass: "",
  },
  {
    name: "resource",
    title: "上传教学资源",
    desc: "添加文档、视频等",
    icon: Upload,
    bgClass: "",
    iconClass: "",
  },
];

const homeCards = computed<HomeCard[]>(() => {
  const ctx = {
    role: authStore.userRole,
    featureFlags: loadFeatureFlags(),
  };
  const routes = router.getRoutes();
  return CARD_SPECS.filter((spec) => {
    const record = routes.find(
      (r) => typeof r.name === "string" && r.name === spec.name,
    );
    if (!record) return false;
    const meta = (record.meta ?? {}) as {
      title?: string;
      section?: string;
      permission?: Parameters<typeof canAccess>[0]["permission"];
      featureFlag?: Parameters<typeof canAccess>[0]["featureFlag"];
      hiddenInNav?: boolean;
    };
    return canAccess(
      {
        title: meta.title ?? "",
        section: (meta.section as never) ?? ("overview" as never),
        permission: meta.permission,
        featureFlag: meta.featureFlag,
      },
      ctx,
    );
  }).map((spec) => ({
    name: spec.name,
    title: spec.title,
    desc: spec.desc,
    icon: spec.icon,
    bgClass: spec.bgClass,
    iconClass: spec.iconClass,
  }));
});

const shortcuts = computed(() => {
  const ctx = {
    role: authStore.userRole,
    featureFlags: loadFeatureFlags(),
  };
  const routes = router.getRoutes();
  return SHORTCUT_SPECS.filter((spec) => {
    const record = routes.find(
      (r) => typeof r.name === "string" && r.name === spec.name,
    );
    if (!record) return false;
    const meta = (record.meta ?? {}) as {
      title?: string;
      section?: string;
      permission?: Parameters<typeof canAccess>[0]["permission"];
      featureFlag?: Parameters<typeof canAccess>[0]["featureFlag"];
    };
    return canAccess(
      {
        title: meta.title ?? "",
        section: (meta.section as never) ?? ("overview" as never),
        permission: meta.permission,
        featureFlag: meta.featureFlag,
      },
      ctx,
    );
  }).map((spec) => ({
    name: spec.name,
    title: spec.title,
    desc: spec.desc,
    icon: spec.icon,
  }));
});

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