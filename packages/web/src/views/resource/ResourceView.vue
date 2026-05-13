<template>
  <div class="p-8 max-w-[1000px] mx-auto">
    <div class="flex items-start justify-between mb-8 animate-slide-up">
      <div>
        <h1 class="text-[24px] font-semibold tracking-tight" style="letter-spacing:-0.5px">校本资源</h1>
        <p class="text-[13px] text-[var(--color-ink-tertiary)] mt-1">教学资源上传、解析与管理</p>
        <div class="wet-line mt-2.5" style="width:40px"></div>
      </div>
      <button @click="showUploadDialog = true" class="liquid-btn liquid-btn-primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        上传资源
      </button>
    </div>

    <div v-if="loading" class="py-20 text-center">
      <div class="inline-flex items-center gap-2 text-[var(--color-ink-tertiary)] text-[14px]">
        <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
        加载中...
      </div>
    </div>

    <div v-else-if="items.length === 0" class="py-16 text-center animate-slide-up stagger-1">
      <svg class="mx-auto mb-5" width="70" height="60" viewBox="0 0 70 60" fill="none">
        <path d="M4 12C4 9.79 5.79 8 8 8H24L30 14H62C64.21 14 66 15.79 66 18V48C66 50.21 64.21 52 62 52H8C5.79 52 4 50.21 4 48V12Z" stroke="var(--color-border)" stroke-width="1.5"/>
        <path d="M4 24H66" stroke="var(--color-border)" stroke-width="1"/>
        <rect x="14" y="30" width="18" height="3" rx="1.5" fill="var(--color-accent-bg)"/>
        <rect x="14" y="37" width="26" height="3" rx="1.5" fill="var(--color-accent-bg)"/>
        <circle cx="54" cy="34" r="8" fill="var(--color-accent-bg)" stroke="var(--color-accent)" stroke-width="0.8"/>
        <path d="M51 34L53.5 36.5L57 32" stroke="var(--color-accent)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <p class="text-[var(--color-ink-secondary)] text-[14px] font-medium">暂无资源</p>
      <p class="text-[var(--color-ink-tertiary)] text-[12px] mt-1">点击右上角上传第一个资源</p>
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="(item, i) in items"
        :key="item.id"
        class="liquid-card p-4 group animate-slide-up"
        :class="[`stagger-${Math.min(i + 1, 5)}`]"
      >
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-3 flex-1 min-w-0">
            <div class="w-9 h-9 rounded-md flex items-center justify-center flex-shrink-0" :class="typeIconClass(item.resource_type)">
              <div v-html="typeIcon(item.resource_type)" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium text-[14px] text-[var(--color-ink)] truncate">{{ item.title }}</span>
                <span class="liquid-tag" :class="typeTagClass(item.resource_type)">{{ typeLabel(item.resource_type) }}</span>
                <span v-if="item.domain" class="liquid-tag liquid-tag-green">{{ domainLabel(item.domain) }}</span>
              </div>
              <div class="flex items-center gap-3 mt-0.5 text-[12px] text-[var(--color-ink-tertiary)]">
                <span v-if="item.file_size">{{ formatSize(item.file_size) }}</span>
                <span>{{ item.created_at?.slice(0, 10) }}</span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <button @click="downloadResource(item)" class="liquid-btn liquid-btn-ghost text-[12px] py-1 px-2.5">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              下载
            </button>
            <button @click="deleteResource(item.id)" class="liquid-btn liquid-btn-ghost text-[12px] py-1 px-2.5 !text-[var(--color-danger)]">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
              删除
            </button>
          </div>
        </div>
        <p v-if="item.description" class="text-[12px] text-[var(--color-ink-tertiary)] mt-1.5 ml-12 truncate">{{ item.description }}</p>
      </div>
    </div>

    <div v-if="total > limit" class="mt-8 flex justify-center items-center gap-4">
      <button :disabled="offset === 0" @click="offset -= limit; loadResources()" class="liquid-btn liquid-btn-ghost text-[13px] disabled:opacity-30">
        上一页
      </button>
      <span class="text-[13px] text-[var(--color-ink-tertiary)]">共 {{ total }} 条</span>
      <button :disabled="offset + limit >= total" @click="offset += limit; loadResources()" class="liquid-btn liquid-btn-ghost text-[13px] disabled:opacity-30">
        下一页
      </button>
    </div>

    <div v-if="showUploadDialog" class="liquid-dialog-overlay" @click.self="showUploadDialog = false">
      <div class="liquid-dialog">
        <h3 class="text-[16px] font-semibold mb-5">上传资源</h3>
        <form @submit.prevent="uploadResource" class="space-y-4">
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">文件</label>
            <div class="liquid-input flex items-center cursor-pointer" @click="($refs.fileInput as HTMLInputElement)?.click()">
              <span class="flex-1 text-[13px]" :class="selectedFile ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-tertiary)]'">
                {{ selectedFile ? selectedFile.name : '选择文件...' }}
              </span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            <input ref="fileInput" type="file" @change="onFileChange" required class="hidden" />
          </div>
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">标题</label>
            <input v-model="uploadForm.title" type="text" required class="liquid-input" />
          </div>
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">类型</label>
            <select v-model="uploadForm.resource_type" class="liquid-input">
              <option v-for="(label, key) in typeMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">专业域（可选）</label>
            <select v-model="uploadForm.domain" class="liquid-input">
              <option value="">不指定</option>
              <option v-for="(label, key) in domainMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div class="flex gap-2 justify-end pt-1">
            <button type="button" @click="showUploadDialog = false" class="liquid-btn liquid-btn-ghost text-[13px]">取消</button>
            <button type="submit" :disabled="uploading" class="liquid-btn liquid-btn-primary text-[13px]">
              {{ uploading ? "上传中..." : "上传" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import api from "@/services/api";

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
const showUploadDialog = ref(false);
const limit = 50;
const offset = ref(0);
const selectedFile = ref<File | null>(null);

const uploadForm = reactive({
  title: "",
  resource_type: "document",
  domain: "",
});

const typeMap: Record<string, string> = {
  document: "文档",
  video: "视频",
  image: "图片",
  audio: "音频",
  other: "其他",
};

const domainMap: Record<string, string> = {
  electronics_info: "电子与信息",
  smart_manufacturing: "智能制造",
  finance_commerce: "财经商贸",
  medical_health: "医药健康",
  education_sports: "教育与体育",
  civil_engineering: "土木建筑",
  transportation: "交通运输",
  agriculture: "农林牧渔",
  art_design: "文化艺术",
  public_service: "公共管理",
};

function typeLabel(t: string) { return typeMap[t] ?? t; }
function domainLabel(d: string) { return domainMap[d] ?? d; }

function typeIcon(type: string) {
  const icons: Record<string, string> = {
    document: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    video: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>',
    image: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>',
    audio: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
    other: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>',
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
    document: "liquid-tag-green",
    video: "liquid-tag-amber",
    image: "liquid-tag-purple",
    audio: "liquid-tag-green",
    other: "liquid-tag-blue",
  };
  return map[type] ?? "liquid-tag-blue";
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
  try {
    const formData = new FormData();
    formData.append("file", selectedFile.value);
    formData.append("title", uploadForm.title);
    formData.append("resource_type", uploadForm.resource_type);
    if (uploadForm.domain) formData.append("domain", uploadForm.domain);
    await api.post("/resources/upload", formData);
    showUploadDialog.value = false;
    uploadForm.title = "";
    uploadForm.domain = "";
    selectedFile.value = null;
    await loadResources();
  } finally {
    uploading.value = false;
  }
}

function downloadResource(item: ResourceItem) {
  const token = localStorage.getItem("metaedu_token");
  window.open(`/api/v1/resources/${item.id}/download?token=${token}`, "_blank");
}

async function deleteResource(id: string) {
  await api.delete(`/resources/${id}`);
  await loadResources();
}

onMounted(() => {
  loadResources();
});
</script>
