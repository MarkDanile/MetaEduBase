import api from "./api";
import type { TaskDTO } from "./document";

// --- Types ---

export interface DatasetDTO {
  id: string;
  tenant_id: string;
  name: string;
  description: string | null;
  column_names: string[] | null;
  column_types: string[] | null;
  row_count: number;
  source_file: string | null;
  tags: string[] | null;
  status: string;
  kg_status: string;
  sort_order: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface DatasetRowDTO {
  id: string;
  dataset_id: string;
  row_index: number;
  data: Record<string, unknown>;
  created_at: string;
}

export interface KGNode {
  id: string;
  title: string;
  description: string | null;
  domain: string;
  level: string;
  source_dataset_id: string | null;
}

export interface KGEdge {
  id: string;
  source_id: string;
  target_id: string;
  relation_type: string;
}

// --- API ---

export const structuredDataApi = {
  // Datasets
  listDatasets: (params?: {
    tag?: string;
    status?: string;
    offset?: number;
    limit?: number;
  }) => api.get<DatasetDTO[]>("/structured-data/datasets", { params }),
  uploadDataset: (formData: FormData) =>
    api.post<DatasetDTO>("/structured-data/datasets/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  getDataset: (id: string) => api.get<DatasetDTO>(`/structured-data/datasets/${id}`),
  deleteDataset: (id: string) => api.delete(`/structured-data/datasets/${id}`),
  updateDataset: (
    id: string,
    data: { name?: string; description?: string; tags?: string[]; sort_order?: number },
  ) => api.patch<DatasetDTO>(`/structured-data/datasets/${id}`, data),

  // Rows
  listRows: (datasetId: string, params?: { offset?: number; limit?: number }) =>
    api.get<DatasetRowDTO[]>(`/structured-data/datasets/${datasetId}/rows`, { params }),

  // Tasks
  listTasks: (datasetId: string) =>
    api.get<TaskDTO[]>(`/structured-data/datasets/${datasetId}/tasks`),
  retryTasks: (datasetId: string) =>
    api.post<TaskDTO[]>(`/structured-data/datasets/${datasetId}/retry`),

  // Knowledge Graph
  getKgStatus: () =>
    api.get<{ id: string; name: string; kg_status: string }[]>(
      "/structured-data/knowledge-graph/status",
    ),
  getKnowledgeGraph: () =>
    api.get<{ nodes: KGNode[]; edges: KGEdge[] }>("/structured-data/knowledge-graph"),
};
