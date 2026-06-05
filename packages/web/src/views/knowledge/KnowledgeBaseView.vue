<template>
  <div class="p-[var(--spacing-page)] max-w-[1000px] mx-auto flex gap-6" style="min-height:100vh">
    <div class="flex-1 min-w-0">
      <div class="flex items-start justify-between mb-[var(--spacing-page)] animate-slide-up">
        <PageHeader title="知识库" subtitle="结构化职业教育知识体系" />
        <button @click="showCreateDialog = true" class="ui-btn ui-btn-primary flex-shrink-0">
          <Plus :size="16" :stroke-width="2" />
          新建节点
        </button>
      </div>

      <div class="mb-[var(--spacing-section)] bg-[var(--color-bg-warm)] border border-[var(--color-border)] rounded-[var(--radius-md)] px-4 py-2.5 flex gap-3 items-center animate-slide-up stagger-1">
        <Search :size="16" :stroke-width="1.5" color="var(--color-ink-tertiary)" />
        <input
          v-model="searchQuery"
          type="text"
          class="flex-1 bg-transparent outline-none text-[var(--text-body)] text-[var(--color-ink)] placeholder:text-[var(--color-ink-tertiary)]"
          placeholder="搜索知识节点..."
          @keyup.enter="handleSearch"
        />
        <button v-if="searchQuery" @click="clearSearch" class="text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink)] transition-colors">清除</button>
      </div>

      <div v-if="breadcrumbPath.length > 0" class="mb-5 flex items-center gap-1.5 animate-slide-up stagger-2">
        <button @click="loadNodes()" class="text-[var(--color-accent)] hover:underline">根目录</button>
        <template v-for="(crumb, i) in breadcrumbPath" :key="i">
          <ChevronRight :size="12" :stroke-width="1.5" color="var(--color-ink-tertiary)" />
          <button
            @click="loadNodes(crumb.id)"
            :class="i === breadcrumbPath.length - 1 ? 'text-[var(--color-ink)] font-medium' : 'text-[var(--color-accent)] hover:underline'"
          >
            {{ crumb.title }}
          </button>
        </template>
      </div>

      <LoadingSpinner v-if="loading" />

      <EmptyState
        v-else-if="nodes.length === 0"
        title="暂无知识节点"
        hint="点击右上角创建第一个知识节点"
      />

      <div v-else class="space-y-2">
        <div
          v-for="(node, i) in nodes"
          :key="node.id"
          class="ui-panel p-4 cursor-pointer group animate-slide-up"
          :class="[`stagger-${Math.min(i + 1, 5)}`, { 'ring-1 ring-[var(--color-accent)] ring-offset-2': selectedNode?.id === node.id }]"
          @click="selectNode(node)"
        >
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded-md flex items-center justify-center text-[var(--text-micro)] font-semibold" :class="levelIconClass(node.level)">
              {{ levelMap[node.level]?.charAt(0) ?? "?" }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium text-[var(--text-body)] text-[var(--color-ink)] truncate">{{ node.title }}</span>
                <span class="ui-tag ui-tag-blue">{{ levelMap[node.level] ?? node.level }}</span>
                <span class="ui-tag ui-tag-green">{{ domainMap[node.domain] ?? node.domain }}</span>
              </div>
              <p v-if="node.description" class="text-[var(--color-ink-tertiary)] mt-0.5 truncate">{{ node.description }}</p>
            </div>
            <ChevronRight :size="14" :stroke-width="1.5" class="opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-[var(--color-ink-tertiary)]" />
          </div>
          <div v-if="node.tags.length > 0" class="flex gap-1.5 mt-2 ml-11 flex-wrap">
            <span v-for="tag in node.tags" :key="tag" class="ui-tag ui-tag-amber">{{ tag }}</span>
          </div>
        </div>
      </div>
    </div>

    <transition name="drawer-slide">
      <div v-if="selectedNode" class="w-[360px] flex-shrink-0 bg-[var(--color-bg-elevated)] border-l border-[var(--color-border)] h-[100vh] sticky top-0 overflow-y-auto animate-slide-up">
        <div class="p-6">
          <div class="flex items-start justify-between mb-5">
            <div>
              <h2 class="text-[var(--text-section-title)] font-semibold tracking-tight">{{ selectedNode.title }}</h2>
              <p v-if="selectedNode.description" class="text-[var(--text-body)] text-[var(--color-ink-secondary)] mt-1">{{ selectedNode.description }}</p>
            </div>
            <button @click="selectedNode = null" class="p-1.5 rounded-md hover:bg-[var(--color-bg-hover)] transition-colors" aria-label="关闭详情">
              <X :size="14" :stroke-width="1.5" color="var(--color-ink-tertiary)" />
            </button>
          </div>

          <div class="grid grid-cols-1 gap-3">
            <div class="bg-[var(--color-bg-warm)] rounded-[var(--radius-md)] p-3">
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mb-0.5">层级</p>
              <p class="font-medium">{{ levelMap[selectedNode.level] ?? selectedNode.level }}</p>
            </div>
            <div class="bg-[var(--color-bg-warm)] rounded-[var(--radius-md)] p-3">
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mb-0.5">专业域</p>
              <p class="font-medium">{{ domainMap[selectedNode.domain] ?? selectedNode.domain }}</p>
            </div>
            <div class="bg-[var(--color-bg-warm)] rounded-[var(--radius-md)] p-3">
              <p class="text-[var(--text-micro)] text-[var(--color-ink-tertiary)] mb-0.5">路径</p>
              <p class="font-mono text-[var(--color-ink-secondary)] truncate">{{ selectedNode.path || "—" }}</p>
            </div>
          </div>

          <div v-if="selectedNode.tags.length > 0" class="mt-4 flex gap-1.5 flex-wrap">
            <span v-for="tag in selectedNode.tags" :key="tag" class="ui-tag ui-tag-amber">{{ tag }}</span>
          </div>

          <div class="mt-5 flex gap-2">
            <button @click="drillDown(selectedNode)" class="ui-btn ui-btn-primary py-1.5 px-4">
              查看子节点
            </button>
            <button @click="confirmDeleteId = selectedNode.id" class="ui-btn ui-btn-ghost py-1.5 px-4 !text-[var(--color-danger)]">
              删除
            </button>
          </div>
        </div>
      </div>
    </transition>

    <div v-if="showCreateDialog" class="ui-dialog-overlay" @click.self="showCreateDialog = false" @keydown.escape="showCreateDialog = false" role="dialog" aria-modal="true">
      <div class="ui-dialog">
        <h3 class="text-[var(--text-subtitle)] font-semibold mb-5">新建知识节点</h3>
        <form @submit.prevent="createNode" class="space-y-4">
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">标题</label>
            <input v-model="newNode.title" type="text" required class="ui-input" />
          </div>
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">专业域</label>
            <select v-model="newNode.domain" class="ui-input">
              <option v-for="(label, key) in domainMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">层级</label>
            <select v-model="newNode.level" class="ui-input">
              <option v-for="(label, key) in levelMap" :key="key" :value="key">{{ label }}</option>
            </select>
          </div>
          <div>
            <label class="block font-medium text-[var(--color-ink-secondary)] mb-1 ml-0.5">描述（可选）</label>
            <textarea v-model="newNode.description" rows="2" class="ui-input resize-none" />
          </div>
          <div class="flex gap-2 justify-end pt-1">
            <button type="button" @click="showCreateDialog = false" class="ui-btn ui-btn-ghost">取消</button>
            <button type="submit" class="ui-btn ui-btn-primary">创建</button>
          </div>
        </form>
      </div>
    </div>

    <ConfirmDialog
      v-model:open="confirmDeleteOpen"
      title="删除知识节点"
      message="删除后关联的边和资源也会被清理，此操作不可撤销。"
      @confirm="doDeleteNode"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from "vue";
import { Plus, Search, ChevronRight, X } from "lucide-vue-next";
import { knowledgeApi, type KnowledgeNodeDTO } from "@/services/knowledge";
import { domainMap, levelMap } from "@/constants/maps";
import PageHeader from "@/components/PageHeader.vue";
import EmptyState from "@/components/EmptyState.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";

const nodes = ref<KnowledgeNodeDTO[]>([]);
const loading = ref(false);
const selectedNode = ref<KnowledgeNodeDTO | null>(null);
const showCreateDialog = ref(false);
const searchQuery = ref("");
const breadcrumbPath = ref<{ id: string; title: string }[]>([]);
const confirmDeleteId = ref<string | null>(null);

const confirmDeleteOpen = computed({
  get: () => confirmDeleteId.value !== null,
  set: (v: boolean) => { if (!v) confirmDeleteId.value = null; },
});

const newNode = reactive({
  title: "",
  domain: "electronics_info",
  level: "professional",
  description: "",
  parent_id: null as string | null,
});

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

async function doDeleteNode() {
  if (!confirmDeleteId.value) return;
  await knowledgeApi.deleteNode(confirmDeleteId.value);
  selectedNode.value = null;
  confirmDeleteId.value = null;
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
.drawer-slide-enter-active {
  transition: all var(--duration-normal) var(--ease-out);
}
.drawer-slide-leave-active {
  transition: all var(--duration-fast) var(--ease-out);
}
.drawer-slide-enter-from,
.drawer-slide-leave-to {
  opacity: 0;
  transform: translateX(24px);
}
</style>
