/**
 * `DocumentSourceList.vue` — 参考来源区视觉与可达性回归锁（AC-6）。
 *
 * BUG-003 fix3：
 * - chunk 按钮加 data-testid 便于维护者 / Playwright 定位；
 * - chunk 按钮加 aria-label "定位到该 chunk" 提升可达性；
 * - 外层容器加左侧 accent 边框（视觉强化作为参考来源区）。
 *
 * AC-6 真实验收由维护者人工截图，本 spec 锁住 DOM 行为契约作为回归
 * 锁——后续若有人去掉 data-testid / aria-label，CI 必断。
 */
import { describe, it, expect } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import DocumentSourceList from "../DocumentSourceList.vue";
import type { DocumentSource, DocumentSourceChunk } from "@/types/evidence";

function makeChunk(overrides: Partial<DocumentSourceChunk> = {}): DocumentSourceChunk {
  return {
    evidence_index: 1,
    chunk_id: "chunk-fake-1",
    chunk_index: 51,
    title: "数据类型和变量",
    snippet: "Python 支持多种数据类型，包括整数、浮点数、字符串...",
    score: 0.9,
    channels: ["vector", "keyword"],
    ...overrides,
  };
}

function makeSource(overrides: Partial<DocumentSource> = {}): DocumentSource {
  return {
    file_id: "file-fake-1",
    title: "Python 教程-廖雪峰.pdf",
    file_name: "Python 教程-廖雪峰.pdf",
    doc_type: "操作指南",
    tags: ["python"],
    best_score: 0.9,
    channels: ["vector", "keyword"],
    evidence_indices: [1],
    chunks: [makeChunk()],
    ...overrides,
  };
}

describe("DocumentSourceList.vue — BUG-003 fix3 AC-6", () => {
  it("chunk 按钮有 data-testid 便于测试 / 维护者定位", async () => {
    const wrapper = mount(DocumentSourceList, {
      props: { sources: [makeSource()] },
    });
    // 默认折叠，需要点击展开按钮才能看到 chunk 列表。
    await wrapper.find('button[aria-label="展开命中片段"]').trigger("click");
    await flushPromises();
    const chunks = wrapper.findAll('[data-testid="document-source-chunk"]');
    expect(chunks).toHaveLength(1);
  });

  it("chunk 按钮有 aria-label=定位到该 chunk 提升可达性", async () => {
    const wrapper = mount(DocumentSourceList, {
      props: { sources: [makeSource()] },
    });
    await wrapper.find('button[aria-label="展开命中片段"]').trigger("click");
    await flushPromises();
    const chunk = wrapper.find('[data-testid="document-source-chunk"]');
    expect(chunk.attributes("aria-label")).toBe("定位到该 chunk");
  });

  it("外链按钮有 aria-label=查看文档（已存在，锁住回归）", () => {
    const wrapper = mount(DocumentSourceList, {
      props: { sources: [makeSource()] },
    });
    const external = wrapper.find('button[aria-label="查看文档"]');
    expect(external.exists()).toBe(true);
  });

  it("渲染 N 个 chunk 按钮（N = source.chunks.length）", async () => {
    const source = makeSource({
      chunks: [makeChunk({ evidence_index: 1, chunk_id: "c1" }), makeChunk({ evidence_index: 2, chunk_id: "c2" })],
    });
    const wrapper = mount(DocumentSourceList, {
      props: { sources: [source] },
    });
    await wrapper.find('button[aria-label="展开命中片段"]').trigger("click");
    await flushPromises();
    const chunks = wrapper.findAll('[data-testid="document-source-chunk"]');
    expect(chunks).toHaveLength(2);
  });
});
