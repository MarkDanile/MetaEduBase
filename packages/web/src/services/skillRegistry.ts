/**
 * REQ-045 Task 4: Skill registry 前端 service.
 *
 * 后端契约见 packages/server-python/app/contexts/skill_registry/interfaces/api/skill_registry_router.py：
 * - POST   /api/v1/skills                - register (admin / data_admin / super_admin)
 * - GET    /api/v1/skills                - list (any authenticated user, own tenant)
 * - GET    /api/v1/skills/{id}           - detail incl. sop_template (any user, own tenant)
 * - PATCH  /api/v1/skills/{id}           - update metadata / allowed_roles (admin roles)
 * - POST   /api/v1/skills/{id}/enable    - enable this version (admin roles)
 * - POST   /api/v1/skills/{id}/disable   - disable this version (admin roles)
 * - DELETE /api/v1/skills/{id}           - soft delete (admin roles)
 * - GET    /api/v1/skills/{id}/executions- 执行审计查询 (admin roles, 分页)
 * - POST   /api/v1/skills/{id}/run       - 试运行 (admin roles)
 *
 * 安全口径：DTO 只含声明式 SOP 模板正文（metadata + steps + report 骨架），
 * **绝不携带 secret**；sop_template 设计上就不含凭证。`/run` 响应的 report
 * 含企业敏感事实，仅返回给管理角色 caller，前端只在试运行 modal 内展示，
 * 不缓存、不打印到控制台。
 */
import api from "./api";

// --- Types ---

/** 注册 Skill（声明式 SOP 模板，无 secret）。 */
export interface SkillDTO {
  id: string;
  tenant_id: string;
  code: string;
  version: string;
  name: string;
  description: string | null;
  sop_template: string;
  source_ref: string | null;
  allowed_roles: string[];
  enabled: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface SkillCreate {
  /** `^[a-z][a-z0-9_]*$`，如 `enterprise_360_dd` */
  code: string;
  /** 语义化版本 `^\d+\.\d+\.\d+$`，如 `1.0.0` */
  version: string;
  name: string;
  /** 声明式 SOP 模板 YAML 正文；**绝不填 secret** */
  sop_template: string;
  description?: string;
  source_ref?: string;
  allowed_roles?: string[];
}

export interface SkillUpdate {
  name?: string;
  description?: string;
  source_ref?: string;
  allowed_roles?: string[];
  // sop_template 改动须走新版本；后端接受该字段只为显式拒绝（422）。
  sop_template?: string;
}

/** 执行审计行 - digest only，不含原始 subject / facts / report。 */
export interface ExecutionDTO {
  id: string;
  skill_id: string;
  skill_code: string;
  skill_version: string;
  caller_type: string;
  caller_user_id: string | null;
  subject_digest: string | null;
  steps_digest: string | null;
  report_digest: string | null;
  ok: boolean;
  error_code: string | null;
  error_message: string | null;
  duration_ms: number;
  created_at: string;
}

export interface ExecutionListResponse {
  items: ExecutionDTO[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListExecutionsParams {
  limit?: number;
  offset?: number;
}

/** 单步摘要 - digest only，无原始 facts。 */
export interface SkillRunStepDTO {
  id: string;
  ok: boolean;
  digest: string | null;
}

/** 试运行产物：report 含企业敏感事实，仅展示给管理角色 caller。 */
export interface SkillRunResponse {
  report: string;
  execution_audit_id: string;
  duration_ms: number;
  steps: SkillRunStepDTO[];
}

export interface SkillRunRequest {
  version: string;
  /** 执行主体（如 {company_name: "..."}），整体传给 runner */
  subject: Record<string, unknown>;
}

// --- API ---

export async function listSkills(): Promise<SkillDTO[]> {
  const res = await api.get<SkillDTO[]>("/skills");
  return res.data;
}

export async function getSkill(id: string): Promise<SkillDTO> {
  const res = await api.get<SkillDTO>(`/skills/${id}`);
  return res.data;
}

export async function createSkill(req: SkillCreate): Promise<SkillDTO> {
  const res = await api.post<SkillDTO>("/skills", req);
  return res.data;
}

export async function updateSkill(id: string, req: SkillUpdate): Promise<SkillDTO> {
  const res = await api.patch<SkillDTO>(`/skills/${id}`, req);
  return res.data;
}

export async function enableSkill(id: string): Promise<SkillDTO> {
  const res = await api.post<SkillDTO>(`/skills/${id}/enable`);
  return res.data;
}

export async function disableSkill(id: string): Promise<SkillDTO> {
  const res = await api.post<SkillDTO>(`/skills/${id}/disable`);
  return res.data;
}

export async function deleteSkill(id: string): Promise<void> {
  await api.delete(`/skills/${id}`);
}

export async function listExecutions(
  id: string,
  params: ListExecutionsParams = {},
): Promise<ExecutionListResponse> {
  const res = await api.get<ExecutionListResponse>(`/skills/${id}/executions`, {
    params,
  });
  return res.data;
}

export async function runSkill(
  id: string,
  req: SkillRunRequest,
): Promise<SkillRunResponse> {
  const res = await api.post<SkillRunResponse>(`/skills/${id}/run`, req);
  return res.data;
}
