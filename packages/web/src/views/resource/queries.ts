// FileDetailView 请求状态封装（Vue Query）。
//
// 把 FileDetailView 的：
// - `loadTasks`（GET + 轮询） + 3 个 mutation（TD-017）
// - `loadFile` / `loadChunks` / `loadKg` / `loadTemplates`（TD-018）
// 全部迁到 Vue Query。
//
// 错误处理：所有 query/mutation 失败时由 main.ts 注册的 QueryCache.onError
// 统一 toast.error；queryFn 内部不再 try/catch。
// 例外：`useTemplatesQuery` 内部 catch 返回 `[]`，保留"templates 是可选"
// 的静默失败语义，不触发全局 toast。
//
// 成功提示：mutation 的 onSuccess 自行 toast.success 业务文案。

import { computed, type Ref } from "vue";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationReturnType,
  type UseQueryReturnType,
} from "@tanstack/vue-query";
import {
  documentApi,
  type ChunkDTO,
  type FileDTO,
  type TaskDTO,
} from "@/services/document";
import {
  knowledgeApi,
  type KnowledgeEdgeDTO,
  type KnowledgeNodeDTO,
} from "@/services/knowledge";
import { templateApi, type Template } from "@/services/template";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const fileKeys = {
  all: ["files"] as const,
  detail: (id: string) => [...fileKeys.all, id, "detail"] as const,
  tasks: (id: string) => [...fileKeys.all, id, "tasks"] as const,
  chunks: (id: string) => [...fileKeys.all, id, "chunks"] as const,
  kg: (id: string) => [...fileKeys.all, id, "kg"] as const,
};

export const templateKeys = {
  all: ["templates"] as const,
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function useFileQuery(fileId: Ref<string>): UseQueryReturnType<FileDTO, Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.detail(fileId.value)),
    queryFn: () => documentApi.getFile(fileId.value).then((r) => r.data),
    enabled: computed(() => !!fileId.value),
  });
}

function useFileTasksQuery(
  fileId: Ref<string>,
): UseQueryReturnType<TaskDTO[], Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.tasks(fileId.value)),
    queryFn: () => documentApi.listTasks(fileId.value).then((r) => r.data),
    enabled: computed(() => !!fileId.value),
    // TD-019 fix: derive the polling signal from `query.state.data`
    // inside Vue Query, not from a `polling` ref passed in by the
    // caller. The previous approach passed a `computed(() =>
    // tasksQuery.data.value ...)` from the page; because Vue Query
    // synchronously evaluates `refetchInterval` during `useQuery()`
    // to build a `watchEffect`, the closure would try to read
    // `tasksQuery` while it was still in the `const` initializer and
    // hit a `ReferenceError: Cannot access 'tasksQuery' before
    // initialization`. Using the function form defers the read until
    // after the first fetch completes, which is exactly the same
    // moment a caller-driven `computed` would have re-evaluated.
    refetchInterval: (query) => {
      const data = query.state.data;
      const hasActive =
        Array.isArray(data) &&
        data.some((t) => t.status === "running" || t.status === "pending");
      return hasActive ? 3000 : false;
    },
  });
}

function useFileChunksQuery(
  fileId: Ref<string>,
  enabled: Ref<boolean>,
): UseQueryReturnType<ChunkDTO[], Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.chunks(fileId.value)),
    queryFn: () => documentApi.listChunks(fileId.value).then((r) => r.data),
    enabled: computed(() => !!fileId.value && enabled.value),
  });
}

interface KgBundle {
  nodes: KnowledgeNodeDTO[];
  edges: KnowledgeEdgeDTO[];
}

function useFileKgQuery(
  fileId: Ref<string>,
  enabled: Ref<boolean>,
): UseQueryReturnType<KgBundle, Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.kg(fileId.value)),
    queryFn: async (): Promise<KgBundle> => {
      // BUG-006 #4 fix: 改用原子端点保证 edges.source/target 都在 nodes 列表
      // 旧路径 listNodes(limit=50) + listEdges(无 limit) 在 > 50 节点时
      // g6 抛 'Node not found' 整图白屏
      const { data } = await knowledgeApi.getFileKgBundle(fileId.value);
      return { nodes: data.nodes, edges: data.edges };
    },
    enabled: computed(() => !!fileId.value && enabled.value),
  });
}

function useTemplatesQuery(): UseQueryReturnType<Template[], Error> {
  return useQuery({
    queryKey: templateKeys.all,
    // Legacy `loadTemplates` silently failed; preserve that behavior by
    // catching inside the queryFn and returning an empty array. Errors
    // do not surface to QueryCache.onError, so the global toast handler
    // is not triggered.
    queryFn: async () => {
      try {
        return (await templateApi.list()).data;
      } catch {
        return [];
      }
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

function useRetryTasksMutation(
  fileId: Ref<string>,
  onSuccess: () => void,
): UseMutationReturnType<TaskDTO[], Error, void, unknown> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => documentApi.retryTasks(fileId.value).then((r) => r.data),
    onSuccess: () => {
      onSuccess();
      void qc.invalidateQueries({ queryKey: fileKeys.tasks(fileId.value) });
    },
  });
}

function useReinitializeFileMutation(
  fileId: Ref<string>,
  onSuccess: () => void,
): UseMutationReturnType<FileDTO, Error, void, unknown> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => documentApi.reinitializeFile(fileId.value).then((r) => r.data),
    onSuccess: () => {
      onSuccess();
      // Reinitialize invalidates both the file detail and the task list.
      void qc.invalidateQueries({ queryKey: fileKeys.detail(fileId.value) });
      void qc.invalidateQueries({ queryKey: fileKeys.tasks(fileId.value) });
    },
  });
}

function useDeleteFileMutation(
  fileId: Ref<string>,
  onSuccess: () => void,
): UseMutationReturnType<void, Error, void, unknown> {
  return useMutation({
    mutationFn: () => documentApi.deleteFile(fileId.value).then(() => undefined),
    onSuccess: () => {
      onSuccess();
      // No cache invalidation — caller navigates away.
    },
  });
}

export {
  useFileQuery,
  useFileTasksQuery,
  useFileChunksQuery,
  useFileKgQuery,
  useTemplatesQuery,
  useRetryTasksMutation,
  useReinitializeFileMutation,
  useDeleteFileMutation,
};
