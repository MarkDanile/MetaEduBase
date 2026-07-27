<template>
  <!--
    REQ-060 Slice 3 收口（修订）：全局 Breadcrumb（NavBreadcrumb）。
    派生链 = 虚拟首页 crumb + 当前 route 的 activeNav 指向的 sidebar route +
    当前 route 自身（如果当前 route 自身不在 sidebar 即 hiddenInNav）。
    全部数据来自 Route Record 的 meta.activeNav/meta.title，无 URL 推断。
    hiddenInNav 不影响 breadcrumb（仅 sidebar 过滤）。
    当前页（最后一项）非链接，aria-current="page"，符合 WAI-ARIA breadcrumb 模式。
  -->
  <nav
    v-if="crumbs.length > 1"
    class="breadcrumb-bar flex items-center gap-1.5 text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mb-3"
    aria-label="面包屑导航"
  >
    <template v-for="(crumb, i) in crumbs" :key="`${crumb.name}-${i}`">
      <RouterLink
        v-if="i < crumbs.length - 1"
        :to="{ name: crumb.name }"
        class="text-[var(--color-accent)] hover:underline"
      >{{ crumb.title }}</RouterLink>
      <span
        v-else
        class="text-[var(--color-ink)] font-medium"
        aria-current="page"
      >{{ crumb.title }}</span>
      <ChevronRight
        v-if="i < crumbs.length - 1"
        :size="12"
        :stroke-width="1.5"
        aria-hidden="true"
      />
    </template>
  </nav>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute, RouterLink, useRouter } from "vue-router";
import { ChevronRight } from "lucide-vue-next";

interface Crumb {
  name: string;
  title: string;
}

interface RouteMeta {
  title?: string;
  section?: string;
  activeNav?: string;
}

const route = useRoute();
const router = useRouter();

function readMeta(meta: unknown): RouteMeta {
  return (meta ?? {}) as RouteMeta;
}

function findRouteByName(name: string) {
  return router.getRoutes().find((r) => r.name === name);
}

function crumbFromName(name: string): Crumb | null {
  const r = findRouteByName(name);
  if (!r) return null;
  const meta = readMeta(r.meta);
  if (!meta.title) return null;
  return { name, title: meta.title };
}

const crumbs = computed<Crumb[]>(() => {
  const currentMeta = readMeta(route.meta);
  const currentName = typeof route.name === "string" ? route.name : "";
  if (!currentName || !currentMeta.title) return [];

  const chain: Crumb[] = [];
  const visited = new Set<string>();

  // 1. 顺着 activeNav 链向上找父项 crumb（activeNav 链以 home 终止）。
  //    典型链路：file-detail -> resource -> home；AiAppDetail -> AiAppsMarketplace -> home。
  let cursor: string | undefined = currentName;
  const cursorChain: string[] = [];
  while (cursor && !visited.has(cursor)) {
    visited.add(cursor);
    cursorChain.push(cursor);
    const meta = readMeta(findRouteByName(cursor)?.meta);
    if (!meta.activeNav) break;
    if (meta.activeNav === cursor) break;
    cursor = meta.activeNav;
  }

  // cursorChain = [current, parent, grandparent, ..., home]
  // breadcrumb 顺序 = reverse（home 在前，current 在末尾）
  for (const name of cursorChain.reverse()) {
    const crumb = crumbFromName(name);
    if (crumb) chain.push(crumb);
  }

  // 2. 顶部追加虚拟「总览」首页 crumb（如果链中没有 home）。
  //    例：/knowledge 的 activeNav = knowledge（自指），cursorChain 只有 [knowledge]，
  //    必须加 home 才能形成 "总览 / 知识库" 链。
  if (chain.length === 0 || chain[0].name !== "home") {
    const home = crumbFromName("home");
    if (home) chain.unshift(home);
  }

  return chain;
});
</script>

<style scoped>
.breadcrumb-bar {
  min-height: 18px;
}
</style>