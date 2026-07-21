/**
 * REQ-044 Task 4: MCP registry 前端 service.
 *
 * 后端契约见 packages/server-python/app/contexts/mcp_registry/interfaces/api/mcp_registry_router.py：
 * - POST   /api/v1/mcp-servers             - register (admin / data_admin / super_admin)
 * - GET    /api/v1/mcp-servers             - list (any authenticated user, own tenant)
 * - GET    /api/v1/mcp-servers/{id}        - detail (any authenticated user, own tenant)
 * - PATCH  /api/v1/mcp-servers/{id}        - update (admin roles)
 * - POST   /api/v1/mcp-servers/{id}/enable - enable + 可选连通探活 (admin roles)
 * - POST   /api/v1/mcp-servers/{id}/disable- disable (admin roles)
 * - DELETE /api/v1/mcp-servers/{id}        - soft delete (admin roles)
 * - GET    /api/v1/mcp-servers/{id}/invocations - 审计查询 (admin roles, 分页)
 *
 * 安全口径：DTO 只含 env-key 引用名 credential_ref，**绝不返回 secret**；
 * secret 仅存在于进程环境，调用瞬间解析注入 Authorization header。
 */
import api from "./api";

// --- Types ---

export type McpTransport = "streamable_http" | "sse";

export interface McpServerDTO {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  description: string | null;
  transport: string;
  server_url: string;
  credential_ref: string | null;
  allowed_roles: string[];
  enabled: boolean;
  timeout_ms: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** enable 响应：server DTO + 可选连通探活 warning（探活失败不阻塞启用）。 */
export interface McpServerEnableDTO extends McpServerDTO {
  warning: string | null;
}

export interface InvocationDTO {
  id: string;
  server_id: string;
  server_code: string;
  tool_name: string;
  caller_type: string;
  caller_user_id: string | null;
  params_digest: string | null;
  response_digest: string | null;
  ok: boolean;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number;
  created_at: string;
}

export interface InvocationListResponse {
  items: InvocationDTO[];
  total: number;
  limit: number;
  offset: number;
}

export interface McpServerCreate {
  code: string;
  name: string;
  server_url: string;
  transport: McpTransport;
  /** env-key 引用名（如 QCC_MCP_TOKEN），只存引用名，绝不填真实 token。 */
  credential_ref?: string;
  allowed_roles?: string[];
  description?: string;
  timeout_ms?: number;
}

export interface McpServerUpdate {
  name?: string;
  description?: string;
  transport?: McpTransport;
  server_url?: string;
  credential_ref?: string;
  allowed_roles?: string[];
  timeout_ms?: number;
}

export interface ListInvocationsParams {
  limit?: number;
  offset?: number;
}

// --- API ---

export async function listMcpServers(): Promise<McpServerDTO[]> {
  const res = await api.get<McpServerDTO[]>("/mcp-servers");
  return res.data;
}

export async function createMcpServer(req: McpServerCreate): Promise<McpServerDTO> {
  const res = await api.post<McpServerDTO>("/mcp-servers", req);
  return res.data;
}

export async function getMcpServer(id: string): Promise<McpServerDTO> {
  const res = await api.get<McpServerDTO>(`/mcp-servers/${id}`);
  return res.data;
}

export async function updateMcpServer(
  id: string,
  req: McpServerUpdate,
): Promise<McpServerDTO> {
  const res = await api.patch<McpServerDTO>(`/mcp-servers/${id}`, req);
  return res.data;
}

/**
 * 启用 server。默认 probe=true 触发真实连通校验；探活失败不阻塞启用，
 * 仅以 warning 返回（spec §4.5）。UI 应把非空 warning 展示给用户。
 */
export async function enableMcpServer(
  id: string,
  probe = true,
): Promise<McpServerEnableDTO> {
  const res = await api.post<McpServerEnableDTO>(
    `/mcp-servers/${id}/enable`,
    null,
    { params: { probe } },
  );
  return res.data;
}

export async function disableMcpServer(id: string): Promise<McpServerDTO> {
  const res = await api.post<McpServerDTO>(`/mcp-servers/${id}/disable`);
  return res.data;
}

export async function deleteMcpServer(id: string): Promise<void> {
  await api.delete(`/mcp-servers/${id}`);
}

export async function listInvocations(
  id: string,
  params: ListInvocationsParams = {},
): Promise<InvocationListResponse> {
  const res = await api.get<InvocationListResponse>(
    `/mcp-servers/${id}/invocations`,
    { params },
  );
  return res.data;
}
