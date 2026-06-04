// DatabaseView 请求状态封装（Vue Query）。
//
// 把 DatabaseView 的 5 个 GET 请求和 5 个 mutation 集中到 Vue Query
// （@tanstack/vue-query），替代手写 ref + setInterval + try/catch + toast。
//
// 错误处理：所有 query/mutation 失败时由 main.ts 注册的 QueryCache.onError
// 统一 toast.error；queryFn 内部不再 try/catch。
//
// 成功提示：mutation 的 onSuccess 自行 toast.success 业务文案。

import { computed, type MaybeRef, type Ref, unref } from "vue";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationReturnType,
  type UseQueryReturnType,
} from "@tanstack/vue-query";
import { structuredDataApi, type DatasetDTO, type DatasetRowDTO } from "@/services/structured-data";
import { knowledgeApi, type KnowledgeEdgeDTO, type KnowledgeNodeDTO } from "@/services/knowledge";
import type { TaskDTO } from "@/services/document";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const datasetKeys = {
  all: ["datasets"] as const,
  list: (params: { sort_by: string; sort_dir: string }) =>
    [...datasetKeys.all, "list", params] as const,
  detail: (id: string) => [...datasetKeys.all, "detail", id] as const,
  tasks: (id: string) => [...datasetKeys.all, id, "tasks"] as const,
  rows: (id: string, params: { offset: number; limit: number }) =>
    [...datasetKeys.all, id, "rows", params] as const,
  kg: (id: string) => [...datasetKeys.all, id, "kg"] as const,
  kgOverview: () => [...datasetKeys.all, "kgOverview"] as const,
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

function useDatasetsQuery(
  params: MaybeRef<{ sort_by: string; sort_dir: string }>,
): UseQueryReturnType<DatasetDTO[], Error> {
  return useQuery({
    queryKey: computed(() => datasetKeys.list(unref(params))),
    queryFn: () => structuredDataApi.listDatasets(unref(params)).then((r) => r.data),
  });
}

function useDatasetTasksQuery(
  datasetId: Ref<string | null>,
  refetchIntervalMs: Ref<number | false>,
): UseQueryReturnType<TaskDTO[], Error> {
  return useQuery({
    queryKey: computed(() =>
      datasetId.value
        ? datasetKeys.tasks(datasetId.value)
        : ["datasets", "none", "tasks"],
    ),
    queryFn: () =>
      structuredDataApi.listTasks(datasetId.value as string).then((r) => r.data),
    enabled: computed(() => !!datasetId.value),
    refetchInterval: refetchIntervalMs,
  });
}

function useDatasetRowsQuery(
  datasetId: Ref<string | null>,
  params: Ref<{ offset: number; limit: number }>,
): UseQueryReturnType<DatasetRowDTO[], Error> {
  return useQuery({
    queryKey: computed(() =>
      datasetId.value
        ? datasetKeys.rows(datasetId.value, unref(params))
        : ["datasets", "none", "rows", unref(params)],
    ),
    queryFn: () =>
      structuredDataApi
        .listRows(datasetId.value as string, unref(params))
        .then((r) => r.data),
    enabled: computed(() => !!datasetId.value),
  });
}

interface KgBundle {
  nodes: KnowledgeNodeDTO[];
  edges: KnowledgeEdgeDTO[];
}

function useDatasetKgQuery(
  datasetId: Ref<string | null>,
): UseQueryReturnType<KgBundle, Error> {
  return useQuery({
    queryKey: computed(() =>
      datasetId.value ? datasetKeys.kg(datasetId.value) : ["datasets", "none", "kg"],
    ),
    queryFn: async (): Promise<KgBundle> => {
      const [nodesRes, edgesRes] = await Promise.all([
        knowledgeApi.listNodes({ source_dataset_id: datasetId.value as string, limit: 100 }),
        knowledgeApi.listEdges({ source_dataset_id: datasetId.value as string }),
      ]);
      return { nodes: nodesRes.data, edges: edgesRes.data };
    },
    enabled: computed(() => !!datasetId.value),
  });
}

function useKgOverviewQuery(): UseQueryReturnType<
  { nodes: KnowledgeNodeDTO[]; edges: KnowledgeEdgeDTO[] },
  Error
> {
  return useQuery({
    queryKey: datasetKeys.kgOverview(),
    queryFn: async () => {
      const { data } = await structuredDataApi.getKnowledgeGraph();
      return { nodes: data.nodes, edges: data.edges };
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

function useUploadDatasetMutation(
  onSuccess: () => void,
): UseMutationReturnType<DatasetDTO, Error, FormData, unknown> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (formData: FormData) =>
      structuredDataApi.uploadDataset(formData, "").then((r) => r.data),
    onSuccess: () => {
      onSuccess();
      void qc.invalidateQueries({ queryKey: datasetKeys.all });
    },
  });
}

function useDeleteDatasetMutation(
  datasetId: Ref<string | null>,
  onSuccess: () => void,
): UseMutationReturnType<void, Error, void, unknown> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      structuredDataApi.deleteDataset(datasetId.value as string).then(() => undefined),
    onSuccess: () => {
      onSuccess();
      void qc.invalidateQueries({ queryKey: datasetKeys.all });
    },
  });
}

function useRetryTasksMutation(
  datasetId: Ref<string | null>,
  onSuccess: () => void,
): UseMutationReturnType<TaskDTO[], Error, void, unknown> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      structuredDataApi.retryTasks(datasetId.value as string).then((r) => r.data),
    onSuccess: () => {
      onSuccess();
      if (datasetId.value) {
        void qc.invalidateQueries({ queryKey: datasetKeys.tasks(datasetId.value) });
      }
    },
  });
}

function useReinitializeMutation(
  datasetId: Ref<string | null>,
  onSuccess: () => void,
): UseMutationReturnType<DatasetDTO, Error, void, unknown> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      structuredDataApi
        .reinitializeDataset(datasetId.value as string)
        .then((r) => r.data),
    onSuccess: () => {
      onSuccess();
      if (datasetId.value) {
        void qc.invalidateQueries({ queryKey: datasetKeys.tasks(datasetId.value) });
        void qc.invalidateQueries({ queryKey: datasetKeys.kg(datasetId.value) });
      }
    },
  });
}

function useRebuildKgMutation(
  datasetId: Ref<string | null>,
  onSuccess: () => void,
): UseMutationReturnType<{ status: string; dataset_count: number }, Error, void, unknown> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      structuredDataApi.rebuildKnowledgeGraph().then((r) => r.data),
    onSuccess: () => {
      onSuccess();
      void qc.invalidateQueries({ queryKey: datasetKeys.kgOverview() });
      if (datasetId.value) {
        void qc.invalidateQueries({ queryKey: datasetKeys.kg(datasetId.value) });
      }
    },
  });
}

export {
  useDatasetsQuery,
  useDatasetTasksQuery,
  useDatasetRowsQuery,
  useDatasetKgQuery,
  useKgOverviewQuery,
  useUploadDatasetMutation,
  useDeleteDatasetMutation,
  useRetryTasksMutation,
  useReinitializeMutation,
  useRebuildKgMutation,
};
