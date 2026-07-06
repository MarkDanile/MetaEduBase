/**
 * REQ-052 Task 6: 数据查询 API 客户端 + 类型定义。
 *
 * 与后端 `/api/v1/data-query/ask` 端点对齐。
 * axios 实例统一从 `./api` 引入，避免使用不存在的 `@/utils/http` 路径。
 */
import api from "./api";

export interface AskRequest {
  entity_type: string;
  question: string;
  business_purpose: string;
  confirmed_company_name?: string;
}

export interface AskResponse {
  ok: boolean;
  query_plan?: Record<string, unknown>;
  result_rows?: Array<Record<string, unknown>>;
  result_count?: number;
  summary?: string;
  metric_values?: Record<string, { value: unknown; label: string; aggregation: string }>;
  filters_applied?: Record<string, unknown>;
  caveats?: string[];
  confidence?: string;
  duration_ms?: number;
  errors?: string[];
  suggestion?: string;
}

export async function ask(req: AskRequest): Promise<AskResponse> {
  const res = await api.post<AskResponse>("/data-query/ask", req);
  return res.data;
}