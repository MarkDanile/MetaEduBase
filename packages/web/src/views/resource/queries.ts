// FileDetailView 请求状态封装（Vue Query）。
//
// 把 FileDetailView 的 `loadTasks`（GET + 轮询）+ 3 个 mutation
// 迁到 Vue Query。`loadFile` / `loadChunks` / `loadKg` / `loadTemplates`
// 仍由 FileDetailView 手写（不在本轮范围）。
//
// 错误处理：所有 query/mutation 失败时由 main.ts 注册的 QueryCache.onError
// 统一 toast.error；queryFn 内部不再 try/catch。
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
import { documentApi, type FileDTO, type TaskDTO } from "@/services/document";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const fileKeys = {
  all: ["files"] as const,
  detail: (id: string) => [...fileKeys.all, id, "detail"] as const,
  tasks: (id: string) => [...fileKeys.all, id, "tasks"] as const,
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function useFileTasksQuery(
  fileId: Ref<string>,
  polling: Ref<boolean>,
): UseQueryReturnType<TaskDTO[], Error> {
  return useQuery({
    queryKey: computed(() => fileKeys.tasks(fileId.value)),
    queryFn: () => documentApi.listTasks(fileId.value).then((r) => r.data),
    enabled: computed(() => !!fileId.value),
    // Only refetch every 3s while at least one task is running or pending.
    // Returning `false` pauses polling entirely.
    refetchInterval: computed(() => (polling.value ? 3000 : false)),
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
  useFileTasksQuery,
  useRetryTasksMutation,
  useReinitializeFileMutation,
  useDeleteFileMutation,
};
