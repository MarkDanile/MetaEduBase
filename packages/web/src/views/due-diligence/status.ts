/**
 * REQ-046 / APP-005: 背调任务 / 报告状态 -> 中文标签 + ui-tag 类。
 * 与后端状态机对齐：
 * - DdTask:   subject_pending -> subject_confirmed -> running -> review / archived | failed
 * - DdReport: draft -> confirmed -> archived
 * 纯展示映射，不改写业务。
 */

const TASK_STATUS: Record<string, { label: string; tag: string }> = {
  subject_pending: { label: "待确认主体", tag: "ui-tag-grey" },
  subject_confirmed: { label: "主体已确认", tag: "ui-tag-blue" },
  running: { label: "背调中", tag: "ui-tag-blue" },
  review: { label: "待人工复核", tag: "ui-tag-amber" },
  archived: { label: "已归档", tag: "ui-tag-green" },
  failed: { label: "失败", tag: "ui-tag-red" },
};

const REPORT_STATUS: Record<string, { label: string; tag: string }> = {
  draft: { label: "草案", tag: "ui-tag-amber" },
  confirmed: { label: "已确认", tag: "ui-tag-green" },
  archived: { label: "已归档", tag: "ui-tag-grey" },
};

export function taskStatus(status: string): { label: string; tag: string } {
  return TASK_STATUS[status] ?? { label: status, tag: "ui-tag-grey" };
}

export function reportStatus(status: string): { label: string; tag: string } {
  return REPORT_STATUS[status] ?? { label: status, tag: "ui-tag-grey" };
}
