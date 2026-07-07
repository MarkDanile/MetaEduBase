/**
 * REQ-054 Task 7: 前端 catalog（数据库）service.
 *
 * 后端契约见 packages/server-python/app/contexts/structured_data/interfaces/api/catalog_router.py：
 * - GET    /api/v1/catalogs       — list
 * - POST   /api/v1/catalogs       — create
 * - GET    /api/v1/catalogs/{id}  — get one
 * - PATCH  /api/v1/catalogs/{id}  — update
 * - DELETE /api/v1/catalogs/{id}  — delete
 *
 * UI 上「数据库」对应 code 层的 `catalog`（避免与 PostgreSQL database 概念冲突）。
 */
import api from "./api";

// --- Types ---

export interface CatalogDTO {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  entity_types: string[];
  default_business_purpose: string | null;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CatalogCreate {
  code: string;
  name: string;
  entity_types: string[];
  description?: string;
  icon?: string;
  color?: string;
  default_business_purpose?: string;
}

export interface CatalogUpdate {
  name?: string;
  description?: string;
  icon?: string;
  color?: string;
  entity_types?: string[];
  default_business_purpose?: string;
}

// --- API ---

export async function listCatalogs(): Promise<CatalogDTO[]> {
  const res = await api.get<CatalogDTO[]>("/catalogs");
  return res.data;
}

export async function createCatalog(req: CatalogCreate): Promise<CatalogDTO> {
  const res = await api.post<CatalogDTO>("/catalogs", req);
  return res.data;
}

export async function getCatalog(id: string): Promise<CatalogDTO> {
  const res = await api.get<CatalogDTO>(`/catalogs/${id}`);
  return res.data;
}

export async function updateCatalog(
  id: string,
  req: CatalogUpdate,
): Promise<CatalogDTO> {
  const res = await api.patch<CatalogDTO>(`/catalogs/${id}`, req);
  return res.data;
}

export async function deleteCatalog(id: string): Promise<void> {
  await api.delete(`/catalogs/${id}`);
}