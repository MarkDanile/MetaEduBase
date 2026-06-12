import { describe, expect, it } from "vitest";
import { deriveDocumentSourcesFromEvidence } from "../documentSources";
import type { EvidenceItem } from "@/types/evidence";

function chunk(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    evidence_id: "chunk:file-1:chunk-1",
    source_type: "chunk",
    file_id: "file-1",
    chunk_id: "chunk-1",
    title: "第一节",
    content: "Python 的基本数据类型包括数字、字符串、列表。",
    snippet: "Python 的基本数据类型包括数字、字符串、列表。",
    metadata: {
      filename: "Python 操作指南.pdf",
      doc_type: "操作指南",
      chunk_index: 1,
      section_title: "基本数据类型",
      tags: ["python"],
    },
    score: 0.9,
    channels: ["vector"],
    ...overrides,
  };
}

describe("deriveDocumentSourcesFromEvidence", () => {
  it("groups multiple chunks under the same document", () => {
    const docs = deriveDocumentSourcesFromEvidence([
      chunk(),
      chunk({
        evidence_id: "chunk:file-1:chunk-2",
        chunk_id: "chunk-2",
        score: 0.8,
        channels: ["keyword"],
      }),
    ]);

    expect(docs).toHaveLength(1);
    expect(docs[0].title).toBe("Python 操作指南.pdf");
    expect(docs[0].chunks).toHaveLength(2);
    expect(docs[0].evidence_indices).toEqual([1, 2]);
    expect(docs[0].channels).toEqual(["keyword", "vector"]);
  });

  it("skips evidence without file_id", () => {
    const docs = deriveDocumentSourcesFromEvidence([
      chunk({ file_id: null, chunk_id: null, source_type: "knowledge_node" }),
    ]);
    expect(docs).toEqual([]);
  });
});
