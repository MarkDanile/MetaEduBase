<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader title="资源库" subtitle="文档管理与处理" />

    <div class="flex gap-4 mt-4" style="min-height: calc(100vh - 200px)">
      <FolderTreePanel
        :folders="flatFolders"
        :loading="loadingFolders"
        :selected-id="selectedFolderId"
        :show-new-folder-input="showNewFolderInput"
        :new-folder-name="newFolderName"
        :active-folder-menu="activeFolderMenu"
        :inline-renaming-folder-id="inlineRenamingFolderId"
        :inline-renaming-name="inlineRenamingName"
        @select="selectFolder"
        @toggle-menu="toggleFolderMenu"
        @start-rename="startRenameFolder"
        @commit-rename="commitRename"
        @cancel-rename="inlineRenamingFolderId = null"
        @confirm-delete="confirmDeleteFolder"
        @create-folder="createFolder"
        @toggle-new-folder="(open) => (showNewFolderInput = open)"
        @update:new-folder-name="(v) => (newFolderName = v)"
        @update:inline-renaming-name="(v) => (inlineRenamingName = v)"
      />

      <FileListPanel
        :files="files"
        :loading="loadingFiles"
        :is-dragging="isDragging"
        :filter-status="filterStatus"
        @set-dragging="(v) => (isDragging = v)"
        @file-change="handleFileSelect"
        @drop="handleDrop"
        @update:filter-status="(v) => (filterStatus = v)"
        @refresh="loadFiles"
        @go-to-detail="goToDetail"
        @confirm-delete="confirmDeleteFile"
      />
    </div>

    <UploadOptionsDialog
      :open="showUploadDialog"
      :doc-type="uploadDocType"
      :tags="uploadTags"
      @update:open="(v) => (showUploadDialog = v)"
      @update:doc-type="(v) => (uploadDocType = v)"
      @update:tags="(v) => (uploadTags = v)"
      @confirm="doUpload"
    />

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
import PageHeader from "@/components/PageHeader.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import { useToast } from "@/composables/useToast";
import { documentApi, type FolderDTO } from "@/services/document";
import FolderTreePanel, { type FolderWithDepth } from "@/views/resource/FolderTreePanel.vue";
import FileListPanel from "@/views/resource/FileListPanel.vue";
import UploadOptionsDialog from "@/views/resource/UploadOptionsDialog.vue";

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

const flatFolders = computed<FolderWithDepth[]>(() => {
  const result: FolderWithDepth[] = [];
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
const files = ref<import("@/services/document").FileDTO[]>([]);
const loadingFiles = ref(false);
const filterStatus = ref("");
const showDeleteDialog = ref(false);
const deleteTarget = ref<import("@/services/document").FileDTO | null>(null);

// --- Upload state ---
const isDragging = ref(false);
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

function startRenameFolder(folder: FolderWithDepth) {
  inlineRenamingFolderId.value = folder.id;
  inlineRenamingName.value = folder.name;
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

function confirmDeleteFolder(folder: FolderWithDepth) {
  if (confirm(`确定删除文件夹「${folder.name}」？`)) {
    doDeleteFolder(folder.id);
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

function confirmDeleteFile(file: import("@/services/document").FileDTO) {
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
// Note: fileInput ref lives inside FileListPanel (its <input type="file">
// is in the child template). The click on the upload area triggers
// FileListPanel's onTriggerUpload, which calls fileInput.click() inside
// the child. The parent only orchestrates the resulting onChange / drop
// events.

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
  await loadFiles();
}

// --- Init ---
onMounted(() => {
  loadFolders();
  loadFiles();
});
</script>
