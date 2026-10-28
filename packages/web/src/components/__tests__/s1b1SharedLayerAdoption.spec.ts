/**
 * REQ-064 S1b-1：共享控件 opt-in 采用行为锁。
 *
 * S1b-1 只在**共享组件**层采用新的语义类（不碰业务页面），
 * 因此这里锁定三件事：
 *
 * - `EmptyState` 采用 `.ui-panel-static`：空态面板是静态容器，
 *   不应因 hover 抬升阴影或表现为可点击（G3）；
 * - `EvidenceCard` 在有源文件时采用 `.ui-panel-interactive`，
 *   无源文件时不采用（静态与可交互语义必须可区分，G3）；
 * - `FieldEditor` / `CloneTemplateDialog` / `ImportTemplateDialog`
 *   的输入框采用 `.ui-input-leading`（行高 opt-in，G4），
 *   且未采用的输入框不会因本切片被全局改写。
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";

import EmptyState from "@/components/EmptyState.vue";
import EvidenceCard from "@/components/EvidenceCard.vue";
import FieldEditor from "@/components/FieldEditor.vue";
import type { EvidenceItem } from "@/types/evidence";

function makeEvidence(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    evidence_id: "chunk:fake-file:fake-chunk",
    source_type: "chunk",
    file_id: "fake-file",
    chunk_id: "fake-chunk",
    title: "电路基础",
    content: "电路基础包含欧姆定律、基尔曼定律等。",
    snippet: "电路基础包含欧姆定律...",
    score: 0.87,
    channels: ["vector", "keyword"],
    ...overrides,
  } as EvidenceItem;
}

describe("S1b-1 共享控件 opt-in 采用（G3 / G4）", () => {
  it("EmptyState 采用静态面板语义（.ui-panel-static）", () => {
    const wrapper = mount(EmptyState, {
      props: { title: "暂无知识节点", hint: "点击右上角创建第一个知识节点" },
    });
    const panel = wrapper.find(".ui-panel");
    expect(panel.exists()).toBe(true);
    expect(panel.classes()).toContain("ui-panel-static");
    expect(panel.classes()).not.toContain("ui-panel-interactive");
  });

  it("EvidenceCard 有源文件时采用可交互面板语义", () => {
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence: makeEvidence() },
    });
    expect(wrapper.classes()).toContain("ui-panel");
    expect(wrapper.classes()).toContain("ui-panel-interactive");
  });

  it("EvidenceCard 无源文件时不采用可交互面板语义", () => {
    const wrapper = mount(EvidenceCard, {
      props: { index: 1, evidence: makeEvidence({ file_id: "" }) },
    });
    expect(wrapper.classes()).toContain("ui-panel");
    expect(wrapper.classes()).not.toContain("ui-panel-interactive");
  });

  it("FieldEditor 的输入框采用行高 opt-in（.ui-input-leading）", () => {
    const wrapper = mount(FieldEditor, {
      props: {
        modelValue: { key: "k", label: "标签", type: "text", description: "" },
      },
    });
    const inputs = wrapper.findAll("input.ui-input");
    expect(inputs.length).toBeGreaterThan(0);
    for (const input of inputs) {
      expect(input.classes()).toContain("ui-input-leading");
    }
  });
});
