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
        <h2 class="text-[var(--text-page-title)] font-medium text-[var(--color-ink)]">新建数据库</h2>
        <button type="button" class="ui-btn-ghost p-1" @click="emit('update:open', false)">
          <X :size="18" />
        </button>
      </div>

      <form class="flex flex-col gap-4" @submit.prevent="onSubmit">
        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">
            数据库标识 (code) <span class="text-red-500">*</span>
          </label>
          <input
            v-model="form.code"
            class="ui-input w-full"
            placeholder="如：finance, hr, auto_repair"
            :pattern="CODE_PATTERN"
            :title="`code 必须以小写字母开头，仅包含小写字母、数字和下划线（2-${MAX_CODE_LEN} 字符）`"
            required
            data-testid="catalog-code-input"
          />
          <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mt-1">
            小写字母开头，仅含 [a-z0-9_]
          </p>
        </div>

        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">
            名称 <span class="text-red-500">*</span>
          </label>
          <input
            v-model="form.name"
            class="ui-input w-full"
            placeholder="如：财务数据库"
            required
            data-testid="catalog-name-input"
          />
        </div>

        <div>
          <label class="block text-[var(--text-small)] text-[var(--color-ink-secondary)] mb-1">
            描述（可选）
          </label>
          <textarea
            v-model="form.description"
            class="ui-input w-full resize-none"
            rows="2"
            placeholder="一句话说明"
          />
        </div>

        <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)]">
          实体类型无需预设，上传数据集后会自动发现并聚合。
        </p>

        <p v-if="errorMessage" class="text-[var(--text-small)] text-red-600" data-testid="catalog-error">
          {{ errorMessage }}
        </p>

        <div class="flex justify-end gap-2 mt-2">
          <button type="button" class="ui-btn-ghost px-4 py-2" @click="emit('update:open', false)">
            取消
          </button>
          <button
            type="submit"
            class="ui-btn-primary px-4 py-2 flex items-center gap-1.5"
            :disabled="!canSubmit || submitting"
            data-testid="catalog-submit"
          >
            <Loader2 v-if="submitting" :size="14" class="animate-spin" />
            <Plus v-else :size="14" />
            {{ submitting ? "创建中..." : "创建" }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { Loader2, Plus, X } from "lucide-vue-next";
import type { CatalogCreate } from "@/services/catalog";

/**
 * REQ-054 review fix: 新建数据库对话框（简化版）。
 *
 * 复查反馈 #1：原 dialog 字段过多（entity_types / icon / color）。
 * 简化为只保留 code + name + description（可选）：
 * - entity_types 不再预设，后端默认空数组，上传数据集后动态发现。
 * - icon / color 由后端默认值处理。
 *
 * 客户端校验：
 * - code: 正则 `^[a-z][a-z0-9_]*$`，长度 2-50（与后端 pydantic 一致）。
 * - name: 非空。
 * 提交成功 emit("submit", req)；失败由父组件 toast 处理，本地只展示 message。
 */

const CODE_PATTERN = "^[a-z][a-z0-9_]*$";
const MAX_CODE_LEN = 50;
const MIN_CODE_LEN = 2;

export interface CatalogCreateForm {
  code: string;
  name: string;
  description: string;
}

const props = defineProps<{
  open: boolean;
  submitting?: boolean;
}>();

const emit = defineEmits<{
  "update:open": [val: boolean];
  submit: [req: CatalogCreate];
}>();

// --- Local form state ---
const empty = (): CatalogCreateForm => ({
  code: "",
  name: "",
  description: "",
});

const form = reactive<CatalogCreateForm>(empty());
const errorMessage = ref("");

// Reset form whenever dialog opens
watch(
  () => props.open,
  (open) => {
    if (open) {
      Object.assign(form, empty());
      errorMessage.value = "";
    }
  },
);

const canSubmit = computed(() => {
  const code = form.code.trim();
  if (code.length < MIN_CODE_LEN || code.length > MAX_CODE_LEN) return false;
  if (!new RegExp(CODE_PATTERN).test(code)) return false;
  if (!form.name.trim()) return false;
  return true;
});

function onSubmit() {
  if (!canSubmit.value) {
    errorMessage.value = "请检查表单：code 仅含小写字母/数字/下划线，名称非空";
    return;
  }
  errorMessage.value = "";

  const req: CatalogCreate = {
    code: form.code.trim(),
    name: form.name.trim(),
  };
  if (form.description.trim()) req.description = form.description.trim();

  emit("submit", req);
}
</script>
