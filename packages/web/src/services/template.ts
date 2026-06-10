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
  // REQ-002-4: schema evolution + deprecation
  schema_version: number;
  is_deprecated: boolean;
  deprecated_at: string | null;
  deprecated_reason: string | null;
}

// REQ-002-2: clone / version / export types

export interface CloneTemplateRequest {
  name: string;
  doc_types: string[];
  source_file_id?: string | null;
}

export interface TemplateVersion {
  version_number: number;
  name: string;
  snapshot_at: string;
  schema_version: number;
  doc_types: string[];
}

export interface TemplateVersionDetail extends TemplateVersion {
  fields: Field[];
  ai_prompt: string | null;
  ai_context: string | null;
}

export interface TemplateExport {
  format: string;
  template: {
    name: string;
    doc_types: string[];
    fields: Field[];
    ai_prompt: string | null;
    ai_context: string | null;
  };
  schema_version: number;
  exported_at: string;
}

// REQ-002-4: deprecation + schema bump types
export interface DeprecateRequest {
  reason: string;
}

export const templateApi = {
  list(includeDeprecated = false) {
    const qs = includeDeprecated ? "?include_deprecated=true" : "";
    return api.get<Template[]>(`/templates${qs}`);
  },
  get(id: string) {
    return api.get<Template>(`/templates/${id}`);
  },
  create(data: Omit<Template, "id" | "created_at" | "updated_at" | "schema_version" | "is_deprecated" | "deprecated_at" | "deprecated_reason">) {
    return api.post<Template>("/templates", data);
  },
  update(id: string, data: Partial<Template> & { force_schema_bump?: boolean }) {
    return api.put<Template>(`/templates/${id}`, data);
  },
  delete(id: string) {
    return api.delete(`/templates/${id}`);
  },
  // REQ-002-4: deprecation lifecycle
  deprecate(id: string, data: DeprecateRequest) {
    return api.post<Template>(`/templates/${id}/deprecate`, data);
  },
  undeprecate(id: string) {
    return api.post<Template>(`/templates/${id}/undeprecate`);
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
  // REQ-002-2: clone / version / export / import
  clone(id: string, data: CloneTemplateRequest) {
    return api.post<Template>(`/templates/${id}/clone`, data);
  },
  listVersions(id: string, limit = 20, offset = 0) {
    return api.get<TemplateVersion[]>(
      `/templates/${id}/versions?limit=${limit}&offset=${offset}`
    );
  },
  getVersion(id: string, versionNumber: number) {
    return api.get<TemplateVersionDetail>(
      `/templates/${id}/versions/${versionNumber}`
    );
  },
  rollback(id: string, versionNumber: number) {
    return api.post<Template>(`/templates/${id}/rollback/${versionNumber}`);
  },
  export(id: string) {
    return api.get<TemplateExport>(`/templates/${id}/export`);
  },
  import(data: { template: Record<string, unknown>; name_override?: string }) {
    return api.post<Template>("/templates/import", data);
  },
};