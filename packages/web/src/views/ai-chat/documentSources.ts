import type { DocumentSource, DocumentSourceChunk, EvidenceItem } from "@/types/evidence";

function metadataString(evidence: EvidenceItem, key: string): string | null {
  const value = evidence.metadata?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function metadataNumber(evidence: EvidenceItem, key: string): number | null {
  const value = evidence.metadata?.[key];
  return typeof value === "number" ? value : null;
}

export function deriveDocumentSourcesFromEvidence(
  sources: EvidenceItem[] = []
): DocumentSource[] {
  const grouped = new Map<string, DocumentSource>();

  sources.forEach((source, index) => {
    if (!source.file_id) return;
    const existing = grouped.get(source.file_id);
    const doc = existing ?? {
      file_id: source.file_id,
      title:
        metadataString(source, "filename") ??
        metadataString(source, "file_name") ??
        source.title ??
        source.file_id,
      file_name: metadataString(source, "filename") ?? metadataString(source, "file_name"),
      doc_type: metadataString(source, "doc_type"),
      tags: Array.isArray(source.metadata?.tags) ? (source.metadata.tags as string[]) : [],
      best_score: null,
      channels: [],
      evidence_indices: [],
      chunks: [],
    };

    doc.evidence_indices.push(index + 1);
    doc.channels = Array.from(new Set([...doc.channels, ...(source.channels ?? [])])).sort();
    if (source.score != null) {
      doc.best_score = doc.best_score == null ? source.score : Math.max(doc.best_score, source.score);
    }

    if (source.chunk_id) {
      const chunk: DocumentSourceChunk = {
        evidence_index: index + 1,
        chunk_id: source.chunk_id,
        chunk_index: metadataNumber(source, "chunk_index"),
        title: metadataString(source, "section_title") ?? source.title,
        snippet: source.snippet || source.content,
        score: source.score,
        channels: source.channels ?? [],
      };
      doc.chunks.push(chunk);
    }

    grouped.set(source.file_id, doc);
  });

  return Array.from(grouped.values()).sort(
    (a, b) => (b.best_score ?? -1) - (a.best_score ?? -1)
  );
}
