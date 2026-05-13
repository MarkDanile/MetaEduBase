<template>
  <div class="p-8 max-w-[1000px] mx-auto">
    <div class="flex items-start justify-between mb-8 animate-slide-up">
      <div>
        <h1 class="text-[24px] font-semibold tracking-tight" style="letter-spacing:-0.5px">知识库</h1>
        <p class="text-[13px] text-[var(--color-ink-tertiary)] mt-1">管理和浏览结构化的职业教育知识体系</p>
        <div class="wet-line mt-2.5" style="width:40px"></div>
      </div>
      <button @click="showCreateDialog = true" class="liquid-btn liquid-btn-primary">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建节点
      </button>
    </div>

    <div class="mb-6 bg-[var(--color-bg-warm)] border border-[var(--color-border)] rounded-[var(--radius-md)] px-4 py-2.5 flex gap-3 items-center animate-slide-up stagger-1">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input
        v-model="searchQuery"
        type="text"
        class="flex-1 bg-transparent outline-none text-[14px] text-[var(--color-ink)] placeholder:text-[var(--color-ink-tertiary)]"
        placeholder="搜索知识节点..."
        @keyup.enter="handleSearch"
      />
      <button v-if="searchQuery" @click="clearSearch" class="text-[12px] text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink)] transition-colors">清除</button>
    </div>

    <div v-if="breadcrumbPath.length > 0" class="mb-5 flex items-center gap-1.5 text-[13px] animate-slide-up stagger-2">
      <button @click="loadNodes()" class="text-[var(--color-accent)] hover:underline">根目录</button>
      <template v-for="(crumb, i) in breadcrumbPath" :key="i">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="1.5"><polyline points="9 18 15 12 9 6"/></svg>
        <button
          @click="loadNodes(crumb.id)"
          :class="i === breadcrumbPath.length - 1 ? 'text-[var(--color-ink)] font-medium' : 'text-[var(--color-accent)] hover:underline'"
        >
          {{ crumb.title }}
        </button>
      </template>
    </div>

    <div v-if="loading" class="py-20 text-center">
      <div class="inline-flex items-center gap-2 text-[var(--color-ink-tertiary)] text-[14px]">
        <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
        加载中...
      </div>
    </div>

    <div v-else-if="nodes.length === 0" class="py-16 text-center animate-slide-up stagger-2">
      <svg class="mx-auto mb-5" width="80" height="60" viewBox="0 0 80 60" fill="none">
        <rect x="8" y="4" width="64" height="48" rx="4" stroke="var(--color-border)" stroke-width="1.5"/>
        <line x1="8" y1="20" x2="72" y2="20" stroke="var(--color-border)" stroke-width="1"/>
        <line x1="8" y1="36" x2="72" y2="36" stroke="var(--color-border)" stroke-width="1"/>
        <rect x="16" y="9" width="12" height="7" rx="1.5" fill="var(--color-accent-bg)" stroke="var(--color-accent)" stroke-width="0.8"/>
        <rect x="32" y="9" width="16" height="7" rx="1.5" fill="var(--color-accent-bg)" stroke="var(--color-accent)" stroke-width="0.8"/>
        <rect x="16" y="25" width="20" height="7" rx="1.5" fill="var(--color-tag-green)" stroke="var(--color-tag-green-text)" stroke-width="0.8"/>
        <rect x="40" y="25" width="8" height="7" rx="1.5" fill="var(--color-tag-green)" stroke="var(--color-tag-green-text)" stroke-width="0.8"/>
        <rect x="16" y="41" width="14" height="7" rx="1.5" fill="var(--color-tag-amber)" stroke="var(--color-tag-amber-text)" stroke-width="0.8"/>
        <rect x="34" y="41" width="22" height="7" rx="1.5" fill="var(--color-tag-amber)" stroke="var(--color-tag-amber-text)" stroke-width="0.8"/>
      </svg>
      <p class="text-[var(--color-ink-secondary)] text-[14px] font-medium">暂无知识节点</p>
      <p class="text-[var(--color-ink-tertiary)] text-[12px] mt-1">点击右上角创建第一个知识节点</p>
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="(node, i) in nodes"
        :key="node.id"
        class="liquid-card p-4 cursor-pointer group animate-slide-up"
        :class="[`stagger-${Math.min(i + 1, 5)}`]"
        @click="selectNode(node)"
      >
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-md flex items-center justify-center text-[11px] font-semibold" :class="levelIconClass(node.level)">
            {{ levelLabel(node.level).charAt(0) }}
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium text-[14px] text-[var(--color-ink)] truncate">{{ node.title }}</span>
              <span class="liquid-tag liquid-tag-blue">{{ levelLabel(node.level) }}</span>
              <span class="liquid-tag liquid-tag-green">{{ domainLabel(node.domain) }}</span>
            </div>
            <p v-if="node.description" class="text-[12px] text-[var(--color-ink-tertiary)] mt-0.5 truncate">{{ node.description }}</p>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </div>
        <div v-if="node.tags.length > 0" class="flex gap-1.5 mt-2 ml-11 flex-wrap">
          <span v-for="tag in node.tags" :key="tag" class="liquid-tag liquid-tag-amber">{{ tag }}</span>
        </div>
      </div>
    </div>

    <transition name="detail-slide">
      <div v-if="selectedNode" class="mt-6 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] p-6 animate-slide-up">
        <div class="flex items-start justify-between mb-5">
          <div>
            <h2 class="text-[18px] font-semibold tracking-tight">{{ selectedNode.title }}</h2>
            <p v-if="selectedNode.description" class="text-[14px] text-[var(--color-ink-secondary)] mt-1">{{ selectedNode.description }}</p>
          </div>
          <button @click="selectedNode = null" class="p-1.5 rounded-md hover:bg-[var(--color-bg-hover)] transition-colors">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-ink-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>

        <div class="grid grid-cols-3 gap-3">
          <div class="bg-[var(--color-bg-warm)] rounded-[var(--radius-md)] p-3">
            <p class="text-[11px] text-[var(--color-ink-tertiary)] mb-0.5">层级</p>
            <p class="text-[13px] font-medium">{{ levelLabel(selectedNode.level) }}</p>
          </div>
          <div class="bg-[var(--color-bg-warm)] rounded-[var(--radius-md)] p-3">
            <p class="text-[11px] text-[var(--color-ink-tertiary)] mb-0.5">专业域</p>
            <p class="text-[13px] font-medium">{{ domainLabel(selectedNode.domain) }}</p>
          </div>
          <div class="bg-[var(--color-bg-warm)] rounded-[var(--radius-md)] p-3">
            <p class="text-[11px] text-[var(--color-ink-tertiary)] mb-0.5">路径</p>
            <p class="text-[12px] font-mono text-[var(--color-ink-secondary)] truncate">{{ selectedNode.path || "—" }}</p>
          </div>
        </div>

        <div v-if="selectedNode.tags.length > 0" class="mt-4 flex gap-1.5 flex-wrap">
          <span v-for="tag in selectedNode.tags" :key="tag" class="liquid-tag liquid-tag-amber">{{ tag }}</span>
        </div>

        <div class="mt-5 flex gap-2">
          <button @click="drillDown(selectedNode)" class="liquid-btn liquid-btn-primary text-[13px] py-1.5 px-4">
            查看子节点
          </button>
          <button @click="deleteNode(selectedNode.id)" class="liquid-btn liquid-btn-ghost text-[13px] py-1.5 px-4 !text-[var(--color-danger)]">
            删除
          </button>
        </div>
      </div>
    </transition>

    <div v-if="showCreateDialog" class="liquid-dialog-overlay" @click.self="showCreateDialog = false">
      <div class="liquid-dialog">
        <h3 class="text-[16px] font-semibold mb-5">新建知识节点</h3>
        <form @submit.prevent="createNode" class="space-y-4">
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">标题</label>
            <input v-model="newNode.title" type="text" required class="liquid-input" />
          </div>
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">专业域</label>
            <select v-model="newNode.domain" class="liquid-input">
              <option v-for="(label, key) in domainMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">层级</label>
            <select v-model="newNode.level" class="liquid-input">
              <option v-for="(label, key) in levelMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block text-[13px] font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">描述（可选）</label>
            <textarea v-model="newNode.description" rows="2" class="liquid-input resize-none" />
          </div>
          <div class="flex gap-2 justify-end pt-1">
            <button type="button" @click="showCreateDialog = false" class="liquid-btn liquid-btn-ghost text-[13px]">取消</button>
            <button type="submit" class="liquid-btn liquid-btn-primary text-[13px]">创建</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { knowledgeApi, type KnowledgeNodeDTO } from "@/services/knowledge";

const nodes = ref<KnowledgeNodeDTO[]>([]);
const loading = ref(false);
const selectedNode = ref<KnowledgeNodeDTO | null>(null);
const showCreateDialog = ref(false);
const searchQuery = ref("");
const breadcrumbPath = ref<{ id: string; title: string }[]>([]);

const newNode = reactive({
  title: "",
  domain: "electronics_info",
  level: "professional",
  description: "",
  parent_id: null as string | null,
});

const levelMap: Record<string, string> = {
  professional: "专业",
  course: "课程",
  chapter: "章节",
  knowledge_point: "知识点",
  skill_point: "技能点",
  operation_step: "操作步骤",
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

function levelLabel(level: string) {
  return levelMap[level] ?? level;
}

function domainLabel(domain: string) {
  return domainMap[domain] ?? domain;
}

function levelIconClass(level: string) {
  const map: Record<string, string> = {
    professional: "bg-[var(--color-accent-bg)] text-[var(--color-accent)]",
    course: "bg-[var(--color-tag-green)] text-[var(--color-tag-green-text)]",
    chapter: "bg-[var(--color-highlight-bg)] text-[var(--color-highlight)]",
    knowledge_point: "bg-[var(--color-tag-blue)] text-[var(--color-tag-blue-text)]",
    skill_point: "bg-[var(--color-tag-purple)] text-[var(--color-tag-purple-text)]",
    operation_step: "bg-[var(--color-bg-warm)] text-[var(--color-ink-secondary)]",
  };
  return map[level] ?? map.professional;
}

async function loadNodes(parentId?: string) {
  loading.value = true;
  try {
    const { data } = await knowledgeApi.listNodes(parentId ? { parent_id: parentId } : undefined);
    nodes.value = data;
  } finally {
    loading.value = false;
  }
}

function selectNode(node: KnowledgeNodeDTO) {
  selectedNode.value = node;
}

function drillDown(node: KnowledgeNodeDTO) {
  breadcrumbPath.value.push({ id: node.id, title: node.title });
  newNode.parent_id = node.id;
  selectedNode.value = null;
  loadNodes(node.id);
}

async function deleteNode(id: string) {
  await knowledgeApi.deleteNode(id);
  selectedNode.value = null;
  await loadNodes(breadcrumbPath.value.length > 0 ? breadcrumbPath.value[breadcrumbPath.value.length - 1].id : undefined);
}

async function createNode() {
  await knowledgeApi.createNode({
    title: newNode.title,
    domain: newNode.domain,
    level: newNode.level,
    description: newNode.description || undefined,
    parent_id: newNode.parent_id,
  });
  showCreateDialog.value = false;
  newNode.title = "";
  newNode.description = "";
  newNode.parent_id = null;
  await loadNodes(breadcrumbPath.value.length > 0 ? breadcrumbPath.value[breadcrumbPath.value.length - 1].id : undefined);
}

async function handleSearch() {
  if (!searchQuery.value.trim()) return;
  loading.value = true;
  try {
    const { data } = await knowledgeApi.search(searchQuery.value.trim());
    nodes.value = data.results ?? data;
  } finally {
    loading.value = false;
  }
}

function clearSearch() {
  searchQuery.value = "";
  loadNodes(breadcrumbPath.value.length > 0 ? breadcrumbPath.value[breadcrumbPath.value.length - 1].id : undefined);
}

onMounted(() => {
  loadNodes();
});
</script>

<style scoped>
.detail-slide-enter-active {
  transition: all var(--duration-normal) var(--ease-out);
}
.detail-slide-leave-active {
  transition: all var(--duration-fast) var(--ease-out);
}
.detail-slide-enter-from,
.detail-slide-leave-to {
  opacity: 0;
  transform: translateY(6px);
}
</style>
