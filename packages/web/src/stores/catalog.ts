/**
 * REQ-054 Task 7: Pinia store for catalog（数据库）列表。
 *
 * 与 auth/theme store 保持同样的 defineStore setup pattern。
 * 只暴露当前 task 需要的 list + loading；后续 Task 8 (CatalogDetailPage) 可能扩展。
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import { listCatalogs, type CatalogDTO } from "@/services/catalog";

export const useCatalogStore = defineStore("catalog", () => {
  const catalogs = ref<CatalogDTO[]>([]);
  const loading = ref(false);

  async function fetch() {
    loading.value = true;
    try {
      catalogs.value = await listCatalogs();
    } finally {
      loading.value = false;
    }
  }

  return { catalogs, loading, fetch };
});