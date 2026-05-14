import api from "./api";

export interface KnowledgeNodeDTO {
  id: string;
  tenant_id: string;
  title: string;
  description: string | null;
  domain: string;
  level: string;
  parent_id: string | null;
  path: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
}

export const knowledgeApi = {
  listNodes: (params?: { domain?: string; parent_id?: string }) =>
    api.get<KnowledgeNodeDTO[]>("/knowledge/nodes", { params }),
  getNode: (id: string) => api.get<KnowledgeNodeDTO>(`/knowledge/nodes/${id}`),
  createNode: (data: Partial<KnowledgeNodeDTO> & { title: string; domain: string; level: string }) =>
    api.post<KnowledgeNodeDTO>("/knowledge/nodes", data),
  updateNode: (id: string, data: Partial<KnowledgeNodeDTO>) =>
    api.patch<KnowledgeNodeDTO>(`/knowledge/nodes/${id}`, data),
  deleteNode: (id: string) => api.delete(`/knowledge/nodes/${id}`),
  search: (query: string, domain?: string) =>
    api.post("/knowledge/search", { query, domain, search_mode: "hybrid" }),
  getTree: (parentId: string) => api.get<KnowledgeNodeDTO[]>(`/knowledge/tree/${parentId}`),
};
