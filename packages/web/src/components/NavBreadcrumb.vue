<template>
  <!--
    REQ-060 Slice 3 收口：全局 Breadcrumb（NavBreadcrumb）。
    从 route.matched 链派生（Vue Router matched = parent -> leaf 顺序）。
    仅显示含 meta.title 的层级（root layout 无 meta.title，自动跳过）。
    hiddenInNav 不影响 breadcrumb（sidebar 控制可见入口；breadcrumb 显示已到达的页面路径）。
    当前页（最后一项）非链接，aria-current="page"，符合 WAI-ARIA breadcrumb 模式。
  -->
  <nav
    v-if="crumbs.length > 1"
    class="breadcrumb-bar flex items-center gap-1.5 text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mb-3"
    aria-label="面包屑导航"
  >
    <template v-for="(crumb, i) in crumbs" :key="`${crumb.path}-${i}`">
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
  path: string;
  title: string;
}

const route = useRoute();
const router = useRouter();

/**
 * Breadcrumb 链派生规则：
 * - route.matched 仅含 parent -> leaf 链。对 `/resource/:id`，matched = [root, file-detail]
 *   （资源库 `/resource` 是 sibling，不是 parent），故 matched 不含「资源库」。
 * - 为详情页补中间 crumb：把当前 path 的最后一段剥掉，找到首个匹配的有
 *   meta.title 的 route；这就是「详情父级」section 入口（如 资源库）。
 * - 在链最前面追加虚拟「总览」首页 crumb（指向 home route）。
 */
const crumbs = computed<Crumb[]>(() => {
  const matched = route.matched.filter(
    (r) => Boolean((r.meta as { title?: string } | undefined)?.title),
  );
  if (matched.length === 0) return [];

  const leaf = matched[matched.length - 1];
  const leafName = typeof leaf.name === "string" ? leaf.name : "";
  const leafMeta = leaf.meta as { title: string };

  // 1. 当前页就是 home -> 只渲染 总览（避免 总览 / 总览）
  if (leafName === "home") {
    return [{ name: "home", path: "/", title: leafMeta.title }];
  }

  // 2. 找「详情父级」section 入口（向上找第一个匹配的有 meta.title 的具名 route）
  // 例：/data/templates/42 -> /data/templates（数据要素模板）
  // 例：/resource/abc -> /resource（资源库）
  // 例：/database/x -> /database（数据库）
  const pathSegments = route.path.split("/").filter(Boolean);
  const parentCrumbs: Crumb[] = [];
  if (pathSegments.length > 1) {
    const allRoutes = router.getRoutes();
    for (let i = pathSegments.length - 1; i > 0; i--) {
      const candidatePath = "/" + pathSegments.slice(0, i).join("/");
      const parentRoute = allRoutes.find(
        (r) =>
          r.path === candidatePath &&
          typeof r.name === "string" &&
          r.name !== leafName &&
          Boolean((r.meta as { title?: string } | undefined)?.title),
      );
      if (parentRoute) {
        const meta = parentRoute.meta as { title: string };
        parentCrumbs.push({
          name: String(parentRoute.name),
          path: parentRoute.path,
          title: meta.title,
        });
        // 只取最近一级父（避免 /a/b/c 撞出多个 parent）
        break;
      }
    }
  }

  // 3. 拼装：虚拟「总览」 + 可选父级 + matched 链（matched 已含 leaf，去重）
  const matchedCrumbs: Crumb[] = matched.map((r) => {
    const meta = r.meta as { title: string };
    return {
      name: typeof r.name === "string" ? r.name : "",
      path: r.path,
      title: meta.title,
    };
  });
  const chain: Crumb[] = [
    { name: "home", path: "/", title: "总览" },
    ...parentCrumbs,
    ...matchedCrumbs,
  ];
  // 去重（按 path + title）
  const seen = new Set<string>();
  return chain.filter((c) => {
    const key = `${c.path}::${c.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
});
</script>

<style scoped>
.breadcrumb-bar {
  /* 与 PageHeader 间距一致：8px gutter */
  min-height: 18px;
}
</style>