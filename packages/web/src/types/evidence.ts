/**
 * REQ-010 — unified evidence DTO type for AI Chat.
 *
 * Mirrors backend `app.contexts.knowledge.domain.evidence.EvidenceItem`.
 * Used by /ai/chat/evidence response and any future evidence-aware
 * surface (MCP, knowledge view, etc.).
 */
export type SourceType =
  | "chunk"
  | "knowledge_node"
  | "knowledge_edge"
  | "structured_field";

export interface EvidenceItem {
  evidence_id: string;
  source_type: SourceType;
  file_id?: string | null;
  chunk_id?: string | null;
  node_id?: string | null;
  edge_id?: string | null;
  structured_path?: string | null;
  title: string;
  content: string;
  snippet: string;
  metadata?: Record<string, unknown>;
  score?: number | null;
  channels: string[];
}

export interface EvidenceChatResponse {
  reply: string;
  sources: EvidenceItem[];
}
