import api from "./api";

export interface TableColumn {
  key: string;
  label: string;
  type: "text" | "textarea" | "number";
  width?: string;
}

export interface Field {
  id?: string;
  key: string;
  label: string;
  type: "text" | "textarea" | "number" | "object" | "table" | "array";
  description?: string;
  children?: Field[];
  columns?: TableColumn[];
  items?: Field[];
}

export interface Template {
  id: string;
  name: string;
  doc_types: string[];
  fields: Field[];
  ai_prompt: string | null;
  ai_context: string | null;
  source_file_id: string | null;
  created_at: string;
  updated_at: string;
}

export const templateApi = {
  list() {
    return api.get<Template[]>("/templates");
  },
  get(id: string) {
    return api.get<Template>(`/templates/${id}`);
  },
  create(data: Omit<Template, "id" | "created_at" | "updated_at">) {
    return api.post<Template>("/templates", data);
  },
  update(id: string, data: Partial<Template>) {
    return api.put<Template>(`/templates/${id}`, data);
  },
  delete(id: string) {
    return api.delete(`/templates/${id}`);
  },
  initByAI(docType: string, sourceFileId?: string, aiContext?: string) {
    return api.post<{ fields: Field[] }>(
      "/templates/init-by-ai",
      {
        doc_type: docType,
        source_file_id: sourceFileId,
        ai_context: aiContext,
      },
      {
        timeout: 120000,
      }
    );
  },
  checkDocType(docType: string) {
    return api.get<{ doc_type: string; used: boolean; templates: { id: string; name: string }[] }>(
      `/templates/check-doc-type?doc_type=${encodeURIComponent(docType)}`
    );
  },
};