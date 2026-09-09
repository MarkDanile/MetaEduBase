/**
 * REQ-042 WS-S1: Agent Workspace 只读三栏 shell 的 service 层。
 *
 * 后端契约（real PG 已落地，本 Slice 只读消费，不开放 submit-turn）：
 * - Conversation/Message: packages/server-python/app/contexts/agent_workspace/interfaces/api/router.py
 *   - POST   /agent-workspace/conversations            幂等创建（201 新建 / 200 幂等重放）
 *   - GET    /agent-workspace/conversations            keyset list（state/q/cursor/limit，无 offset）
 *   - GET    /agent-workspace/conversations/{id}       tenant+owner visibility
 *   - PATCH  /agent-workspace/conversations/{id}       rename（必须 If-Match）
 *   - PUT    /agent-workspace/conversations/{id}/pin   user-scoped pin
 *   - DELETE /agent-workspace/conversations/{id}/pin   unpin
 *   - POST   /agent-workspace/conversations/{id}/archive  CAS archive（If-Match）
 *   - POST   /agent-workspace/conversations/{id}/restore  archived→active（If-Match）
 *   - DELETE /agent-workspace/conversations/{id}       202 soft delete（If-Match）
 *   - GET    /agent-workspace/conversations/{id}/messages  before_seq/after_seq keyset 分页
 * - Run 只读: packages/server-python/app/contexts/agent_execution/interfaces/api/router.py
 *   - GET    /agent-runs/{run_id}                       owner-scoped 终态事实（本 Slice 唯一允许的 run endpoint）
 *
 * 严禁（WS-S1 边界）：submit-turn、/ai/chat/evidence、SSE/EventSource、cancel/stop、
 * Approval/HumanInput/Tool/Artifact/run-scoped Evidence、SkillRunner、turn-dispatch retry/abandon。
 *
 * 约定：路径不带 /api/v1 前缀（axios baseURL 已含）；tenant/owner 由请求拦截器注入，函数签名不收 token/tenant。
 * 错误不归一化为 Error：原始 AxiosError 冒泡，消费方用 parseApiError 读取 detail.code 分支。
 */
import api from "./api";

// --- Types（镜像后端 DTO，字段 snake_case，可空用 `| null`）---

export type ConversationState = "active" | "archived" | "deleted";
export type ConversationTitleSource = "none" | "auto" | "user";

export interface ConversationDTO {
  id: string;
  title: string | null;
  title_source: ConversationTitleSource | string;
  state: ConversationState | string;
  parent_conversation_id: string | null;
  forked_from_message_id: string | null;
  last_activity_at: string;
  pinned_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: ConversationDTO[];
  next_cursor: string | null;
}

export type MessageKind = "user_input" | "assistant_output" | "system_notice";
export type MessageAuthorType = "user" | "agent" | "system";
export type MessageContentState = "visible" | "redacted" | "superseded";
export type MessagePartType = "text" | "resource_ref";

export interface MessagePartDTO {
  id: string;
  part_seq: number;
  type: MessagePartType | string;
  text: string | null;
  format: string | null;
  resource_id: string | null;
  media_type: string | null;
  display_name: string | null;
  classification: string;
}

export interface MessageDTO {
  id: string;
  seq: number;
  kind: MessageKind | string;
  author_type: MessageAuthorType | string;
  author_id: string | null;
  requested_run_id: string | null;
  requested_run_queue_seq: number | null;
  dispatch_state: string | null;
  origin_run_id: string | null;
  output_ordinal: number | null;
  reply_to_message_id: string | null;
  content_state: MessageContentState | string;
  created_at: string;
  parts: MessagePartDTO[];
}

export interface MessageListResponse {
  items: MessageDTO[];
  has_more: boolean;
}

export type RunStatus =
  | "queued"
  | "starting"
  | "running"
  | "waiting_input"
  | "waiting_approval"
  | "resume_required"
  | "cancelling"
  | "completed"
  | "failed"
  | "cancelled"
  | "expired";

export type OutputPublishState =
  | "not_required"
  | "pending"
  | "published"
  | "dead_letter"
  | "suppressed";

export interface AgentRunDTO {
  id: string;
  conversation_id: string;
  queue_seq: number;
  root_input_message_id: string;
  parent_run_id: string | null;
  agent_definition_version_id: string;
  runtime_profile_id: string;
  runtime_binding_id: string | null;
  status: RunStatus | string;
  status_revision: number;
  first_available_event_seq: number;
  last_event_seq: number;
  event_log_complete: boolean;
  queued_at: string;
  started_at: string | null;
  ended_at: string | null;
  terminal_code: string | null;
  terminal_reason: string | null;
  terminal_result_digest: string | null;
  terminal_output_digest: string | null;
  terminal_output_size: number | null;
  terminal_output_media_type: string | null;
  terminal_output_classification: string | null;
  terminal_message_id: string | null;
  output_publish_state: OutputPublishState | string;
  usage: Record<string, number>;
  pending_input_request_count: number;
  pending_approval_count: number;
  created_at: string;
  updated_at: string;
}

/** 终态集合（后端 TERMINAL_RUN_STATUSES）；queued 既非终态也非 active，按进行中诚实展示。 */
export const TERMINAL_RUN_STATUSES: ReadonlySet<string> = new Set([
  "completed",
  "failed",
  "cancelled",
  "expired",
]);

// --- 请求参数 ---

export interface ConversationListParams {
  state?: "active" | "archived";
  q?: string;
  cursor?: string;
  limit?: number;
}

export interface ConversationCreateRequest {
  conversation_id?: string;
  title?: string;
}

export interface MessageListParams {
  before_seq?: number;
  after_seq?: number;
  limit?: number;
}

// --- 错误解析（兼容三种 detail 形状：{code,message} 对象 / 字符串(401) / FastAPI 422 数组）---

export interface ApiErrorInfo {
  status?: number;
  code?: string;
  message: string;
}

interface AxiosLikeError {
  response?: {
    status?: number;
    data?: { detail?: unknown };
  };
  message?: string;
}

/**
 * 统一错误解析器。先判 detail 类型：
 * - 对象 {code, message}：业务错误（读 code 分支，不匹配 message 文案）。
 * - 字符串：401 等（如“无效的认证令牌”）。
 * - 数组：FastAPI 请求校验 422（[{loc, msg, type}]）。
 * - 其他：fallback。
 */
export function parseApiError(e: unknown, fallback = "操作失败"): ApiErrorInfo {
  const err = e as AxiosLikeError;
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  if (detail != null) {
    if (typeof detail === "string") {
      return { status, message: detail };
    }
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: unknown } | undefined;
      const msg = first && typeof first.msg === "string" ? first.msg : fallback;
      return { status, message: msg };
    }
    if (typeof detail === "object") {
      const d = detail as { code?: unknown; message?: unknown };
      return {
        status,
        code: typeof d.code === "string" ? d.code : undefined,
        message: typeof d.message === "string" ? d.message : fallback,
      };
    }
  }
  return { status, message: typeof err?.message === "string" ? err.message : fallback };
}

// --- API: Conversation ---

const CONVERSATIONS = "/agent-workspace/conversations";

export async function listConversations(
  params: ConversationListParams = {},
): Promise<ConversationListResponse> {
  const res = await api.get<ConversationListResponse>(CONVERSATIONS, {
    params: {
      state: params.state ?? "active",
      ...(params.q ? { q: params.q } : {}),
      ...(params.cursor ? { cursor: params.cursor } : {}),
      ...(params.limit ? { limit: params.limit } : {}),
    },
  });
  return res.data;
}

export async function createConversation(
  req: ConversationCreateRequest = {},
): Promise<ConversationDTO> {
  const res = await api.post<ConversationDTO>(CONVERSATIONS, req);
  return res.data;
}

export async function getConversation(
  id: string,
  opts: { includeDeleted?: boolean } = {},
): Promise<ConversationDTO> {
  const res = await api.get<ConversationDTO>(`${CONVERSATIONS}/${id}`, {
    params: opts.includeDeleted ? { include_deleted: true } : {},
  });
  return res.data;
}

function ifMatchHeaders(revision: number): { headers: { "If-Match": string } } {
  return { headers: { "If-Match": String(revision) } };
}

export async function renameConversation(
  id: string,
  title: string,
  revision: number,
): Promise<ConversationDTO> {
  const res = await api.patch<ConversationDTO>(
    `${CONVERSATIONS}/${id}`,
    { title },
    ifMatchHeaders(revision),
  );
  return res.data;
}

export async function pinConversation(id: string): Promise<ConversationDTO> {
  const res = await api.put<ConversationDTO>(`${CONVERSATIONS}/${id}/pin`);
  return res.data;
}

export async function unpinConversation(id: string): Promise<ConversationDTO> {
  const res = await api.delete<ConversationDTO>(`${CONVERSATIONS}/${id}/pin`);
  return res.data;
}

export async function archiveConversation(
  id: string,
  revision: number,
): Promise<ConversationDTO> {
  const res = await api.post<ConversationDTO>(
    `${CONVERSATIONS}/${id}/archive`,
    {},
    ifMatchHeaders(revision),
  );
  return res.data;
}

export async function restoreConversation(
  id: string,
  revision: number,
): Promise<ConversationDTO> {
  const res = await api.post<ConversationDTO>(
    `${CONVERSATIONS}/${id}/restore`,
    {},
    ifMatchHeaders(revision),
  );
  return res.data;
}

export async function deleteConversation(
  id: string,
  revision: number,
): Promise<ConversationDTO> {
  const res = await api.delete<ConversationDTO>(
    `${CONVERSATIONS}/${id}`,
    ifMatchHeaders(revision),
  );
  return res.data;
}

// --- API: Message history ---

export async function listMessages(
  conversationId: string,
  params: MessageListParams = {},
): Promise<MessageListResponse> {
  const res = await api.get<MessageListResponse>(
    `${CONVERSATIONS}/${conversationId}/messages`,
    {
      params: {
        ...(params.before_seq != null ? { before_seq: params.before_seq } : {}),
        ...(params.after_seq != null ? { after_seq: params.after_seq } : {}),
        ...(params.limit ? { limit: params.limit } : {}),
      },
    },
  );
  return res.data;
}

// --- API: Run（只读，本 Slice 唯一允许的 run endpoint）---

export async function getRun(runId: string): Promise<AgentRunDTO> {
  const res = await api.get<AgentRunDTO>(`/agent-runs/${runId}`);
  return res.data;
}
