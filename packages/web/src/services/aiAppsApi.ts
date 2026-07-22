/**
 * BUG-018 Slice 4: AI App 前端 service 改用共享 axios client（api.ts）。
 *
 * 复用 api.ts 已有的：
 * - 30s 超时
 * - 401 拦截 -> 清 token + 跳转 /login
 * - X-Tenant-ID 头
 * - 错误统一抛 Error（FastAPI detail 优先）
 *
 * 移除手写 fetch + localStorage.getItem('metaedu_token')，统一从 axios 拦截器取。
 */
import api from './api';

export interface AiAppPublic {
  id: string;
  code: string;
  name: string;
  description: string | null;
  category: string | null;
  icon: string | null;
  status: string;
  visibility: string;
  entry_type: string;
  route_path: string | null;
  external_url: string | null;
  required_capabilities: string[] | null;
  version: string;
  sort_order: number;
  tenant_id: string | null;
  is_platform: boolean;
  created_at: string;
  updated_at: string;
}

// 管理详情（含 token / owner / config_schema）—— 仅超管 ?scope=admin 返回。
// 字段类型合并到 AiAppPublic，所有字段 optional。
export interface AiAppAdmin extends AiAppPublic {
  owner: string | null;
  config_schema: Record<string, unknown> | null;
  share_token: string | null;
  api_token: string | null;
}

export interface AiAppListResponse {
  items: AiAppPublic[];
  total: number;
}

export interface AiAppListAdminResponse {
  items: AiAppAdmin[];
  total: number;
}

export interface ListParams {
  status?: string;
  include_archived?: boolean;
  /** 超管 ?scope=admin 返回 AiAppAdmin（含 token）。仅 super_admin 有效。 */
  admin_scope?: boolean;
}

export interface CreateAppPayload {
  code: string;
  name: string;
  description?: string | null;
  category?: string | null;
  icon?: string | null;
  status?: string;
  visibility?: string;
  entry_type?: string;
  route_path?: string | null;
  external_url?: string | null;
  config_schema?: Record<string, unknown> | null;
  required_capabilities?: string[] | null;
  owner?: string | null;
  version?: string;
  sort_order?: number;
}

export interface UpdateAppPayload {
  name?: string;
  description?: string | null;
  category?: string | null;
  icon?: string | null;
  status?: string;
  visibility?: string;
  entry_type?: string;
  route_path?: string | null;
  external_url?: string | null;
  config_schema?: Record<string, unknown> | null;
  required_capabilities?: string[] | null;
  owner?: string | null;
  version?: string;
  sort_order?: number;
}

function buildListParams(params: ListParams = {}): string {
  const qs = new URLSearchParams();
  if (params.status) qs.set('status', params.status);
  if (params.include_archived) qs.set('include_archived', 'true');
  if (params.admin_scope) qs.set('scope', 'admin');
  const query = qs.toString();
  return query ? `?${query}` : '';
}

export const aiAppsApi = {
  /** AC-5: 公开应用广场（匿名），仅 Published+public+is_platform 子集。 */
  listPublic(): Promise<AiAppListResponse> {
    return api.get<AiAppListResponse>('/ai-apps/public').then((r) => r.data);
  },

  /** BUG-018 Slice 4: 公开 share 链接解析（匿名），按 share_token 查。 */
  getByShareToken(token: string): Promise<AiAppPublic> {
    return api
      .get<AiAppPublic>(`/ai-apps/share/${encodeURIComponent(token)}`)
      .then((r) => r.data);
  },

  /** 管理列表。超管传 admin_scope=true 拿 AiAppAdmin 含 token。 */
  list(params: ListParams = {}): Promise<AiAppListResponse | AiAppListAdminResponse> {
    return api
      .get<AiAppListResponse | AiAppListAdminResponse>(
        `/ai-apps${buildListParams(params)}`,
      )
      .then((r) => r.data);
  },

  get(
    id: string,
    opts: { admin_scope?: boolean } = {},
  ): Promise<AiAppPublic | AiAppAdmin> {
    const qs = opts.admin_scope ? '?scope=admin' : '';
    return api
      .get<AiAppPublic | AiAppAdmin>(`/ai-apps/${id}${qs}`)
      .then((r) => r.data);
  },

  create(data: CreateAppPayload): Promise<AiAppPublic> {
    return api.post<AiAppPublic>('/ai-apps', data).then((r) => r.data);
  },

  update(id: string, data: UpdateAppPayload): Promise<AiAppPublic> {
    return api.put<AiAppPublic>(`/ai-apps/${id}`, data).then((r) => r.data);
  },

  archive(id: string): Promise<void> {
    return api.delete<void>(`/ai-apps/${id}`).then(() => undefined);
  },

  publish(id: string): Promise<AiAppPublic> {
    return api.post<AiAppPublic>(`/ai-apps/${id}/publish`).then((r) => r.data);
  },

  disable(id: string): Promise<AiAppPublic> {
    return api.post<AiAppPublic>(`/ai-apps/${id}/disable`).then((r) => r.data);
  },

  enable(id: string): Promise<AiAppPublic> {
    return api.post<AiAppPublic>(`/ai-apps/${id}/enable`).then((r) => r.data);
  },

  regenerateShareToken(id: string): Promise<{ token: string }> {
    return api
      .post<{ token: string }>(`/ai-apps/${id}/regenerate-share-token`)
      .then((r) => r.data);
  },

  regenerateApiToken(id: string): Promise<{ token: string }> {
    return api
      .post<{ token: string }>(`/ai-apps/${id}/regenerate-api-token`)
      .then((r) => r.data);
  },
};