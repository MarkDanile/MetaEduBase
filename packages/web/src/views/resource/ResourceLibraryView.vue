<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader title="资源库" subtitle="文档管理与处理" />

    <div class="flex gap-4 mt-4" style="min-height: calc(100vh - 200px)">
      <!-- Left: Folder tree -->
      <div class="w-[240px] flex-shrink-0 ui-panel p-3 flex flex-col gap-2">
        <div class="flex items-center justify-between mb-1">
          <span class="text-[var(--text-caption)] font-medium text-[var(--color-ink)]">文件夹</span>
          <button
            v-if="!showNewFolderInput"
            class="liquid-btn-ghost text-[var(--text-small)] px-2 py-0.5"
            @click="showNewFolderInput = true"
          >
            <Plus :size="14" /> 
          </button>
        </div>

        <!-- Inline new folder input -->
        <div v-if="showNewFolderInput" class="flex gap-1">
          <input
            v-model="newFolderName"
            class="liquid-input text-[var(--text-small)] py-0.5 px-2 flex-1"
            placeholder="文件夹名称"
            @keyup.enter="createFolder"
            @keyup.escape="showNewFolderInput = false; newFolderName = ''"
          />
          <button class="liquid-btn-primary text-[var(--text-small)] px-2 py-0.5" @click="createFolder">
            <Check :size="14" />
          </button>
          <button class="liquid-btn-ghost text-[var(--text-small)] px-1 py-0.5" @click="showNewFolderInput = false; newFolderName = ''">
            <X :size="14" />
          </button>
        </div>

        <LoadingSpinner v-if="loadingFolders" text="加载中..." />
        <div v-else class="flex-1 overflow-auto space-y-0.5">
          <!-- "全部文件" as virtual root — always first, visually a section header -->
          <button
            class="w-full text-left px-2 py-1.5 rounded-lg text-[var(--text-caption)] font-medium transition-colors flex items-center gap-1.5 border-none bg-none cursor-pointer mb-0.5"
            :class="!selectedFolderId
              ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
              : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-ink-secondary)]'"
            style="padding-left: 8px"
            @click="selectFolder(null)"
          >
            <FolderOpen :size="14" class="flex-shrink-0" />
            <span>全部文件</span>
          </button>
          <!-- Folder tree — all indented 8px more than 全部文件 -->
          <div v-for="folder in flatFolders" :key="folder.id" class="relative group">
            <!-- Inline rename input -->
            <div
              v-if="inlineRenamingFolderId === folder.id"
              class="flex items-center gap-1"
              :style="{ paddingLeft: `${16 + folder.depth * 16}px` }"
            >
              <Folder :size="14" class="flex-shrink-0 text-[var(--color-accent)]" />
              <input
                v-model="inlineRenamingName"
                class="liquid-input text-[var(--text-small)] py-0.5 px-1 flex-1"
                @keyup.enter="commitRename"
                @keyup.escape="inlineRenamingFolderId = null"
                @click.stop
              />
              <button class="liquid-btn-ghost p-0.5" @click.stop="commitRename"><Check :size="12" /></button>
              <button class="liquid-btn-ghost p-0.5" @click.stop="inlineRenamingFolderId = null"><X :size="12" /></button>
            </div>
            <!-- Normal folder row -->
            <button
              v-else
              class="w-full text-left px-2 py-1 rounded-lg text-[var(--text-small)] transition-colors flex items-center gap-1 border-none bg-none cursor-pointer"
              :class="selectedFolderId === folder.id
                ? 'bg-[var(--color-accent-bg)] text-[var(--color-accent)]'
                : 'hover:bg-[var(--color-bg-hover)] text-[var(--color-ink)]'"
              :style="{ paddingLeft: `${16 + folder.depth * 16}px` }"
              @click="selectFolder(folder.id)"
            >
              <Folder :size="12" class="flex-shrink-0" />
              <span class="truncate flex-1">{{ folder.name }}</span>
            </button>
            <!-- Three-dot menu for each folder -->
            <button
              v-if="inlineRenamingFolderId !== folder.id"
              class="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 liquid-btn-ghost p-0.5 rounded"
              style="transform: translateY(-50%)"
              @click.stop="toggleFolderMenu(folder.id)"
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
                @click="startRenameFolder(folder)"
              >
                <Pencil :size="10" /> 重命名
              </button>
              <button
                class="w-full text-left px-3 py-1 text-[var(--text-micro)] hover:bg-[var(--color-bg-hover)] text-red-500 flex items-center gap-2"
                @click="confirmDeleteFolder(folder)"
              >
                <Trash2 :size="10" /> 删除
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: File list -->
      <div class="flex-1 ui-panel p-4 flex flex-col gap-3">
        <!-- Upload area -->
        <div
          class="border-2 border-dashed border-[var(--color-border)] rounded-xl p-4 text-center transition-colors cursor-pointer"
          :class="isDragging ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)]' : 'hover:border-[var(--color-ink-tertiary)]'"
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop.prevent="handleDrop"
          @click="triggerUpload"
        >
          <Upload :size="20" class="mx-auto mb-1 text-[var(--color-ink-tertiary)]" />
          <p class="text-[var(--text-caption)] text-[var(--color-ink-secondary)]">
            拖拽文件到此处上传，或点击选择文件
          </p>
        </div>
        <input ref="fileInput" type="file" class="hidden" multiple @change="handleFileSelect" />

        <!-- Filter bar -->
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">筛选:</span>
          <select
            v-model="filterStatus"
            class="liquid-input text-[var(--text-small)] py-1 px-2 rounded"
          >
            <option value="">全部状态</option>
            <option value="uploaded">已上传</option>
            <option value="processing">处理中</option>
            <option value="processed">已完成</option>
            <option value="failed">失败</option>
          </select>
          <button class="liquid-btn-ghost text-[var(--text-small)] px-2 py-1" @click="loadFiles">
            <RefreshCw :size="14" :class="{ 'animate-spin': loadingFiles }" />
          </button>
        </div>

        <!-- File table -->
        <LoadingSpinner v-if="loadingFiles" text="加载文件..." />
        <EmptyState v-else-if="files.length === 0" title="暂无文件" hint="上传文档开始处理" />
        <div v-else class="overflow-auto flex-1">
          <table class="w-full text-[var(--text-caption)]">
            <thead>
              <tr class="border-b border-[var(--color-border)] text-[var(--text-small)] text-[var(--color-ink-tertiary)]">
                <th class="text-left py-2 px-2 font-medium w-10">序号</th>
                <th class="text-left py-2 px-2 font-medium">文件名</th>
                <th class="text-left py-2 px-2 font-medium">类型</th>
                <th class="text-left py-2 px-2 font-medium">状态</th>
                <th class="text-left py-2 px-2 font-medium">上传人</th>
                <th class="text-left py-2 px-2 font-medium">大小</th>
                <th class="text-left py-2 px-2 font-medium">上传时间</th>
                <th class="text-right py-2 px-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(file, idx) in files"
                :key="file.id"
                class="border-b border-[var(--color-border)] hover:bg-[var(--color-bg-hover)] cursor-pointer transition-colors"
                @click="goToDetail(file.id)"
              >
                <td class="py-2.5 px-2 text-[var(--color-ink-tertiary)]">{{ idx + 1 }}</td>
                <td class="py-2.5 px-2">
                  <div class="flex items-center gap-2">
                    <FileText :size="14" class="text-[var(--color-ink-tertiary)] flex-shrink-0" />
                    <span class="truncate max-w-[200px]">{{ file.filename }}</span>
                  </div>
                </td>
                <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ file.doc_type || file.file_type }}</td>
                <td class="py-2.5 px-2">
                  <span :class="statusTagClass(file.status)">{{ statusLabel(file.status) }}</span>
                </td>
                <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ file.uploaded_by_name || file.uploaded_by || '-' }}</td>
                <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ formatSize(file.file_size) }}</td>
                <td class="py-2.5 px-2 text-[var(--color-ink-secondary)]">{{ formatDate(file.created_at) }}</td>
                <td class="py-2.5 px-2 text-right" @click.stop>
                  <button class="liquid-btn-ghost px-2 py-1" @click="goToDetail(file.id)">
                    <Eye :size="14" />
                  </button>
                  <button class="liquid-btn-ghost px-2 py-1 text-red-500" @click="confirmDeleteFile(file)">
                    <Trash2 :size="14" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Upload options dialog -->
    <ConfirmDialog
      v-model:open="showUploadDialog"
      title="上传文件"
      :show-cancel="true"
      confirm-text="上传"
      @confirm="doUpload"
    >
      <div class="space-y-3 mt-2">
        <div>
          <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">文档类型</label>
          <select v-model="uploadDocType" class="liquid-input w-full mt-1">
            <option value="">不选择</option>
            <option v-for="opt in DOC_TYPE_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <div>
          <label class="text-[var(--text-small)] text-[var(--color-ink-tertiary)]">标签（逗号分隔）</label>
          <input v-model="uploadTags" class="liquid-input w-full mt-1" placeholder="如: 教案, 期末考试" />
        </div>
      </div>
    </ConfirmDialog>

    <!-- Delete file dialog -->
    <ConfirmDialog
      v-model:open="showDeleteDialog"
      title="删除文件"
      :message="`确定删除文件「${deleteTarget?.filename}」？此操作不可恢复。`"
      @confirm="doDeleteFile"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useRouter } from "vue-router";
import {
  Plus, Folder, FolderOpen, FileText, Upload, Pencil, Trash2, Eye, RefreshCw, Check, X,
  MoreHorizontal,
} from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useToast } from "@/composables/useToast";
import { documentApi, type FolderDTO, type FileDTO } from "@/services/document";
import { FILE_STATUS_MAP, DOC_TYPE_OPTIONS } from "@/constants/pipeline";

const router = useRouter();
const toast = useToast();

// --- Folder state ---
const folders = ref<FolderDTO[]>([]);
const loadingFolders = ref(true);
const selectedFolderId = ref<string | null>(null);
const showNewFolderInput = ref(false);
const newFolderName = ref("");
const activeFolderMenu = ref<string | null>(null);
const inlineRenamingFolderId = ref<string | null>(null);
const inlineRenamingName = ref("");

const flatFolders = computed(() => {
  const result: (FolderDTO & { depth: number })[] = [];
  function walk(nodes: FolderDTO[], depth: number) {
    for (const node of nodes) {
      result.push({ ...node, depth });
      if (node.children?.length) walk(node.children, depth + 1);
    }
  }
  walk(folders.value, 0);
  return result;
});

// --- File state ---
const files = ref<FileDTO[]>([]);
const loadingFiles = ref(false);
const filterStatus = ref("");
const showDeleteDialog = ref(false);
const deleteTarget = ref<FileDTO | null>(null);

// --- Upload state ---
const isDragging = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const pendingFiles = ref<File[]>([]);
const showUploadDialog = ref(false);
const uploadDocType = ref("");
const uploadTags = ref("");

// --- Folder actions ---
async function loadFolders() {
  loadingFolders.value = true;
  try {
    const { data } = await documentApi.listFolders();
    folders.value = data;
  } catch {
    toast.error("加载文件夹失败");
  } finally {
    loadingFolders.value = false;
  }
}

function selectFolder(id: string | null) {
  selectedFolderId.value = id;
  activeFolderMenu.value = null;
  inlineRenamingFolderId.value = null;
  loadFiles();
}

function toggleFolderMenu(id: string) {
  activeFolderMenu.value = activeFolderMenu.value === id ? null : id;
}

async function createFolder() {
  if (!newFolderName.value.trim()) return;
  try {
    await documentApi.createFolder({
      name: newFolderName.value.trim(),
      parent_id: selectedFolderId.value ?? undefined,
    });
    toast.success("文件夹已创建");
    newFolderName.value = "";
    showNewFolderInput.value = false;
    await loadFolders();
  } catch {
    toast.error("创建失败");
  }
}

function startRenameFolder(folder?: FolderDTO & { depth: number }) {
  const target = folder ?? flatFolders.value.find((f) => f.id === selectedFolderId.value);
  if (!target) return;
  inlineRenamingFolderId.value = target.id;
  inlineRenamingName.value = target.name;
  activeFolderMenu.value = null;
}

async function commitRename() {
  const id = inlineRenamingFolderId.value;
  if (!id || !inlineRenamingName.value.trim()) {
    inlineRenamingFolderId.value = null;
    return;
  }
  try {
    await documentApi.updateFolder(id, { name: inlineRenamingName.value.trim() });
    toast.success("已重命名");
    inlineRenamingFolderId.value = null;
    await loadFolders();
  } catch {
    toast.error("重命名失败");
  }
}

function confirmDeleteFolder(folder?: FolderDTO & { depth: number }) {
  const target = folder ?? flatFolders.value.find((f) => f.id === selectedFolderId.value);
  if (!target) return;
  if (confirm(`确定删除文件夹「${target.name}」？`)) {
    doDeleteFolder(target.id);
  }
}

async function doDeleteFolder(id?: string) {
  const fid = id ?? selectedFolderId.value;
  if (!fid) return;
  try {
    await documentApi.deleteFolder(fid);
    toast.success("文件夹已删除");
    selectedFolderId.value = null;
    activeFolderMenu.value = null;
    await loadFolders();
    await loadFiles();
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "删除失败";
    toast.error(msg);
  }
}

// --- File actions ---
async function loadFiles() {
  loadingFiles.value = true;
  try {
    const { data } = await documentApi.listFiles({
      folder_id: selectedFolderId.value ?? undefined,
      status: filterStatus.value || undefined,
      limit: 100,
    });
    files.value = data;
  } catch {
    toast.error("加载文件失败");
  } finally {
    loadingFiles.value = false;
  }
}

function goToDetail(id: string) {
  router.push(`/resource/${id}`);
}

function confirmDeleteFile(file: FileDTO) {
  deleteTarget.value = file;
  showDeleteDialog.value = true;
}

async function doDeleteFile() {
  if (!deleteTarget.value) return;
  try {
    await documentApi.deleteFile(deleteTarget.value.id);
    toast.success("文件已删除");
    deleteTarget.value = null;
    showDeleteDialog.value = false;
    await loadFiles();
  } catch {
    toast.error("删除失败");
  }
}

// --- Upload actions ---
function triggerUpload() {
  fileInput.value?.click();
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files?.length) {
    pendingFiles.value = Array.from(input.files);
    showUploadDialog.value = true;
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false;
  if (e.dataTransfer?.files.length) {
    pendingFiles.value = Array.from(e.dataTransfer.files);
    showUploadDialog.value = true;
  }
}

async function doUpload() {
  for (const file of pendingFiles.value) {
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (selectedFolderId.value) formData.append("folder_id", selectedFolderId.value);
      if (uploadDocType.value) formData.append("doc_type", uploadDocType.value);
      const tags = uploadTags.value.split(",").map((t) => t.trim()).filter(Boolean);
      for (const tag of tags) {
        formData.append("tags", tag);
      }
      await documentApi.uploadFile(formData);
      toast.success(`${file.name} 上传成功`);
    } catch {
      toast.error(`${file.name} 上传失败`);
    }
  }
  pendingFiles.value = [];
  uploadDocType.value = "";
  uploadTags.value = "";
  showUploadDialog.value = false;
  if (fileInput.value) fileInput.value.value = "";
  await loadFiles();
}

// --- Helpers ---
function statusLabel(status: string) {
  return FILE_STATUS_MAP[status]?.label ?? status;
}

function statusTagClass(status: string) {
  const color = FILE_STATUS_MAP[status]?.color ?? "blue";
  return `liquid-tag-${color} text-[var(--text-micro)]`;
}

function formatSize(bytes: number | null) {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// --- Init ---
onMounted(() => {
  loadFolders();
  loadFiles();
});
</script>
