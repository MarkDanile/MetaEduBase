/**
 * REQ-042 WS-S1: Workspace 只读 shell 的状态 -> 中文标签 + ui-tag 类。
 *
 * 纯展示映射，不改写业务。只使用 components.css 真实定义的 tag 变体
 * （blue/green/amber/purple）+ 基础 `.ui-tag`（无填充，作 muted/中性态）；
 * 不引用未定义的 ui-tag-red/grey（会静默退化为无填充）。
 *
 * 与后端对齐：
 * - Run.status: 11 值（queued..expired），终态 = completed/failed/cancelled/expired
 * - Conversation.state: active/archived/deleted
 * - Message.kind/author_type/content_state、Run.output_publish_state
 */

export interface StatusDisplay {
  label: string;
  tag: string;
}

const RUN_STATUS: Record<string, StatusDisplay> = {
  queued: { label: "排队中", tag: "ui-tag-blue" },
  starting: { label: "启动中", tag: "ui-tag-blue" },
  running: { label: "运行中", tag: "ui-tag-blue" },
  waiting_input: { label: "等待输入", tag: "ui-tag-purple" },
  waiting_approval: { label: "等待审批", tag: "ui-tag-purple" },
  resume_required: { label: "待恢复", tag: "ui-tag-purple" },
  cancelling: { label: "取消中", tag: "ui-tag-purple" },
  completed: { label: "已完成", tag: "ui-tag-green" },
  failed: { label: "失败", tag: "ui-tag-amber" },
  cancelled: { label: "已取消", tag: "ui-tag" },
  expired: { label: "已过期", tag: "ui-tag" },
};

const CONVERSATION_STATE: Record<string, StatusDisplay> = {
  active: { label: "进行中", tag: "ui-tag-green" },
  archived: { label: "已归档", tag: "ui-tag" },
  deleted: { label: "已删除", tag: "ui-tag" },
};

const MESSAGE_KIND: Record<string, StatusDisplay> = {
  user_input: { label: "用户输入", tag: "ui-tag-blue" },
  assistant_output: { label: "助手输出", tag: "ui-tag-green" },
  system_notice: { label: "系统通知", tag: "ui-tag" },
};

const MESSAGE_AUTHOR: Record<string, StatusDisplay> = {
  user: { label: "用户", tag: "ui-tag-blue" },
  agent: { label: "助手", tag: "ui-tag-purple" },
  system: { label: "系统", tag: "ui-tag" },
};

const CONTENT_STATE: Record<string, StatusDisplay> = {
  visible: { label: "可见", tag: "ui-tag" },
  redacted: { label: "已脱敏", tag: "ui-tag-amber" },
  superseded: { label: "已被取代", tag: "ui-tag" },
};

const OUTPUT_PUBLISH_STATE: Record<string, StatusDisplay> = {
  not_required: { label: "无需发布", tag: "ui-tag" },
  pending: { label: "待发布", tag: "ui-tag-blue" },
  published: { label: "已发布", tag: "ui-tag-green" },
  dead_letter: { label: "发布失败", tag: "ui-tag-amber" },
  suppressed: { label: "已抑制", tag: "ui-tag" },
};

function lookup(table: Record<string, StatusDisplay>, key: string): StatusDisplay {
  return table[key] ?? { label: key, tag: "ui-tag" };
}

export function runStatus(status: string): StatusDisplay {
  return lookup(RUN_STATUS, status);
}

export function conversationState(state: string): StatusDisplay {
  return lookup(CONVERSATION_STATE, state);
}

export function messageKind(kind: string): StatusDisplay {
  return lookup(MESSAGE_KIND, kind);
}

export function messageAuthor(authorType: string): StatusDisplay {
  return lookup(MESSAGE_AUTHOR, authorType);
}

export function contentState(state: string): StatusDisplay {
  return lookup(CONTENT_STATE, state);
}

export function outputPublishState(state: string): StatusDisplay {
  return lookup(OUTPUT_PUBLISH_STATE, state);
}
