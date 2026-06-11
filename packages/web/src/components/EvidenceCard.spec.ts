/**
 * REQ-010 AC-5/AC-6: `EvidenceCard.vue` 行为锁。
 *
 * - 渲染 [N] 编号 + source_type label + 通道 tag + 分数。
 * - 当 evidence 有 file_id 时显示 "查看源文件" 提示 + 触发 open-file 事件。
 * - 当 evidence 无 file_id 时不可点击 + 不显示跳转提示。
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import EvidenceCard from "./EvidenceCard.vue";
import type { EvidenceItem } from "@/types/evidence";

function makeChunk(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    evidence_id: "chunk:fake-file:fake-chunk",
    source_type: "chunk",
    file_id: "fake-file",
    chunk_id: "fake-chunk",
    title: "电路基础",
    content: "电路基础包含欧姆定律、基尔霍夫定律等。",
    snippet: "电路基础包含欧姆定律...",
    score: 0.87,
    channels: ["vector", "keyword"],
    ...overrides,
  };
}

describe("EvidenceCard.vue (REQ-010 AC-5/AC-6)", () => {
  it("渲染 [N] 编号 + source_type 中文 label", () => {
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence: makeChunk() },
    });
    expect(wrapper.text()).toContain("[1]");
    expect(wrapper.text()).toContain("原文切片");  // source_type=chunk
  });

  it("渲染 evidence.title 作为主标题", () => {
    const wrapper = mount(EvidenceCard, {
      props: { index: 2, evidence: makeChunk({ title: "数字系统设计" }) },
    });
    expect(wrapper.text()).toContain("数字系统设计");
  });

  it("渲染 channels tag 列表", () => {
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence: makeChunk() },
    });
    expect(wrapper.text()).toContain("vector");
    expect(wrapper.text()).toContain("keyword");
  });

  it("渲染 score 为百分比", () => {
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence: makeChunk({ score: 0.95 }) },
    });
    expect(wrapper.text()).toContain("95%");
  });

  it("knowledge_node 用 '知识节点' label", () => {
    const node: EvidenceItem = {
      evidence_id: "knowledge_node:fake-file:fake-node",
      source_type: "knowledge_node",
      file_id: null,
      chunk_id: null,
      node_id: "fake-node",
      title: "智能制造",
      content: "专业方向描述",
      snippet: "",
      score: 0.7,
      channels: ["vector"],
    };
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence: node },
    });
    expect(wrapper.text()).toContain("知识节点");
  });

  it("有 file_id 时点击 emit open-file 事件", async () => {
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence: makeChunk() },
    });
    await wrapper.trigger("click");
    const emitted = wrapper.emitted("open-file");
    expect(emitted).toBeTruthy();
    expect(emitted![0][0]).toEqual(makeChunk());
  });

  it("无 file_id 时不 emit open-file（不可点击）", async () => {
    const evidence = makeChunk({ file_id: null, chunk_id: null });
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence },
    });
    await wrapper.trigger("click");
    expect(wrapper.emitted("open-file")).toBeFalsy();
  });
});
