const API_BASE = '/api/v1/ai-apps';

export interface AiAppResponse {
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
  config_schema: Record<string, unknown> | null;
  required_capabilities: string[] | null;
  owner: string | null;
  version: string;
  sort_order: number;
  tenant_id: string | null;
  share_token: string | null;
  api_token: string | null;
  created_at: string;
  updated_at: string;
}

export interface AiAppListResponse {
  items: AiAppResponse[];
  total: number;
}

export interface ListParams {
  status?: string;
  tenant_id?: string;
  include_archived?: boolean;
}

async function getToken(): Promise<string | null> {
  return localStorage.getItem('metaedu_token');
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText })) as { detail: string };
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json();
}

export const aiAppsApi = {
  list(params: ListParams = {}): Promise<AiAppListResponse> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.tenant_id) qs.set('tenant_id', params.tenant_id);
    if (params.include_archived) qs.set('include_archived', 'true');
    const query = qs.toString();
    return request<AiAppListResponse>(query ? `?${query}` : '');
  },

  get(id: string): Promise<AiAppResponse> {
    return request<AiAppResponse>(`/${id}`);
  },

  create(data: Partial<AiAppResponse>): Promise<AiAppResponse> {
    return request<AiAppResponse>('', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  update(id: string, data: Partial<AiAppResponse>): Promise<AiAppResponse> {
    return request<AiAppResponse>(`/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  archive(id: string): Promise<void> {
    return request<void>(`/${id}`, { method: 'DELETE' });
  },

  publish(id: string): Promise<AiAppResponse> {
    return request<AiAppResponse>(`/${id}/publish`, { method: 'POST' });
  },

  disable(id: string): Promise<AiAppResponse> {
    return request<AiAppResponse>(`/${id}/disable`, { method: 'POST' });
  },

  enable(id: string): Promise<AiAppResponse> {
    return request<AiAppResponse>(`/${id}/enable`, { method: 'POST' });
  },

  regenerateShareToken(id: string): Promise<{ token: string }> {
    return request<{ token: string }>(`/${id}/regenerate-share-token`, { method: 'POST' });
  },

  regenerateApiToken(id: string): Promise<{ token: string }> {
    return request<{ token: string }>(`/${id}/regenerate-api-token`, { method: 'POST' });
  },
};
