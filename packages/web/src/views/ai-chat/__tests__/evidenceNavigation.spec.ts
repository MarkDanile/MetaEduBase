import { describe, expect, it } from "vitest";
import { findEvidenceForMessage, type ChatEvidenceMessage } from "../evidenceNavigation";
import type { EvidenceItem } from "@/types/evidence";

function source(fileId: string, chunkId: string): EvidenceItem {
  return {
    evidence_id: `chunk:${fileId}:${chunkId}`,
    source_type: "chunk",
    file_id: fileId,
    chunk_id: chunkId,
    title: chunkId,
    content: "",
    snippet: "",
    channels: ["vector"],
  };
}

describe("findEvidenceForMessage", () => {
  it("uses the clicked assistant message instead of the latest assistant message", () => {
    const messages: ChatEvidenceMessage[] = [
      { id: "assistant-old", role: "assistant", sources: [source("file-a", "chunk-a")] },
      { id: "assistant-new", role: "assistant", sources: [source("file-b", "chunk-b")] },
    ];

    const evidence = findEvidenceForMessage(messages, "assistant-old", 1);
    expect(evidence?.file_id).toBe("file-a");
    expect(evidence?.chunk_id).toBe("chunk-a");
  });

  it("returns undefined for missing message or out-of-range index", () => {
    const messages: ChatEvidenceMessage[] = [
      { id: "assistant-old", role: "assistant", sources: [source("file-a", "chunk-a")] },
    ];
    expect(findEvidenceForMessage(messages, "missing", 1)).toBeUndefined();
    expect(findEvidenceForMessage(messages, "assistant-old", 2)).toBeUndefined();
  });
});
