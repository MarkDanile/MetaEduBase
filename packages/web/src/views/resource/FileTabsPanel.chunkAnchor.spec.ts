/**
 * REQ-010 AC-15: `FileTabsPanel.vue` ?chunk= 锚点行为锁。
 *
 * - chunk 元素有 id="chunk-{id}"
 * - highlightChunkId prop 匹配时高亮（边框 + 背景）
 * - 不匹配时不高亮
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import FileTabsPanel from "./FileTabsPanel.vue";
import type { ChunkDTO } from "@/services/document";
import type { Template } from "@/services/template";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";

const FAKE_CHUNKS: ChunkDTO[] = [
  {
    id: "chunk-aaa",
    tenant_id: "t1",
    file_id: "file-1",
    chunk_index: 0,
    content: "第一段内容",
    section_title: "引言",
    section_path: "1",
    has_embedding: true,
    char_start: 0,
    char_end: 100,
  } as unknown as ChunkDTO,
  {
    id: "chunk-bbb",
    tenant_id: "t1",
    file_id: "file-1",
    chunk_index: 1,
    content: "第二段内容",
    section_title: "发展史",
    section_path: "2",
    has_embedding: false,
    char_start: 100,
    char_end: 200,
  } as unknown as ChunkDTO,
];

function mountFileTabsPanel(highlightChunkId: string | null) {
  return mount(FileTabsPanel, {
    props: {
      activeTab: "chunks",
      templates: [] as Template[],
      chunks: FAKE_CHUNKS,
      chunksLoading: false,
      kgNodes: [] as KnowledgeNodeDTO[],
      kgEdges: [] as KnowledgeEdgeDTO[],
      kgLoading: false,
      structuredData: null,
      highlightChunkId,
    },
  });
}

describe("FileTabsPanel.vue ?chunk= anchor (REQ-010 AC-15)", () => {
  it("chunk 元素带 id='chunk-{id}'", () => {
    const wrapper = mountFileTabsPanel(null);
    const first = wrapper.find("#chunk-chunk-aaa");
    expect(first.exists()).toBe(true);
    const second = wrapper.find("#chunk-chunk-bbb");
    expect(second.exists()).toBe(true);
  });

  it("highlightChunkId 匹配的 chunk 加高亮类", () => {
    const wrapper = mountFileTabsPanel("chunk-aaa");
    const first = wrapper.find("#chunk-chunk-aaa");
    // 高亮类（accent border + accent bg）
    const cls = first.attributes("class") || "";
    expect(cls).toContain("border-[var(--color-accent)]");
    expect(cls).toContain("bg-[var(--color-accent-bg)]");
  });

  it("highlightChunkId 不匹配的 chunk 不高亮", () => {
    const wrapper = mountFileTabsPanel("chunk-bbb");
    const first = wrapper.find("#chunk-chunk-aaa");
    const cls = first.attributes("class") || "";
    expect(cls).not.toContain("border-[var(--color-accent)]");
    expect(cls).not.toContain("bg-[var(--color-accent-bg)]");
    // 但仍是普通 border
    expect(cls).toContain("border-[var(--color-border)]");
  });
});
