/**
 * REQ-010 AC-4: renderMarkdown [N] 引用编号改写行为锁。
 *
 * 覆盖 3 场景：
 * 1. sources 存在且编号对齐 → 改写为 <a class="evidence-ref" data-ref=N>
 * 2. sources 存在但 [3] 越界 → 保持字面 [3]
 * 3. sources 为空 / undefined → 保持字面所有 [N]
 */
import { describe, it, expect } from "vitest";
import { replaceEvidenceReferences } from "../evidenceReferences";
import type { EvidenceItem } from "@/types/evidence";

function makeSources(n: number): EvidenceItem[] {
  return Array.from({ length: n }, (_, i) => ({
    evidence_id: `chunk:file-${i + 1}:chunk-${i + 1}`,
    source_type: "chunk" as const,
    file_id: `file-${i + 1}`,
    chunk_id: `chunk-${i + 1}`,
    title: `来源 ${i + 1}`,
    content: "",
    snippet: "",
    channels: ["vector"],
  }));
}

describe("replaceEvidenceReferences (REQ-010 AC-4)", () => {
  it("sources 存在且编号对齐时改写为 evidence-ref <a>", () => {
    const html = "<p>请参考 [1] 和 [2] 这两个来源。</p>";
    const out = replaceEvidenceReferences(html, makeSources(2));
    expect(out).toContain('<a class="evidence-ref" data-ref="1" href="#evidence-1">[1]</a>');
    expect(out).toContain('<a class="evidence-ref" data-ref="2" href="#evidence-2">[2]</a>');
  });

  it("传入 messageId 时写入 data-message-id", () => {
    const html = "<p>请参考 [1]。</p>";
    const out = replaceEvidenceReferences(html, makeSources(1), "assistant-1");
    expect(out).toContain('data-message-id="assistant-1"');
  });

  it("[3] 越界时保持字面 [3]", () => {
    const html = "<p>请参考 [1]、[2]、[3] 来源。</p>";
    const out = replaceEvidenceReferences(html, makeSources(2));
    expect(out).toContain('<a class="evidence-ref" data-ref="1"');
    expect(out).toContain('<a class="evidence-ref" data-ref="2"');
    expect(out).toContain("[3]"); // 越界保持字面
    expect(out).not.toContain("data-ref=\"3\"");
  });

  it("sources 为空时所有 [N] 保持字面", () => {
    const html = "<p>请参考 [1]、[2] 来源。</p>";
    expect(replaceEvidenceReferences(html, undefined)).toBe(html);
    expect(replaceEvidenceReferences(html, [])).toBe(html);
  });

  it("不修改 N < 1 / 非数字 / 负数", () => {
    const html = "<p>[0] [abc] [-1] [1]</p>";
    const out = replaceEvidenceReferences(html, makeSources(2));
    // [0] / [abc] / [-1] 都保持字面
    expect(out).toContain("[0]");
    expect(out).toContain("[abc]");
    expect(out).toContain("[-1]");
    // [1] 改写
    expect(out).toContain('<a class="evidence-ref" data-ref="1"');
  });

  it("marked 输出的 <p> 包裹文本中 [N] 仍能匹配", () => {
    // 模拟 marked.parse() 的真实输出格式
    const html = "<p>智能制造专业需要掌握 CAD、CAE 等技能 [1]，\n并熟悉 PLC 编程 [2]。</p>";
    const out = replaceEvidenceReferences(html, makeSources(2));
    expect(out).toContain('<a class="evidence-ref" data-ref="1"');
    expect(out).toContain('<a class="evidence-ref" data-ref="2"');
  });
});
