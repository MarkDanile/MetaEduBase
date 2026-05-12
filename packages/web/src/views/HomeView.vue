<template>
  <div class="p-8 max-w-[1200px] mx-auto">
    <header class="mb-10 animate-slide-up">
      <p class="text-[13px] text-[var(--color-ink-tertiary)] mb-1 tracking-wide">{{ greeting }}</p>
      <h1 class="text-[32px] font-semibold tracking-tight" style="font-family: var(--font-display)">元知职教基座</h1>
      <p class="text-[15px] text-[var(--color-ink-secondary)] mt-1">探索、构建、管理你的职业教育知识体系</p>
    </header>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <RouterLink
        v-for="(item, i) in navItems"
        :key="item.route"
        :to="item.route"
        class="liquid-card p-6 group animate-slide-up"
        :class="[`stagger-${i + 1}`]"
      >
        <div class="flex items-start justify-between mb-5">
          <div class="w-11 h-11 rounded-[var(--radius-md)] flex items-center justify-center" :class="item.bgClass">
            <div v-html="item.icon" />
          </div>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mt-1 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:stroke-[var(--color-accent)]">
            <line x1="7" y1="17" x2="17" y2="7"/><polyline points="7 7 17 7 17 17"/>
          </svg>
        </div>
        <h2 class="text-[17px] font-semibold tracking-tight mb-1.5" style="font-family: var(--font-display)">{{ item.title }}</h2>
        <p class="text-[13px] text-[var(--color-ink-tertiary)] leading-relaxed">{{ item.desc }}</p>
      </RouterLink>
    </div>

    <div class="mt-8 glass rounded-[var(--radius-lg)] p-6 animate-slide-up stagger-5">
      <div class="flex items-center gap-3 mb-4">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--color-bg-mesh-3)] to-[var(--color-bg-mesh-1)] flex items-center justify-center">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>
          </svg>
        </div>
        <h3 class="text-[15px] font-semibold" style="font-family: var(--font-display)">快速开始</h3>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <button
          v-for="shortcut in shortcuts"
          :key="shortcut.label"
          @click="$router.push(shortcut.route)"
          class="text-left p-4 rounded-[var(--radius-md)] bg-[var(--color-glass-subtle)] hover:bg-[var(--color-glass)] border border-[var(--color-glass-border-subtle)] hover:border-[var(--color-glass-border)] transition-all duration-300"
          style="transition-timing-function: var(--ease-liquid)"
        >
          <p class="text-[13px] font-medium text-[var(--color-ink)]">{{ shortcut.label }}</p>
          <p class="text-[11px] text-[var(--color-ink-tertiary)] mt-0.5">{{ shortcut.hint }}</p>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const authStore = useAuthStore();

const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 12) return "早上好";
  if (h < 14) return "中午好";
  if (h < 18) return "下午好";
  return "晚上好";
});

const navItems = [
  {
    title: "知识库",
    desc: "构建和管理结构化的职业教育知识体系，涵盖专业、课程、技能点等多层级节点",
    route: "/knowledge",
    bgClass: "bg-gradient-to-br from-[var(--color-bg-mesh-1)] to-[var(--color-bg-mesh-2)]",
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
  },
  {
    title: "校本资源",
    desc: "上传和管理教学文档、视频、音频等多媒体教学资源，支持智能解析",
    route: "/resource",
    bgClass: "bg-gradient-to-br from-[var(--color-bg-mesh-2)] to-[var(--color-bg-mesh-4)]",
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
  },
  {
    title: "AI 助教",
    desc: "基于知识库的智能问答系统，精准检索课程内容与技能标准",
    route: "/ai-chat",
    bgClass: "bg-gradient-to-br from-[var(--color-bg-mesh-3)] to-[var(--color-bg-mesh-1)]",
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  },
  {
    title: "Skill 编排",
    desc: "可视化编排 AI 技能流程，构建复杂的自动化教学辅助工作流",
    route: "/skill-editor",
    bgClass: "bg-gradient-to-br from-[var(--color-bg-mesh-4)] to-[var(--color-bg-mesh-2)]",
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
  },
  {
    title: "系统管理",
    desc: "用户权限、租户配置和系统运维管理",
    route: "/admin",
    bgClass: "bg-gradient-to-br from-[var(--color-bg-mesh-1)] to-[var(--color-bg-mesh-4)]",
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v6m0 6v6m9-7h-6m-6 0H3m15.36 5.64l-4.24-4.24M9.88 9.88L5.64 5.64m12.72 0l-4.24 4.24M9.88 14.12l-4.24 4.24"/></svg>',
  },
];

const shortcuts = [
  { label: "浏览知识目录", hint: "查看专业和课程层级", route: "/knowledge" },
  { label: "与 AI 助教对话", hint: "提问职教相关问题", route: "/ai-chat" },
  { label: "上传教学资源", hint: "添加文档、视频等", route: "/resource" },
];
</script>
