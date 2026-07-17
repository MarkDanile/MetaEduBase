/**
 * REQ-052 Task 6 + REQ-054 Task 8 + BUG-015: 数据查询 API 客户端 + 类型定义。
 *
 * 与后端 `/api/v1/data-query/ask` 端点对齐。
 * axios 实例统一从 `./api` 引入，避免使用不存在的 `@/utils/http` 路径。
 *
 * REQ-054 加 `catalog_id` 字段：按 (catalog_id, entity_type) 双键路由到对应语义模型。
 *
 * BUG-015: `business_purpose` 改为可选，`confirmed_company_name` 删除 ——
 * 查询面板不再要求用户每次重复输入这两个字段，业务背景由问题本身驱动。
 */
import api from "./api";

export interface AskRequest {
  catalog_id: string;
  entity_type: string;
  question: string;
  business_purpose?: string;
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