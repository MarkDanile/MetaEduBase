<template>
  <div class="w-[240px] flex-shrink-0 ui-panel p-3 flex flex-col gap-2">
    <div class="flex items-center justify-between mb-1">
      <span class="text-[var(--text-caption)] font-medium text-[var(--color-ink)]">文件夹</span>
      <button
        v-if="!showNewFolderInput"
        class="ui-btn-ghost text-[var(--text-small)] px-2 py-0.5"
        @click="emit('toggle-new-folder', true)"
      >
        <Plus :size="14" />
      </button>
    </div>

    <!-- Inline new folder input -->
    <div v-if="showNewFolderInput" class="flex gap-1">
      <input
        :value="newFolderName"
        class="ui-input text-[var(--text-small)] py-0.5 px-2 flex-1"
        placeholder="文件夹名称"
        @keyup.enter="emit('create-folder')"
        @keyup.escape="emit('toggle-new-folder', false); emit('update:new-folder-name', '')"
        @input="emit('update:new-folder-name', ($event.target as HTMLInputElement).value)"
      />
      <button class="ui-btn-primary text-[var(--text-small)] px-2 py-0.5" @click="emit('create-folder')">
        <Check :size="14" />
      </button>
      <button class="ui-btn-ghost text-[var(--text-small)] px-1 py-0.5" @click="emit('toggle-new-folder', false); emit('update:new-folder-name', '')">
        <X :size="14" />
      </button>
    </div>

    <LoadingSpinner v-if="loading" text="加载中..." />
    <div v-else class="flex-1 overflow-auto space-y-0.5">
      <!-- "全部文件" as virtual root — always first, visually a section header -->
      <button
        class="w-full text-left px-2 py-1.5 rounded-lg text-[var(--text-caption)] font-medium transition-colors flex items-center gap-1.5 border-none bg-none cursor-pointer mb-0.5"
        :class="!selectedId
          ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
          : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-ink-secondary)]'"
        style="padding-left: 8px"
        @click="emit('select', null)"
      >
        <FolderOpen :size="14" class="flex-shrink-0" />
        <span>全部文件</span>
      </button>
      <!-- Folder tree — all indented 8px more than 全部文件 -->
      <div v-for="folder in folders" :key="folder.id" class="relative group">
        <!-- Inline rename input -->
        <div
          v-if="inlineRenamingFolderId === folder.id"
          class="flex items-center gap-1"
          :style="{ paddingLeft: `${16 + folder.depth * 16}px` }"
        >
          <Folder :size="14" class="flex-shrink-0 text-[var(--color-accent)]" />
          <input
            :value="inlineRenamingName"
            class="ui-input text-[var(--text-small)] py-0.5 px-1 flex-1"
            @keyup.enter="emit('commit-rename')"
            @keyup.escape="emit('cancel-rename')"
            @input="emit('update:inline-renaming-name', ($event.target as HTMLInputElement).value)"
            @click.stop
          />
          <button class="ui-btn-ghost p-0.5" @click.stop="emit('commit-rename')"><Check :size="12" /></button>
          <button class="ui-btn-ghost p-0.5" @click.stop="emit('cancel-rename')"><X :size="12" /></button>
        </div>
        <!-- Normal folder row -->
        <button
          v-else
          class="w-full text-left px-2 py-1 rounded-lg text-[var(--text-small)] transition-colors flex items-center gap-1 border-none bg-none cursor-pointer"
          :class="selectedId === folder.id
            ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
            : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-ink)]'"
          :style="{ paddingLeft: `${16 + folder.depth * 16}px` }"
          @click="emit('select', folder.id)"
        >
          <Folder :size="12" class="flex-shrink-0" />
          <span class="truncate flex-1">{{ folder.name }}</span>
        </button>
        <!-- Three-dot menu for each folder -->
        <button
          v-if="inlineRenamingFolderId !== folder.id"
          class="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 ui-btn-ghost p-0.5 rounded"
          style="transform: translateY(-50%)"
          @click.stop="emit('toggle-menu', folder.id)"
        >
          <MoreHorizontal :size="10" />
        </button>
        <!-- Inline dropdown menu -->
        <div
          v-if="activeFolderMenu === folder.id"
          class="absolute right-0 top-full z-10 mt-1 py-1 rounded-lg ui-panel shadow-lg border border-[var(--color-border)] min-w-[80px]"
          @click.stop
        >
          <button
            class="w-full text-left px-3 py-1 text-[var(--text-micro)] hover:bg-[var(--color-bg-hover)] flex items-center gap-2"
            @click="emit('start-rename', folder)"
          >
            <Pencil :size="10" /> 重命名
          </button>
          <button
            class="w-full text-left px-3 py-1 text-[var(--text-micro)] hover:bg-[var(--color-bg-hover)] text-red-500 flex items-center gap-2"
            @click="emit('confirm-delete', folder)"
          >
            <Trash2 :size="10" /> 删除
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Plus, Folder, FolderOpen, Check, X, MoreHorizontal, Pencil, Trash2 } from "lucide-vue-next";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import type { FolderDTO } from "@/services/document";

export type FolderWithDepth = FolderDTO & { depth: number };

defineProps<{
  folders: FolderWithDepth[];
  loading: boolean;
  selectedId: string | null;
  showNewFolderInput: boolean;
  newFolderName: string;
  activeFolderMenu: string | null;
  inlineRenamingFolderId: string | null;
  inlineRenamingName: string;
}>();

const emit = defineEmits<{
  "select": [id: string | null];
  "toggle-menu": [id: string];
  "start-rename": [folder: FolderWithDepth];
  "commit-rename": [];
  "cancel-rename": [];
  "confirm-delete": [folder: FolderWithDepth];
  "create-folder": [];
  "toggle-new-folder": [open: boolean];
  "update:new-folder-name": [val: string];
  "update:inline-renaming-name": [val: string];
}>();
</script>
