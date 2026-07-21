/**
 * REQ-046 / APP-005: 企业 360 背调工作台前端 service.
 *
 * 后端契约见 packages/server-python/app/contexts/due_diligence/interfaces/api/dd_router.py：
 * - POST /api/v1/dd/tasks                       - 创建任务 (subject_pending)
 * - GET  /api/v1/dd/tasks                       - 本租户任务列表
 * - GET  /api/v1/dd/tasks/{id}                  - 任务详情
 * - POST /api/v1/dd/tasks/{id}/resolve-subject  - 主体锚定 -> 候选
 * - POST /api/v1/dd/tasks/{id}/confirm-subject  - 确认候选 -> subject_confirmed
 * - POST /api/v1/dd/tasks/{id}/run              - 运行背调 -> 报告草案 (AC-1 未确认 422)
 * - GET  /api/v1/dd/reports/{id}                - 报告详情 (含 report_json + markdown)
 * - POST /api/v1/dd/reports/{id}/confirm        - 人工确认锁版
 * - POST /api/v1/dd/reports/{id}/archive        - 归档
 * - GET  /api/v1/dd/reports/{id}/evidence       - 证据账本 (§4.7)
 *
 * 安全口径：report_json / report_markdown 含企业敏感事实，仅返回给归属租户的业务
 * caller；前端只在报告视图内展示，不缓存、不打印到控制台。evidence 只含非敏感
 * summary + ref_id（审计/问数 id），不含原始事实。
 */
import api from "./api";

// --- Types ---

export interface DdTask {
  id: string;
  tenant_id: string;
  title: string;
  subject_query: string;
  status: string;
  confirmed_subject: { company_name: string; credit_code: string | null } | null;
  created_by: string;
}

export interface DdTaskCreate {
  title: string;
  subject_query: string;
}

export interface SubjectCandidate {
  company_name: string;
  credit_code: string | null;
}

export interface SubjectConfirm {
  company_name: string;
  credit_code?: string | null;
}

/** §4.6 七键结构化报告。 */
export interface DdReportJson {
  summary?: string[];
  external_facts?: string[];
  internal_facts?: string[];
  risk_watch_items?: string[];
  human_review_items?: string[];
  evidence_refs?: Array<{
    source_step: string;
    evidence_type: string;
    ref_id: string;
  }>;
  report_sections?: Array<{ title: string; content: string }>;
}

export interface DdReport {
  id: string;
  task_id: string;
  version: number;
  status: string;
  report_json: DdReportJson;
  report_markdown: string;
  skill_execution_audit_id: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

/** §4.7 证据账单行 - 非敏感摘要 + 来源 ref。 */
export interface DdEvidence {
  id: string;
  evidence_type: string;
  ref_id: string | null;
  section: string | null;
  summary: string | null;
}

// --- API: tasks ---

export async function createTask(req: DdTaskCreate): Promise<DdTask> {
  const res = await api.post<DdTask>("/dd/tasks", req);
  return res.data;
}

export async function listTasks(): Promise<DdTask[]> {
  const res = await api.get<DdTask[]>("/dd/tasks");
  return res.data;
}

export async function getTask(id: string): Promise<DdTask> {
  const res = await api.get<DdTask>(`/dd/tasks/${id}`);
  return res.data;
}

export async function resolveSubject(id: string): Promise<SubjectCandidate[]> {
  const res = await api.post<SubjectCandidate[]>(`/dd/tasks/${id}/resolve-subject`);
  return res.data;
}

export async function confirmSubject(
  id: string,
  req: SubjectConfirm,
): Promise<DdTask> {
  const res = await api.post<DdTask>(`/dd/tasks/${id}/confirm-subject`, req);
  return res.data;
}

export async function runTask(id: string): Promise<DdReport> {
  const res = await api.post<DdReport>(`/dd/tasks/${id}/run`);
  return res.data;
}

// --- API: reports + evidence ---

export async function getReport(id: string): Promise<DdReport> {
  const res = await api.get<DdReport>(`/dd/reports/${id}`);
  return res.data;
}

export async function confirmReport(id: string): Promise<DdReport> {
  const res = await api.post<DdReport>(`/dd/reports/${id}/confirm`);
  return res.data;
}

export async function archiveReport(id: string): Promise<DdReport> {
  const res = await api.post<DdReport>(`/dd/reports/${id}/archive`);
  return res.data;
}

export async function listEvidence(id: string): Promise<DdEvidence[]> {
  const res = await api.get<DdEvidence[]>(`/dd/reports/${id}/evidence`);
  return res.data;
}
