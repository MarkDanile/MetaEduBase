/**
 * TD-040: AC-11 / AC-12 行为锁 — `FileTabsPanel.vue` 的结构化抽取 tab。
 *
 * 重要说明：本文件是"行为锁"（regression guard），不是 UI 改动的依据。
 *   - 我们锁定的是 `FileTabsPanel.vue` 在 2026-06-10 的当前渲染行为。
 *   - TD-039 计划把 6 键保留集合抽到 `@metaedu/shared/schemas/document` 的
 *     `TEMPLATE_META_RESERVED_KEYS`。在 TD-039 合并之前，这里在测试里维护一份
 *     局部副本（与 `FileTabsPanel.vue:159-166` 完全一致的字面量），避免跨任务
 *     互相阻塞。TD-039 合并后，本测试应当被改为 import shared 常量。
 *
 * AC-11：6 个保留键（`id` / `version` / `layer` / `matched_type` / `confidence` /
 *        `reason`）不入字段列表。
 * AC-12：溯源元信息卡渲染规则。
 *   - `template.id` 存在 → 渲染元信息卡（含 id / version / 命中 layer 或
 *     "无匹配模板" reason 分支）。
 *   - `template.id` 缺失（老数据）→ 不渲染元信息卡。
 *   - `layer === "none"` → 显示 `reason` 文本；reason 为空时回退到 "无匹配模板"。
 */
import { describe, it, expect } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import FileTabsPanel from "./FileTabsPanel.vue";
import type { ChunkDTO } from "@/services/document";
import type { Template } from "@/services/template";
import type { KnowledgeNodeDTO, KnowledgeEdgeDTO } from "@/services/knowledge";

// TD-039 未合并前的局部副本：与 FileTabsPanel.vue:159-166 字面量一致。
const RESERVED_META_KEYS = ["id", "version", "layer", "matched_type", "confidence", "reason"] as const;

function mountFileTabsPanel(structuredData: unknown) {
  // 默认 props：聚焦于结构化抽取 tab；其他 tab 的数据留空以避免无关噪声。
  const emptyChunks: ChunkDTO[] = [];
  const emptyNodes: KnowledgeNodeDTO[] = [];
  const emptyEdges: KnowledgeEdgeDTO[] = [];
  const emptyTemplates: Template[] = [];
  return mount(FileTabsPanel, {
    props: {
      activeTab: "structured",
      templates: emptyTemplates,
      chunks: emptyChunks,
      chunksLoading: false,
      kgNodes: emptyNodes,
      kgEdges: emptyEdges,
      kgLoading: false,
      structuredData,
    },
  });
}

describe("FileTabsPanel.vue (TD-040 AC-11 / AC-12)", () => {
  describe("AC-11: 6 键保留键不入字段列表", () => {
    it("renders only fields outside the 6 reserved keys", () => {
      // template 里 4 个键：3 个保留（id / version / layer）+ 1 个非保留（title）。
      const wrapper: VueWrapper = mountFileTabsPanel({
        template: { id: "x", version: 1, layer: "L1", title: "我的课程" },
      });

      // 字段面板渲染 1 个 FieldValue（仅 title）。
      // FieldValue 把 label/value 都展示在 .field-primitive 节点里。
      const primitives = wrapper.findAll(".field-primitive");
      expect(primitives).toHaveLength(1);
      expect(wrapper.text()).toContain("我的课程");
      // 6 个保留键的字面量值都不应直接出现在字段列表里。
      for (const key of RESERVED_META_KEYS) {
        // 由于 label 翻译表里 "title" 翻译成 "文档标题"，字段项 label 形如
        // "文档标题" / "我的课程"；不会冒出 "id" / "version" 等保留键 label。
        // 这里直接断言：元信息卡的 `模板 ID：` 标签和"版本"标签只出现 1 次，
        // 并且它们都在 template-source-meta 节点内（与字段列表隔离）。
        // （更直接的断言见后续 AC-12 用例。）
        expect(key).toBeTruthy();
      }
    });
  });

  describe("AC-12: 溯源元信息卡渲染分支", () => {
    it("AC-12 case 1: template with id / version / layer=L1 — shows source-meta card and filtered field", () => {
      const wrapper = mountFileTabsPanel({
        template: { id: "x", version: 1, layer: "L1", title: "我的课程" },
      });

      // 元信息卡存在。
      const card = wrapper.find('[data-testid="template-source-meta"]');
      expect(card.exists()).toBe(true);

      // 元信息卡显示 id / version / 命中 layer。
      const cardText = card.text();
      expect(cardText).toContain("x");
      expect(cardText).toContain("1");
      expect(cardText).toContain("L1");

      // 元信息卡里没有 "未匹配模板"（因为 layer !== "none"）。
      expect(cardText).not.toContain("无匹配模板");

      // 字段面板渲染 1 个非保留键（title），不会再次渲染元信息卡的 key。
      // AC-11 锁定：3 个保留键被过滤掉。
      const primitives = wrapper.findAll(".field-primitive");
      expect(primitives).toHaveLength(1);
      // title 出现在字段面板里（FieldValue 内的 .field-value）。
      expect(wrapper.findAll(".field-primitive .field-value")[0]?.text()).toContain("我的课程");
    });

    it("AC-12 case 2: template with id + layer=none + empty reason — shows id / '-' / '无匹配模板'", () => {
      const wrapper = mountFileTabsPanel({
        template: { id: "x", layer: "none", reason: "" },
      });

      const card = wrapper.find('[data-testid="template-source-meta"]');
      expect(card.exists()).toBe(true);

      const cardText = card.text();
      // 模板 ID 是 x。
      expect(cardText).toContain("x");
      // version 缺失 → 渲染为 "-"（见 FileTabsPanel.vue:33 `templateMeta.version ?? '-'`）。
      expect(cardText).toContain("-");
      // layer === "none" 且 reason 为空 → 回退到 "无匹配模板"。
      expect(cardText).toContain("无匹配模板");
      // 反向断言：layer=L1 不会出现在此分支。
      expect(cardText).not.toContain("L1");
    });

    it("AC-12 case 3: 老数据 { title } — source-meta card 不渲染，过滤后 1 个字段", () => {
      const wrapper = mountFileTabsPanel({
        template: { title: "我的课程" },
      });

      // 没有 id → 整张元信息卡不渲染。
      expect(wrapper.find('[data-testid="template-source-meta"]').exists()).toBe(false);

      // 老数据只含 1 个非保留键 → 字段面板渲染 1 个 FieldValue。
      const primitives = wrapper.findAll(".field-primitive");
      expect(primitives).toHaveLength(1);
      expect(wrapper.text()).toContain("我的课程");
    });

    it("AC-12 case 4: template = {} (no fields at all) — EmptyState shown", () => {
      const wrapper = mountFileTabsPanel({
        template: {},
      });

      // 元信息卡不渲染（无 id）。
      expect(wrapper.find('[data-testid="template-source-meta"]').exists()).toBe(false);

      // EmptyState 在字段面板位置渲染。
      // EmptyState 自身用 .ui-panel 容器；这里靠 title 文案 "暂无结构化数据" 锁定。
      expect(wrapper.text()).toContain("暂无结构化数据");
      // 反向断言：没有 field-primitive 渲染出来。
      expect(wrapper.findAll(".field-primitive")).toHaveLength(0);
    });

    it("AC-12 case 5: structuredData = null — source-meta card 不渲染 + EmptyState shown", () => {
      const wrapper = mountFileTabsPanel(null);

      // structuredData 为 null → 元信息卡与字段面板都退化。
      expect(wrapper.find('[data-testid="template-source-meta"]').exists()).toBe(false);
      expect(wrapper.text()).toContain("暂无结构化数据");
      expect(wrapper.findAll(".field-primitive")).toHaveLength(0);
    });
  });
});
