<template>
  <div class="p-6 max-w-[1600px] mx-auto">
    <PageHeader :title="file?.filename ?? '文件详情'" subtitle="处理状态与数据预览">
      <template #extra>
        <div class="flex gap-2 mt-2">
          <button class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5" @click="goBack">
            <ArrowLeft :size="14" /> 返回
          </button>
          <button class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5" @click="reinitializeMutation.mutate()">
            <RefreshCw :size="14" /> 重新初始化
          </button>
          <button
            class="ui-btn-ghost px-3 py-1.5 flex items-center gap-1.5 text-red-500"
            @click="showDelete = true"
          >
            <Trash2 :size="14" /> 删除
          </button>
        </div>
      </template>
    </PageHeader>

    <LoadingSpinner v-if="fileQuery.isLoading.value" text="加载文件..." />

    <template v-else-if="file">
      <FileMetaBar :file="file" />

      <FileDetailPipelineStatusPanel
        :tasks="tasks"
        :polling="polling"
        :loading="loadingTasks"
        @retry="retryMutation.mutate()"
        @refresh="refreshAll"
      />

      <FileTabsPanel
        :active-tab="activeTab"
        :templates="templates"
        :chunks="chunks"
        :chunks-loading="chunksQuery.isFetching.value"
        :highlight-chunk-id="highlightChunkId"
        :kg-nodes="kgNodes"
        :kg-edges="kgEdges"
        :kg-loading="kgQuery.isFetching.value"
        :structured-data="file.structured_data"
        @update:active-tab="(k) => (activeTab = k)"
        @node-click="selectedKgNode = $event"
      />
    </template>

    <!-- Delete dialog -->
    <ConfirmDialog
      v-model:open="showDelete"
      title="删除文件"
      :message="`确定删除文件「${file?.filename}」？此操作不可恢复。`"
      @confirm="deleteMutation.mutate()"
    />

    <!-- KG node detail panel -->
    <KGDetailPanel
      :node="selectedKgNode"
      :edges="kgEdges"
      :nodes="kgNodes"
      @close="selectedKgNode = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Trash2, RefreshCw } from "lucide-vue-next";
import PageHeader from "@/components/PageHeader.vue";
import LoadingSpinner from "@/components/LoadingSpinner.vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";
import KGDetailPanel from "@/components/KGDetailPanel.vue";
import FileMetaBar from "@/views/resource/FileMetaBar.vue";
import FileDetailPipelineStatusPanel from "@/views/resource/FileDetailPipelineStatusPanel.vue";
import FileTabsPanel from "@/views/resource/FileTabsPanel.vue";
import { useToast } from "@/composables/useToast";
import { type FileDTO, type ChunkDTO, type TaskDTO } from "@/services/document";
import { type KnowledgeNodeDTO, type KnowledgeEdgeDTO } from "@/services/knowledge";
import { type Template } from "@/services/template";
import {
  useFileQuery,
  useFileTasksQuery,
  useFileChunksQuery,
  useFileKgQuery,
  useTemplatesQuery,
  useRetryTasksMutation,
  useReinitializeFileMutation,
  useDeleteFileMutation,
  fileKeys,
} from "@/views/resource/queries";
import { useQueryClient } from "@tanstack/vue-query";

const route = useRoute();
const router = useRouter();
const toast = useToast();

const fileId = computed(() => route.params.id as string);

// --- State ---
const selectedKgNode = ref<KnowledgeNodeDTO | null>(null);
const activeTab = ref("structured");
const showDelete = ref(false);

// REQ-010 AC-15: ?chunk= query → 自动滚到对应 chunk + 高亮 3s
const highlightChunkId = ref<string | null>(null);

function scrollToChunk(chunkId: string) {
  highlightChunkId.value = chunkId;
  activeTab.value = "chunks";
  // wait for chunks to load + DOM to update
  setTimeout(() => {
    const el = document.getElementById(`chunk-${chunkId}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, 300);
  // clear highlight after 3s
  setTimeout(() => {
    if (highlightChunkId.value === chunkId) {
      highlightChunkId.value = null;
    }
  }, 3000);
}

watch(
  () => route.query.chunk,
  (newChunk) => {
    if (newChunk && typeof newChunk === "string") {
      scrollToChunk(newChunk);
    }
  },
  { immediate: true }
);

// --- Queries (Vue Query) ---
const queryClient = useQueryClient();
const fileQuery = useFileQuery(fileId);
const file = computed<FileDTO | null>(() => fileQuery.data.value ?? null);

const tasksQuery = useFileTasksQuery(fileId);
const tasks = computed<TaskDTO[]>(() => tasksQuery.data.value ?? []);
const loadingTasks = computed(() => tasksQuery.isFetching.value);
const polling = computed(() =>
  tasks.value.some((t) => t.status === "running" || t.status === "pending"),
);

const chunksQuery = useFileChunksQuery(
  fileId,
  // Lazy-load: only fetch chunks when the chunks tab is active.
  computed(() => activeTab.value === "chunks"),
);
const chunks = computed<ChunkDTO[]>(() => chunksQuery.data.value ?? []);

const kgQuery = useFileKgQuery(
  fileId,
  // Lazy-load: only fetch kg when the kg tab is active.
  computed(() => activeTab.value === "kg"),
);
const kgNodes = computed<KnowledgeNodeDTO[]>(() => kgQuery.data.value?.nodes ?? []);
const kgEdges = computed<KnowledgeEdgeDTO[]>(() => kgQuery.data.value?.edges ?? []);

const templatesQuery = useTemplatesQuery();
const templates = computed<Template[]>(() => templatesQuery.data.value ?? []);

// --- Mutations (Vue Query) ---
const retryMutation = useRetryTasksMutation(fileId, () => {
  toast.success("已重新提交任务");
});
const reinitializeMutation = useReinitializeFileMutation(fileId, () => {
  toast.success("已开始重新初始化");
  // Clear stale chunks/kg caches so the next tab switch re-fetches.
  // The legacy behavior was to reset the local refs; with Vue Query we
  // remove the cached entries and let the active-tab query refetch on
  // next access.
  queryClient.removeQueries({ queryKey: fileKeys.chunks(fileId.value) });
  queryClient.removeQueries({ queryKey: fileKeys.kg(fileId.value) });
});
const deleteMutation = useDeleteFileMutation(fileId, () => {
  toast.success("文件已删除");
  router.push("/resource");
});

// --- Data loading (Vue Query) ---
async function refreshAll() {
  await Promise.all([
    fileQuery.refetch(),
    chunksQuery.refetch(),
    kgQuery.refetch(),
  ]);
}

// --- Actions ---
function goBack() {
  router.push("/resource");
}

// --- Tab data loading ---
// Tab switching is handled by the `enabled` ref on each query; switching
// to a tab triggers a refetch via the `enabled` reactive computation. No
// explicit watch needed.

watch(polling, (now, prev) => {
  if (prev && !now) {
    // Tasks just finished — refresh file detail and the active tab's data.
    void fileQuery.refetch();
    if (activeTab.value === "chunks") void chunksQuery.refetch();
    if (activeTab.value === "kg") void kgQuery.refetch();
  }
});
</script>
