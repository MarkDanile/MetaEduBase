<template>
  <div
    v-if="open"
    class="fixed inset-0 z-[var(--z-dialog)] flex items-center justify-center"
    role="dialog"
    aria-modal="true"
    @keydown.escape="emit('update:open', false)"
  >
    <div class="absolute inset-0 bg-black/50" @click="emit('update:open', false)" />
    <div class="relative ui-panel p-6 w-[480px]">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-[var(--text-page-title)] font-medium text-[var(--color-ink)]">上传数据集</h2>
        <button class="ui-btn-ghost p-1" @click="emit('update:open', false)">
          <X :size="18" />
        </button>
      </div>

      <div class="flex flex-col gap-4">
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">
            所属数据库 <span class="text-red-500">*</span>
          </label>
          <select
            :value="form.catalog_id"
            class="ui-input w-full"
            data-testid="upload-catalog-select"
            :disabled="lockedCatalogId !== null"
            @change="onCatalogChange(($event.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>请选择数据库</option>
            <option
              v-for="c in catalogs"
              :key="c.id"
              :value="c.id"
            >
              {{ c.name }} ({{ c.code }})
            </option>
          </select>
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">
            实体类型 <span class="text-red-500">*</span>
          </label>
          <select
            :value="form.entity_type"
            class="ui-input w-full"
            data-testid="upload-entity-type-select"
            :disabled="!form.catalog_id || availableEntityTypes.length === 0"
          >
            <option value="" disabled>
              {{ availableEntityTypes.length === 0 ? "请先选择数据库" : "请选择实体类型" }}
            </option>
            <option
              v-for="t in availableEntityTypes"
              :key="t"
              :value="t"
            >
              {{ t }}
            </option>
          </select>
          <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-1">
            仅显示所选数据库的白名单 entity_types
          </p>
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">
            数据集名称 <span class="text-red-500">*</span>
          </label>
          <input
            :value="form.name"
            class="ui-input w-full"
            placeholder="输入数据集名称"
            @input="emit('update:form', { ...form, name: ($event.target as HTMLInputElement).value })"
          />
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">描述（可选）</label>
          <textarea
            :value="form.description"
            class="ui-input w-full resize-none"
            rows="2"
            placeholder="输入描述"
            @input="emit('update:form', { ...form, description: ($event.target as HTMLTextAreaElement).value })"
          />
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">标签（可选，多个用逗号分隔）</label>
          <input
            :value="form.tags"
            class="ui-input w-full"
            placeholder="如：汽车维修，数据分析"
            @input="emit('update:form', { ...form, tags: ($event.target as HTMLInputElement).value })"
          />
        </div>
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">选择文件</label>
          <div
            class="border-2 border-dashed border-[var(--color-border)] rounded-lg p-6 text-center cursor-pointer hover:border-[var(--color-accent)] transition-colors"
            :class="{ 'border-[var(--color-accent)]': form.file }"
            @click="triggerFileInput"
          >
            <FileSpreadsheet :size="24" class="mx-auto mb-2 text-[var(--color-ink-tertiary)]" />
            <p class="text-[var(--text-caption)] text-[var(--color-ink-secondary)]">
              {{ form.file ? form.file.name : "点击选择 Excel 文件" }}
            </p>
            <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-1">支持 .xlsx, .xls, .csv</p>
          </div>
          <input
            ref="fileInputRef"
            type="file"
            accept=".xlsx,.xls,.csv"
            class="hidden"
            @change="emit('file-change', $event)"
          />
        </div>
        <p v-if="errorMessage" class="text-[var(--text-small)] text-red-600" data-testid="upload-error">
          {{ errorMessage }}
        </p>
        <div class="flex justify-end gap-2 mt-2">
          <button class="ui-btn-ghost px-4 py-2" @click="emit('update:open', false)">取消</button>
          <button
            class="ui-btn-primary px-4 py-2 flex items-center gap-1.5"
            :disabled="!canUpload || uploading"
            data-testid="upload-submit"
            @click="emit('upload')"
          >
            <LoadingSpinner v-if="uploading" :size="14" />
            <Upload v-else :size="14" />
            {{ uploading ? "上传中..." : "上传" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * REQ-052 + REQ-054 Task 8: 数据集上传对话框。
 *
 * REQ-054 改造：
 * - 加 数据库 select（catalogs 列表从 store 加载）。
 * - 加 entity_type select（按所选数据库白名单过滤）。
 * - `preSelectedCatalogId` prop 支持 CatalogDetailPage 预选锁定。
 * - 上传时 FormData 必带 `catalog_id` + `entity_type`（父组件负责）。
 */
import { computed, ref, watch } from "vue";
import { Upload, FileSpreadsheet, X } from "lucide-vue-next";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import { useCatalogStore } from "@/stores/catalog";

export interface UploadForm {
  name: string;
  description: string;
  tags: string;
  file: File | null;
  catalog_id: string;
  entity_type: string;
}

const props = defineProps<{
  open: boolean;
  form: UploadForm;
  uploading: boolean;
  preSelectedCatalogId?: string | null;
}>();

const emit = defineEmits<{
  "update:open": [val: boolean];
  "update:form": [form: UploadForm];
  "upload": [];
  "file-change": [e: Event];
}>();

const catalogStore = useCatalogStore();
const catalogs = computed(() => catalogStore.catalogs);
const lockedCatalogId = computed(() => props.preSelectedCatalogId ?? null);

const errorMessage = ref("");

const availableEntityTypes = computed(() => {
  const current = catalogs.value.find((c) => c.id === props.form.catalog_id);
  return current?.entity_types ?? [];
});

function onCatalogChange(catalogId: string) {
  emit("update:form", { ...props.form, catalog_id: catalogId, entity_type: "" });
}

// When dialog opens with a locked catalog, sync the form
watch(
  () => props.open,
  (open) => {
    if (open) {
      errorMessage.value = "";
      if (lockedCatalogId.value && props.form.catalog_id !== lockedCatalogId.value) {
        emit("update:form", {
          ...props.form,
          catalog_id: lockedCatalogId.value,
          entity_type: "",
        });
      }
    }
  },
);

const canUpload = computed(
  () =>
    props.form.catalog_id.trim() !== "" &&
    props.form.entity_type.trim() !== "" &&
    props.form.name.trim() !== "" &&
    props.form.file !== null,
);

// Show a soft validation warning when required fields empty
watch(
  () => [props.form.catalog_id, props.form.entity_type, props.form.name, props.form.file],
  () => {
    if (!props.form.catalog_id) {
      errorMessage.value = "请先选择数据库";
    } else if (!props.form.entity_type) {
      errorMessage.value = "请选择实体类型";
    } else {
      errorMessage.value = "";
    }
  },
);

const fileInputRef = ref<HTMLInputElement | null>(null);
function triggerFileInput() {
  fileInputRef.value?.click();
}
</script>
