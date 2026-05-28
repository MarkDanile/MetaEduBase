<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader title="模板管理" subtitle="结构化数据提取模板配置" />

    <ui-page-section class="mt-4">
      <!-- Template grid -->
      <LoadingSpinner v-if="loading" text="加载模板..." />
      <EmptyState
        v-else-if="templates.length === 0"
        title="暂无模板"
        hint="创建模板开始结构化数据提取"
      />
      <div
        v-else
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      >
        <ui-panel
          v-for="t in templates"
          :key="t.id"
          class="cursor-pointer hover:border-[var(--color-accent)] transition-colors group"
          @click="router.push(`/admin/template/${t.id}`)"
        >
          <div class="flex flex-col gap-2">
            <!-- Template name -->
            <div class="flex items-start justify-between gap-2">
              <h3 class="text-[var(--text-subtitle)] font-medium text-[var(--color-ink)] truncate flex-1">
                {{ t.name }}
              </h3>
              <button
                class="liquid-btn-ghost p-1 opacity-0 group-hover:opacity-100 transition-opacity text-red-500"
                @click.stop="confirmDelete(t)"
              >
                <Trash2 :size="14" />
              </button>
            </div>

            <!-- Doc type tags -->
            <div class="flex flex-wrap gap-1">
              <span
                v-for="dt in t.doc_types"
                :key="dt"
                class="liquid-tag-blue text-[var(--text-micro)]"
              >
                {{ dt }}
              </span>
              <span v-if="t.doc_types.length === 0" class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
                未指定类型
              </span>
            </div>

            <!-- Meta info -->
            <div class="flex items-center gap-3 text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
              <span>{{ countFields(t.fields) }} 个字段</span>
              <span>{{ formatDate(t.updated_at) }}</span>
            </div>
          </div>
        </ui-panel>
      </div>
    </ui-page-section>

    <!-- Delete confirmation -->
    <ConfirmDialog
      v-model:open="showDeleteDialog"
      title="删除模板"
      :message="`确定删除模板「${deleteTarget?.name}」？此操作不可恢复。`"
      danger
      @confirm="doDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { Trash2 } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useToast } from "@/composables/useToast";
import { templateApi, type Template, type Field } from "@/services/template";

const router = useRouter();
const toast = useToast();

const templates = ref<Template[]>([]);
const loading = ref(false);
const showDeleteDialog = ref(false);
const deleteTarget = ref<Template | null>(null);

function countFields(fields: Field[]): number {
  let count = 0;
  for (const f of fields) {
    count += 1;
    if (f.children) count += countFields(f.children);
    if (f.items) count += countFields(f.items);
  }
  return count;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("zh-CN", {
    month: "short",
    day: "numeric",
  });
}

function confirmDelete(t: Template) {
  deleteTarget.value = t;
  showDeleteDialog.value = true;
}

async function doDelete() {
  if (!deleteTarget.value) return;
  try {
    await templateApi.delete(deleteTarget.value.id);
    toast.success("模板已删除");
    templates.value = templates.value.filter((t) => t.id !== deleteTarget.value!.id);
    deleteTarget.value = null;
    showDeleteDialog.value = false;
  } catch {
    toast.error("删除失败");
  }
}

async function loadTemplates() {
  loading.value = true;
  try {
    const { data } = await templateApi.list();
    templates.value = data;
  } catch {
    toast.error("加载模板失败");
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  loadTemplates();
});
</script>