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
import { structuredDataApi, type DatasetDTO, type DatasetRowDTO, type KGNode, type KGEdge } from "@/services/structured-data";
import { knowledgeApi, type KnowledgeEdgeDTO, type KnowledgeNodeDTO } from "@/services/knowledge";
import type { TaskDTO } from "@/services/document";

// ---------------------------------------------------------------------------
// DTO adapters
// ---------------------------------------------------------------------------

/**
 * Map the lightweight overview payload (`KGNode` / `KGEdge` from
 * `structured-data.ts`) into the full DTO shapes used by `KGGraph.vue`
 * (`KnowledgeNodeDTO` / `KnowledgeEdgeDTO` from `knowledge.ts`).
 *
 * The two types share identity columns (id / source_id / target_id) but
 * differ in display metadata. We fill the missing fields with safe defaults
 * so the consumer doesn't have to sprinkle `?? {}` or `unknown as` casts.
 */
function kgOverviewToDto(overview: {
  nodes: KGNode[];
  edges: KGEdge[];
}): { nodes: KnowledgeNodeDTO[]; edges: KnowledgeEdgeDTO[] } {
  return {
    nodes: overview.nodes.map<KnowledgeNodeDTO>((n) => ({
      id: n.id,
      tenant_id: "",
      title: n.title,
      description: n.description,
      domain: n.domain,
      level: n.level,
      parent_id: null,
      path: null,
      tags: [],
      metadata: {},
    })),
    edges: overview.edges.map<KnowledgeEdgeDTO>((e) => ({
      id: e.id,
      source_id: e.source_id,
      target_id: e.target_id,
      relation_type: e.relation_type,
      weight: 1,
      metadata: e.metadata ?? {},
    })),
  };
}

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

function useKgOverviewQuery(
  enabled: Ref<boolean>,
): UseQueryReturnType<
  { nodes: KnowledgeNodeDTO[]; edges: KnowledgeEdgeDTO[] },
  Error
> {
  return useQuery({
    queryKey: datasetKeys.kgOverview(),
    queryFn: async () => {
      const { data } = await structuredDataApi.getKnowledgeGraph();
      return kgOverviewToDto({ nodes: data.nodes, edges: data.edges });
    },
    // TD-015 fix: lazy-load the overview payload only when the caller
    // explicitly enables the query (e.g. when the user expands the panel).
    enabled,
  });
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

interface UploadDatasetVars {
  formData: FormData;
  name: string;
}

function useUploadDatasetMutation(
  onSuccess: () => void,
): UseMutationReturnType<DatasetDTO, Error, UploadDatasetVars, unknown> {
  const qc = useQueryClient();
  return useMutation({
    // TD-015 fix: forward the user-supplied name as the second arg
    // (the backend reads it as a query parameter). TD-007's empty string
    // here silently dropped the dataset name and fell back to file.filename.
    mutationFn: ({ formData, name }) =>
      structuredDataApi.uploadDataset(formData, name).then((r) => r.data),
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
