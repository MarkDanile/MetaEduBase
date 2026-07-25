const AI_CHAT_STORAGE_PREFIX = "metaedu.ai-chat.";

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

export function aiChatSessionScope(
  token = localStorage.getItem("metaedu_token"),
  tenantId = localStorage.getItem("metaedu_tenant_id"),
): string | null {
  const subject = tokenSubject(token);
  return tenantId && subject ? `${tenantId}.${subject}` : null;
}

export function aiChatStorageKeys(): {
  conversation: string;
  pendingRequest: string;
} {
  const scope = aiChatSessionScope();
  if (!scope) throw new Error("AI Chat requires an authenticated session scope");
  return {
    conversation: `${AI_CHAT_STORAGE_PREFIX}${scope}.conversation-id`,
    pendingRequest: `${AI_CHAT_STORAGE_PREFIX}${scope}.pending-request`,
  };
}

export function clearAiChatSessionStorage(): void {
  const keys = Array.from({ length: sessionStorage.length }, (_, index) => (
    sessionStorage.key(index)
  )).filter((key): key is string => Boolean(key?.startsWith(AI_CHAT_STORAGE_PREFIX)));
  keys.forEach((key) => sessionStorage.removeItem(key));
}
