/**
 * REQ-042 WS-S1: Workspace 草稿 store（浏览器端未发送草稿持久化）。
 *
 * 隔离维度：tenant + owner(JWT sub) + conversation_id。存储 key 形如
 * `metaedu.workspace.<tenantId>.<sub>.draft.<conversationId>`。
 *
 * 设计要点：
 * - 不复用旧 AI Chat 的 `metaedu.ai-chat.` 前缀（不同功能，且 clearAiChatSessionStorage 会按前缀整批清掉）。
 * - 用 localStorage（草稿需跨刷新/重进/重新登录存活）；scope 派生自 localStorage 的
 *   metaedu_token / metaedu_tenant_id，sub 从 JWT payload base64url 解码，失败返回 null。
 * - 只存草稿纯文本；绝不写 token、凭据或任何敏感字段。
 * - 响应式镜像以【完整 scoped key】为键（含 tenant+owner），因此同一 Pinia 生命周期内
 *   跨 owner 也不会读到他人草稿缓存；跨 owner 因 key 不同天然不可读。
 * - 无 scope（未登录/匿名）时读写静默降级为空，不 throw（草稿是渐进增强，不是硬依赖）。
 */
import { defineStore } from "pinia";
import { ref } from "vue";

const WORKSPACE_STORAGE_PREFIX = "metaedu.workspace.";

function tokenSubject(token: string | null): string | null {
  if (!token) return null;
  const encoded = token.split(".")[1];
  if (!encoded) return null;
  try {
    const normalized = encoded.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const payload = JSON.parse(atob(padded)) as { sub?: unknown };
    return typeof payload.sub === "string" ? payload.sub : null;
  } catch {
    return null;
  }
}

/** tenant + owner scope；未认证/无法解析时返回 null（草稿静默降级）。 */
export function workspaceScope(
  token = localStorage.getItem("metaedu_token"),
  tenantId = localStorage.getItem("metaedu_tenant_id"),
): string | null {
  const subject = tokenSubject(token);
  return tenantId && subject ? `${tenantId}.${subject}` : null;
}

/** 完整 scoped 存储 key（含 tenant+owner+conversation）；无 scope 返回 null。 */
function draftKey(conversationId: string): string | null {
  const scope = workspaceScope();
  if (!scope) return null;
  return `${WORKSPACE_STORAGE_PREFIX}${scope}.draft.${conversationId}`;
}

export const useWorkspaceDraftStore = defineStore("workspaceDraft", () => {
  // 响应式镜像，键为完整 scoped 存储 key（含 tenant+owner），杜绝跨 owner 缓存串读。
  const drafts = ref<Record<string, string>>({});

  function getDraft(conversationId: string): string {
    const key = draftKey(conversationId);
    if (!key) return "";
    if (Object.prototype.hasOwnProperty.call(drafts.value, key)) {
      return drafts.value[key];
    }
    const stored = localStorage.getItem(key) ?? "";
    drafts.value[key] = stored;
    return stored;
  }

  function setDraft(conversationId: string, text: string): void {
    const key = draftKey(conversationId);
    if (!key) return;
    drafts.value[key] = text;
    if (text.length === 0) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, text);
    }
  }

  function clearDraft(conversationId: string): void {
    const key = draftKey(conversationId);
    if (!key) return;
    delete drafts.value[key];
    localStorage.removeItem(key);
  }

  return { drafts, getDraft, setDraft, clearDraft };
});
