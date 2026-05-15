import api from "./api";

// --- Types ---

export interface FolderDTO {
  id: string;
  tenant_id: string;
  name: string;
  parent_id: string | null;
  path: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
  children?: FolderDTO[];
}

export interface FileDTO {
  id: string;
  tenant_id: string;
  folder_id: string | null;
  filename: string;
  file_type: string;
  doc_type: string | null;
  file_size: number | null;
  tags: string[] | null;
  status: string;
  structured_data: Record<string, unknown> | null;
  uploaded_by: string;
  created_at: string;
  updated_at: string;
}

export interface ChunkDTO {
  id: string;
  file_id: string;
  chunk_index: number;
  content: string;
  section_title: string | null;
  section_path: string | null;
  char_start: number | null;
  char_end: number | null;
  has_embedding: boolean;
  created_at: string;
}

export interface TaskDTO {
  id: string;
  file_id: string | null;
  dataset_id: string | null;
  task_type: string;
  status: string;
  progress: number;
  error_message: string | null;
  label: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

// --- API ---

export const documentApi = {
  // Folders
  listFolders: () => api.get<FolderDTO[]>("/document/folders"),
  createFolder: (data: { name: string; parent_id?: string; sort_order?: number }) =>
    api.post<FolderDTO>("/document/folders", data),
  updateFolder: (id: string, data: { name?: string; sort_order?: number }) =>
    api.patch<FolderDTO>(`/document/folders/${id}`, data),
  deleteFolder: (id: string) => api.delete(`/document/folders/${id}`),
  moveFolder: (id: string, data: { parent_id: string | null }) =>
    api.patch<FolderDTO>(`/document/folders/${id}/move`, data),

  // Files
  listFiles: (params?: {
    folder_id?: string;
    tag?: string;
    status?: string;
    offset?: number;
    limit?: number;
  }) => api.get<FileDTO[]>("/document/files", { params }),
  uploadFile: (formData: FormData) =>
    api.post<FileDTO>("/document/files/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  getFile: (id: string) => api.get<FileDTO>(`/document/files/${id}`),
  deleteFile: (id: string) => api.delete(`/document/files/${id}`),
  updateFile: (id: string, data: { tags?: string[]; doc_type?: string; folder_id?: string }) =>
    api.patch<FileDTO>(`/document/files/${id}`, data),

  // Chunks
  listChunks: (fileId: string) => api.get<ChunkDTO[]>(`/document/files/${fileId}/chunks`),

  // Tasks
  listTasks: (fileId: string) => api.get<TaskDTO[]>(`/document/files/${fileId}/tasks`),
  retryTasks: (fileId: string) => api.post<TaskDTO[]>(`/document/files/${fileId}/retry`),
};
