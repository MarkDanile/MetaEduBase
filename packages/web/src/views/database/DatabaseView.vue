<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader title="数据库" subtitle="按主题域管理数据集与知识图谱">
      <template #extra>
        <button
          v-if="canCreateCatalog"
          type="button"
          class="ui-btn-primary px-3 py-1.5 flex items-center gap-1.5"
          data-testid="catalog-create-btn"
          @click="showCreate = true"
        >
          <Plus :size="14" /> 新建数据库
        </button>
      </template>
    </PageHeader>

    <LoadingSpinner v-if="loading" text="加载数据库..." />

    <EmptyState
      v-else-if="!catalogs.length"
      title="还没有数据库"
      hint="管理员可以点击右上角“新建数据库”按主题域分组数据集"
    >
      <template #action>
        <button
          v-if="canCreateCatalog"
          type="button"
          class="ui-btn-primary px-3 py-1.5 flex items-center gap-1.5 mx-auto"
          @click="showCreate = true"
        >
          <Plus :size="14" /> 新建数据库
        </button>
      </template>
    </EmptyState>

    <div
      v-else
      class="grid gap-4 mt-4"
      style="grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))"
      data-testid="catalog-grid"
    >
      <CatalogCard
        v-for="catalog in catalogs"
        :key="catalog.id"
        :catalog="catalog"
        @click="onCardClick"
      />
    </div>

    <CatalogCreateDialog
      :open="showCreate"
      :submitting="creating"
      @update:open="(v) => (showCreate = v)"
      @submit="doCreate"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * REQ-054 Task 7: DatabaseView 改为 catalog（数据库）卡片列表。
 *
 * - 顶部 PageHeader + [+ 新建数据库] 按钮（仅 admin / data_admin / super_admin 可见）。
 * - 卡片网格 (v-for catalog in catalogs)。
 * - 点击卡片 → router.push(`/database/${catalog.code}`) （Task 8 负责该路由对应的 CatalogDetailPage）。
 * - 加载中 → LoadingSpinner；空 → EmptyState。
 *
 * 原本 DatabaseView 内部的数据集列表 + 图谱面板逻辑保留在 queries.ts 供 Task 8
 * 的 CatalogDetailPage 复用；本文件只负责「数据库」主题域列表 + 新建入口。
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Plus } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { useAuthStore } from "@/stores/auth";
import { useCatalogStore } from "@/stores/catalog";
import { createCatalog, type CatalogCreate, type CatalogDTO } from "@/services/catalog";
import { useToast } from "@/composables/useToast";
import CatalogCard from "@/views/database/CatalogCard.vue";
import CatalogCreateDialog from "@/views/database/CatalogCreateDialog.vue";

const router = useRouter();
const authStore = useAuthStore();
const catalogStore = useCatalogStore();
const toast = useToast();

// Roles allowed to create new databases (mirrors backend CatalogPermissionError logic).
const ADMIN_ROLES = new Set(["admin", "data_admin", "super_admin"]);
const canCreateCatalog = computed(() =>
  authStore.userRole ? ADMIN_ROLES.has(authStore.userRole) : false,
);

const showCreate = ref(false);
const creating = ref(false);

const catalogs = computed<CatalogDTO[]>(() => catalogStore.catalogs);
const loading = computed(() => catalogStore.loading);

onMounted(() => {
  void catalogStore.fetch();
});

function onCardClick(catalog: CatalogDTO) {
  // Task 8 will register /database/:code route and render CatalogDetailPage.
  // Fallback to /database if the route is not yet registered to avoid runtime errors.
  try {
    router.push(`/database/${catalog.code}`);
  } catch {
    router.push("/database");
  }
}

async function doCreate(req: CatalogCreate) {
  creating.value = true;
  try {
    await createCatalog(req);
    toast.success("数据库创建成功");
    showCreate.value = false;
    void catalogStore.fetch();
  } catch (err: unknown) {
    const message =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
      (err instanceof Error ? err.message : "创建失败");
    toast.error(message);
  } finally {
    creating.value = false;
  }
}
</script>