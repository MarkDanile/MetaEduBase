import { beforeEach, describe, expect, it } from "vitest";
import {
  aiChatSessionScope,
  aiChatStorageKeys,
  clearAiChatSessionStorage,
} from "./aiChatSessionStorage";

function token(subject: string): string {
  const payload = btoa(JSON.stringify({ sub: subject }))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  return `header.${payload}.signature`;
}

describe("AI Chat session storage scope", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("isolates storage keys by tenant and JWT subject", () => {
    const first = aiChatSessionScope(token("user-a"), "tenant-a");
    const second = aiChatSessionScope(token("user-b"), "tenant-a");
    expect(first).toBe("tenant-a.user-a");
    expect(second).toBe("tenant-a.user-b");
    expect(first).not.toBe(second);

    localStorage.setItem("metaedu_token", token("user-a"));
    localStorage.setItem("metaedu_tenant_id", "tenant-a");
    expect(aiChatStorageKeys().conversation).toContain("tenant-a.user-a");
  });

  it("clears all AI Chat state without touching unrelated session data", () => {
    sessionStorage.setItem("metaedu.ai-chat.a.conversation-id", "conversation");
    sessionStorage.setItem("metaedu.ai-chat.b.pending-request", "pending");
    sessionStorage.setItem("unrelated", "keep");

    clearAiChatSessionStorage();

    expect(sessionStorage.getItem("metaedu.ai-chat.a.conversation-id")).toBeNull();
    expect(sessionStorage.getItem("metaedu.ai-chat.b.pending-request")).toBeNull();
    expect(sessionStorage.getItem("unrelated")).toBe("keep");
  });
});
