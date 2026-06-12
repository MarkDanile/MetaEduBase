import type { EvidenceItem } from "@/types/evidence";

export interface ChatEvidenceMessage {
  id: string;
  role: "user" | "assistant";
  sources?: EvidenceItem[];
}

export function findEvidenceForMessage(
  messages: ChatEvidenceMessage[],
  messageId: string | undefined,
  evidenceIndex: number
): EvidenceItem | undefined {
  if (!messageId || evidenceIndex < 1) return undefined;
  const message = messages.find((item) => item.id === messageId);
  return message?.sources?.[evidenceIndex - 1];
}
