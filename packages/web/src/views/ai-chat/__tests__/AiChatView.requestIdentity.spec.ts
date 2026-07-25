import { describe, expect, it } from "vitest";
import aiChatViewSource from "../AiChatView.vue?raw";

const source = aiChatViewSource as string;

describe("AiChatView Direct RAG durable request identity", () => {
  it("persists the conversation and reuses pending request identity", () => {
    expect(source).toMatch(
      /sessionStorage\.getItem\(conversationStorageKey\)\s*\|\|\s*crypto\.randomUUID\(\)/,
    );
    expect(source).toMatch(
      /parsed\?\.text\s*===\s*text[\s\S]*parsed\.clientMessageId/,
    );
    expect(source).toMatch(/sessionStorage\.setItem\(pendingRequestStorageKey/);
    expect(source).toMatch(/conversation_id:\s*conversationId/);
    expect(source).toMatch(/client_message_id:\s*clientMessageId/);
    expect(source).toMatch(/unresolved\.text\s*!==\s*text/);
    expect(source).toMatch(/conversationId\s*=\s*data\.conversation_id/);
    expect(source).not.toMatch(
      /name === "CanceledError"[\s\S]{0,250}removeItem\(pendingRequestStorageKey\)/,
    );
  });
});
