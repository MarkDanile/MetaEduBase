<template>
  <div class="p-[var(--spacing-page)] max-w-[1000px] mx-auto">
    <div class="flex items-start justify-between mb-[var(--spacing-page)] animate-slide-up">
      <PageHeader title="校本资源" subtitle="教学资源上传、解析与管理" />
      <button @click="showUploadDialog = true" class="ui-btn ui-btn-primary flex-shrink-0">
        <Upload :size="16" :stroke-width="2" />
        上传资源
      </button>
    </div>

    <LoadingSpinner v-if="loading" />

    <EmptyState
      v-else-if="items.length === 0"
      title="暂无资源"
      hint="点击右上角上传第一个资源"
    >
      <template #icon>
        <svg class="mx-auto mb-5" width="70" height="60" viewBox="0 0 70 60" fill="none">
          <path d="M4 12C4 9.79 5.79 8 8 8H24L30 14H62C64.21 14 66 15.79 66 18V48C66 50.21 64.21 52 62 52H8C5.79 52 4 50.21 4 48V12Z" stroke="var(--color-border)" stroke-width="1.5"/>
          <path d="M4 24H66" stroke="var(--color-border)" stroke-width="1"/>
          <rect x="14" y="30" width="18" height="3" rx="1.5" fill="var(--color-accent-bg)"/>
          <rect x="14" y="37" width="26" height="3" rx="1.5" fill="var(--color-accent-bg)"/>
          <circle cx="54" cy="34" r="8" fill="var(--color-accent-bg)" stroke="var(--color-accent)" stroke-width="0.8"/>
          <path d="M51 34L53.5 36.5L57 32" stroke="var(--color-accent)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </template>
    </EmptyState>

    <div v-else class="space-y-2">
      <div
        v-for="(item, i) in items"
        :key="item.id"
        class="ui-panel p-4 group animate-slide-up"
        :class="[`stagger-${Math.min(i + 1, 5)}`]"
      >
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-3 flex-1 min-w-0">
            <div class="w-9 h-9 rounded-md flex items-center justify-center flex-shrink-0" :class="typeIconClass(item.resource_type)">
              <component :is="typeIcon(item.resource_type)" :size="16" :stroke-width="1.5" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium text-[var(--text-body)] text-[var(--color-ink)] truncate">{{ item.title }}</span>
                <span class="ui-tag" :class="typeTagClass(item.resource_type)">{{ resourceTypeMap[item.resource_type] ?? item.resource_type }}</span>
                <span v-if="item.domain" class="ui-tag ui-tag-green">{{ domainMap[item.domain] ?? item.domain }}</span>
              </div>
              <div class="flex items-center gap-3 mt-0.5 text-[var(--color-ink-tertiary)]">
                <span v-if="item.file_size">{{ formatSize(item.file_size) }}</span>
                <span>{{ item.created_at?.slice(0, 10) }}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <button @click="downloadResource(item)" class="ui-btn ui-btn-ghost py-1 px-2.5" aria-label="下载资源">
              <Download :size="12" :stroke-width="2" />
              下载
            </button>
            <button @click="confirmDeleteId = item.id" class="ui-btn ui-btn-ghost py-1 px-2.5 !text-[var(--color-danger)]" aria-label="删除资源">
              <Trash2 :size="12" :stroke-width="2" />
              删除
            </button>
          </div>
        </div>
        <p v-if="item.description" class="text-[var(--color-ink-tertiary)] mt-1.5 ml-12 truncate">{{ item.description }}</p>
      </div>
    </div>

    <div v-if="total > limit" class="mt-[var(--spacing-page)] flex justify-center items-center gap-4">
      <button :disabled="offset === 0" @click="offset -= limit; loadResources()" class="ui-btn ui-btn-ghost disabled:opacity-30">
        上一页
      </button>
      <span class="text-[var(--color-ink-tertiary)]">共 {{ total }} 条</span>
      <button :disabled="offset + limit >= total" @click="offset += limit; loadResources()" class="ui-btn ui-btn-ghost disabled:opacity-30">
        下一页
      </button>
    </div>

    <div v-if="showUploadDialog" class="ui-dialog-overlay" @click.self="showUploadDialog = false" @keydown.escape="showUploadDialog = false" role="dialog" aria-modal="true">
      <div class="ui-dialog">
        <h3 class="text-[var(--text-subtitle)] font-semibold mb-5">上传资源</h3>
        <form @submit.prevent="uploadResource" class="space-y-4">
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">文件</label>
            <div
              class="ui-input flex items-center cursor-pointer"
              :class="dragOver ? 'border-[var(--color-accent)] bg-[var(--color-accent-bg)]' : ''"
              @click="fileInput?.click()"
              @dragover.prevent="dragOver = true"
              @dragleave="dragOver = false"
              @drop.prevent="handleDrop"
            >
              <span class="flex-1" :class="selectedFile ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-tertiary)]'">
                {{ selectedFile ? selectedFile.name : '拖拽文件到此处或点击选择...' }}
              </span>
              <Upload :size="14" :stroke-width="1.5" color="var(--color-ink-tertiary)" />
            </div>
            <input ref="fileInput" type="file" @change="onFileChange" required class="hidden" />
          </div>
          <div v-if="uploadProgress !== null" class="w-full h-2 bg-[var(--color-bg-warm)] rounded-full overflow-hidden">
            <div class="h-full bg-[var(--color-accent)] rounded-full transition-all duration-300" :style="{ width: uploadProgress + '%' }"></div>
          </div>
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">标题</label>
            <input v-model="uploadForm.title" type="text" required class="ui-input" />
          </div>
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">类型</label>
            <select v-model="uploadForm.resource_type" class="ui-input">
              <option v-for="(label, key) in resourceTypeMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">专业域（可选）</label>
            <select v-model="uploadForm.domain" class="ui-input">
              <option value="">不指定</option>
              <option v-for="(label, key) in domainMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div class="flex gap-2 justify-end pt-1">
            <button type="button" @click="showUploadDialog = false" class="ui-btn ui-btn-ghost">取消</button>
            <button type="submit" :disabled="uploading" class="ui-btn ui-btn-primary">
              {{ uploading ? "上传中..." : "上传" }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <ConfirmDialog
      v-model:open="confirmDeleteOpen"
      title="删除资源"
      message="删除后资源文件也将被移除，此操作不可撤销。"
      @confirm="doDeleteResource"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, type Component } from "vue";
import {
  File,
  FileImage,
  FileText,
  Music,
  Upload,
  Video,
  Download,
  Trash2,
} from "lucide-vue-next";
import api from "@/services/api";
import { domainMap, resourceTypeMap } from "@/constants/maps";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";

interface ResourceItem {
  id: string;
  title: string;
  description: string | null;
  resource_type: string;
  status: string;
  domain: string | null;
  file_size: number | null;
  file_type: string | null;
  created_at: string;
}

const items = ref<ResourceItem[]>([]);
const total = ref(0);
const loading = ref(false);
const uploading = ref(false);
const uploadProgress = ref<number | null>(null);
const showUploadDialog = ref(false);
const dragOver = ref(false);
const limit = 50;
const offset = ref(0);
const selectedFile = ref<File | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const confirmDeleteId = ref<string | null>(null);

const confirmDeleteOpen = computed({
  get: () => confirmDeleteId.value !== null,
  set: (v: boolean) => { if (!v) confirmDeleteId.value = null; },
});

const uploadForm = reactive({
  title: "",
  resource_type: "document",
  domain: "",
});

function typeIcon(type: string) {
  const icons: Record<string, Component> = {
    document: FileText,
    video: Video,
    image: FileImage,
    audio: Music,
    other: File,
  };
  return icons[type] ?? icons.other;
}

function typeIconClass(type: string) {
  const map: Record<string, string> = {
    document: "bg-[var(--color-accent-bg)] text-[var(--color-accent)]",
    video: "bg-[var(--color-highlight-bg)] text-[var(--color-highlight)]",
    image: "bg-[var(--color-tag-purple)] text-[var(--color-tag-purple-text)]",
    audio: "bg-[var(--color-tag-green)] text-[var(--color-tag-green-text)]",
    other: "bg-[var(--color-bg-warm)] text-[var(--color-ink-secondary)]",
  };
  return map[type] ?? map.other;
}

function typeTagClass(type: string) {
  const map: Record<string, string> = {
    document: "ui-tag-green",
    video: "ui-tag-amber",
    image: "ui-tag-purple",
    audio: "ui-tag-green",
    other: "ui-tag-blue",
  };
  return map[type] ?? "ui-tag-blue";
}

function formatSize(bytes: number | null) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  selectedFile.value = input.files?.[0] ?? null;
  if (selectedFile.value && !uploadForm.title) {
    uploadForm.title = selectedFile.value.name.replace(/\.[^.]+$/, "");
  }
}

function handleDrop(e: DragEvent) {
  dragOver.value = false;
  const file = e.dataTransfer?.files[0];
  if (file) {
    selectedFile.value = file;
    if (!uploadForm.title) {
      uploadForm.title = file.name.replace(/\.[^.]+$/, "");
    }
  }
}

async function loadResources() {
  loading.value = true;
  try {
    const { data } = await api.get("/resources/", { params: { limit, offset: offset.value } });
    items.value = data.items;
    total.value = data.total;
  } finally {
    loading.value = false;
  }
}

async function uploadResource() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadProgress.value = 0;
  try {
    const formData = new FormData();
    formData.append("file", selectedFile.value);
    formData.append("title", uploadForm.title);
    formData.append("resource_type", uploadForm.resource_type);
    if (uploadForm.domain) formData.append("domain", uploadForm.domain);
    await api.post("/resources/upload", formData, {
      onUploadProgress: (e) => {
        if (e.total) uploadProgress.value = Math.round((e.loaded / e.total) * 100);
      },
    });
    showUploadDialog.value = false;
    uploadForm.title = "";
    uploadForm.domain = "";
    selectedFile.value = null;
    uploadProgress.value = null;
    await loadResources();
  } finally {
    uploading.value = false;
  }
}

async function downloadResource(item: ResourceItem) {
  // BUG-020 AC-5: 下载改用 Authorization header（axios 拦截器自动带），
  // 不再把 token 拼进 URL query（防进浏览器历史 + 代理日志）。
  try {
    const res = await api.get(`/resources/${item.id}/download`, {
      responseType: "blob",
    });
    // 从 Content-Disposition 提取文件名，回退到 item 标题
    const cd = res.headers["content-disposition"] || "";
    const m = cd.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)/i);
    const filename = m?.[1] || `${item.title || item.id}.${item.file_type || "bin"}`;
    const url = window.URL.createObjectURL(res.data);
    const a = document.createElement("a");
    a.href = url;
    a.download = decodeURIComponent(filename);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  } catch {
    // 401 由 api.ts 拦截器跳转 /login；其他错误静默
  }
}

async function doDeleteResource() {
  if (!confirmDeleteId.value) return;
  await api.delete(`/resources/${confirmDeleteId.value}`);
  confirmDeleteId.value = null;
  await loadResources();
}

onMounted(() => {
  loadResources();
});
</script>
