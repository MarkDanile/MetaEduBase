import type { DocumentSource, EvidenceItem } from "@/types/evidence";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: EvidenceItem[];
  document_sources?: DocumentSource[];
  document_sources_view: DocumentSource[];
  /** 仅标记本地展示语气，不改变请求或后端错误语义。 */
  tone?: "error" | "stopped";
}
