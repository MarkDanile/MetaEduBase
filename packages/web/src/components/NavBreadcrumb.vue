<template>
  <!--
    REQ-060 Slice 3 收口（修订-2）：全局 Breadcrumb（NavBreadcrumb）。
    派生规则：
    1. 从当前 route 的 meta.activeNav 链向上追溯（router.getRoutes()）。
    2. 每一步校验：父项必须与当前 route 的 meta.section 一致，否则 fail-closed
       （不加入链，防误配 activeNav 跳出当前 section）。
    3. 链以 home 终止（home 自身不再向上）。
    4. 顶部追加虚拟「总览」首页 crumb（如果链中没有 home）。
    5. hiddenInNav route 仍出现（仅 sidebar 过滤 breadcrumb 不过滤）。
    6. 当前页（最后一项）非链接，aria-current="page"，符合 WAI-ARIA breadcrumb 模式。
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
      >
        {{ crumb.title }}
      </RouterLink>
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

/**
 * 单步沿 activeNav 向上走：父项必须与 currentRoute 的 section 一致；否则
 * fail-closed 返回 null（不引入跨 section 的 crumb，防误配 activeNav 跳出
 * 当前 IA 区域）。
 *
 * 返回值：父项 route name（同 section），或 null（不跳转）。
 */
function parentRouteName(
  currentName: string,
  currentSection: string | undefined,
): string | null {
  if (currentName === "home") return null;
  const currentMeta = readMeta(findRouteByName(currentName)?.meta);
  const parentName = currentMeta.activeNav;
  if (!parentName) return null;
  if (parentName === currentName) return null;
  const parentMeta = readMeta(findRouteByName(parentName)?.meta);
  if (!parentMeta.title) return null;
  // section 一致性校验（fail-closed）：
  // - currentSection 与 parentMeta.section 都必须存在
  // - 且严格相等
  // 任一缺失或不相等均返回 null（不允许跨 section 跳转；不允许 meta 缺失放行）。
  // 这与 Plan "无完整 meta 一律 fail-closed" 一致。
  if (
    currentSection === undefined ||
    parentMeta.section === undefined ||
    parentMeta.section !== currentSection
  ) {
    return null;
  }
  return parentName;
}

const crumbs = computed<Crumb[]>(() => {
  const currentMeta = readMeta(route.meta);
  const currentName = typeof route.name === "string" ? route.name : "";
  if (!currentName || !currentMeta.title) return [];

  const chain: Crumb[] = [];
  const visited = new Set<string>();

  // 沿 activeNav 链向上（每步同 section 校验），直到 home 或 fail-closed。
  let cursor: string | null = currentName;
  const cursorSection: string | undefined = currentMeta.section;
  const cursorChain: string[] = [];
  while (cursor && !visited.has(cursor)) {
    visited.add(cursor);
    cursorChain.push(cursor);
    if (cursor === "home") break;
    cursor = parentRouteName(cursor, cursorSection);
  }

  // cursorChain = [current, parent, ..., home]；breadcrumb 顺序 = reverse
  for (const name of cursorChain.reverse()) {
    const crumb = crumbFromName(name);
    if (crumb) chain.push(crumb);
  }

  // 顶部追加虚拟「总览」首页 crumb（如果链中没有 home）。
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
