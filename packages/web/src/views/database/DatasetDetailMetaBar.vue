<template>
  <div class="ui-panel p-4 mb-4 flex flex-wrap items-center gap-4">
    <div class="flex items-center gap-2">
      <FileSpreadsheet :size="18" class="text-[var(--color-accent)]" />
      <span class="text-[var(--text-body)] font-medium text-[var(--color-ink)]">{{ selected.name }}</span>
    </div>
    <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
      {{ selected.row_count }} 行 × {{ selected.column_names?.length ?? 0 }} 列
    </span>
    <div v-if="selected.tags?.length" class="flex gap-1">
      <span v-for="tag in selected.tags" :key="tag" class="ui-tag-purple text-[var(--text-micro)]">{{ tag }}</span>
    </div>

    <!-- REQ-054 bugfix: inline edit entity_type for the selected dataset.
         Lets legacy datasets (entity_type NULL pre-migration-019) be tagged
         without re-upload, so the semantic tab + 问数 entity_type dropdown
         can aggregate them. -->
    <div class="flex items-center gap-1.5" data-testid="entity-type-editor">
      <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">实体类型:</span>
      <span
        v-if="!editing"
        class="text-[var(--text-small)] font-medium text-[var(--color-ink)]"
        data-testid="entity-type-display"
      >
        {{ selected.entity_type || '未指定' }}
      </span>
      <button
        v-if="!editing"
        type="button"
        class="ui-btn-ghost px-2 py-1 flex items-center gap-1"
        data-testid="edit-entity-type-btn"
        @click="startEdit"
      >
        <Pencil :size="12" /> 编辑
      </button>
      <div v-else class="flex items-center gap-1">
        <input
          v-model="draft"
          class="border border-[var(--color-border)] rounded px-2 py-1 bg-[var(--color-bg)] text-[var(--color-ink)] text-sm w-40"
          data-testid="entity-type-input"
          @keyup.enter="save"
          @keyup.esc="cancel"
        />
        <button
          type="button"
          class="ui-btn-primary px-2 py-1 text-sm"
          data-testid="save-entity-type-btn"
          @click="save"
        >
          保存
        </button>
        <button
          type="button"
          class="ui-btn-ghost px-2 py-1 text-sm"
          data-testid="cancel-entity-type-btn"
          @click="cancel"
        >
          取消
        </button>
      </div>
    </div>

    <button
      class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5 text-red-500 ml-auto"
      @click="emit('delete')"
    >
      <Trash2 :size="14" /> 删除
    </button>
    <button
      class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5"
      @click="emit('reinitialize')"
    >
      <RefreshCw :size="14" /> 重新初始化
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { FileSpreadsheet, Pencil, Trash2, RefreshCw } from "lucide-vue-next";
import type { DatasetDTO } from "@/services/structured-data";

const props = defineProps<{
  selected: DatasetDTO;
}>();

const emit = defineEmits<{
  "delete": [];
  "reinitialize": [];
  "update-entity-type": [value: string];
}>();

// REQ-054 bugfix: inline entity_type edit state.
const editing = ref(false);
const draft = ref("");

// Reset edit mode when the selected dataset changes.
watch(
  () => props.selected.id,
  () => {
    editing.value = false;
  },
);

function startEdit() {
  draft.value = props.selected.entity_type ?? "";
  editing.value = true;
}

function save() {
  const trimmed = draft.value.trim();
  // Empty entity_type is rejected: backend cannot clear to NULL either
  // (DatasetRepository.update skips None), and an empty entity_type has no
  // semantic value for routing/aggregation.
  if (!trimmed) return;
  emit("update-entity-type", trimmed);
  editing.value = false;
}

function cancel() {
  editing.value = false;
}
</script>
