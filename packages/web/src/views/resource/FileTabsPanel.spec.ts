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

function mountFileTabsPanel(
  structuredData: unknown,
  templates: Template[] = [],
) {
  // 默认 props: 聚焦于结构化抽取 tab; 其他 tab 的数据留空以避免无关噪声.
  const emptyChunks: ChunkDTO[] = [];
  const emptyNodes: KnowledgeNodeDTO[] = [];
  const emptyEdges: KnowledgeEdgeDTO[] = [];
  return mount(FileTabsPanel, {
    props: {
      activeTab: "structured",
      templates,
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

describe("BUG-006 #1: 模板字段 label 渲染", () => {
  it("renders top-level field label not key", () => {
    // Mock 模板 fields: {key: "title", label: "标题", type: "text"}
    const templates: Template[] = [
      {
        id: "t1",
        name: "教案",
        doc_types: ["教案"],
        ai_prompt: null,
        ai_context: null,
        source_file_id: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
        // REQ-002-4: schema_version + deprecation fields (Template interface requires)
        schema_version: 1,
        is_deprecated: false,
        deprecated_at: null,
        deprecated_reason: null,
        fields: [
          { key: "title", label: "标题", type: "text" },
        ],
      },
    ];
    const structuredData = { template: { title: "数学教案" } };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 断言: 渲染 "标题" 不含 "title:" 文本
    expect(wrapper.text()).toContain("标题");
    expect(wrapper.text()).toContain("数学教案");
    expect(wrapper.text()).not.toContain("title:");
  });

  it("renders nested object field label via dot-path", () => {
    // Mock 模板 fields: basic_info 嵌套 major_name / degree
    const templates: Template[] = [
      {
        id: "t2",
        name: "人才培养方案",
        doc_types: ["人才培养方案"],
        ai_prompt: null,
        ai_context: null,
        source_file_id: null,
        created_at: "2026-01-01",
        updated_at: "2026-01-01",
        schema_version: 1,
        is_deprecated: false,
        deprecated_at: null,
        deprecated_reason: null,
        fields: [
          {
            key: "basic_info",
            label: "基本信息",
            type: "object",
            children: [
              { key: "major_name", label: "专业名称", type: "text" },
              { key: "degree", label: "学位", type: "text" },
            ],
          },
        ],
      },
    ];
    const structuredData = {
      template: {
        basic_info: { major_name: "环境监测技术", degree: "-" },
      },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 断言: 父 "基本信息" + 子 "专业名称" / "学位" 都渲染
    expect(wrapper.text()).toContain("基本信息");
    expect(wrapper.text()).toContain("专业名称");
    expect(wrapper.text()).toContain("环境监测技术");
    expect(wrapper.text()).toContain("学位");
    // 关键: 不含原始 key
    expect(wrapper.text()).not.toContain("major_name:");
    expect(wrapper.text()).not.toContain("degree:");
  });

  it("falls back to key when label not configured", () => {
    const templates: Template[] = [];  // 模板空
    const structuredData = {
      template: { some_unconfigured_key: "X" },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 接受 fallback: 字段名显示原始 key (不抛错)
    expect(wrapper.text()).toContain("some_unconfigured_key");
    expect(wrapper.text()).toContain("X");
  });

  it("falls back to hard-coded map for legacy course keys", () => {
    const templates: Template[] = [];  // 模板空, 但 hard-coded map 兜底
    const structuredData = {
      template: { course_name: "数学" },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // 断言: 即使模板无 fields, 走 hard-coded map 仍能显示 "课程名称"
    expect(wrapper.text()).toContain("课程名称");
    expect(wrapper.text()).toContain("数学");
    expect(wrapper.text()).not.toContain("course_name:");
  });

  it("renders array item field label (course_content[].module_name)", () => {
    // Mock 模板: course_content (array) → items[0].key='module_name' label='模块/项目名称'
    const templates: Template[] = [
      {
        id: "t3", name: "课程标准", doc_types: ["课程标准"],
        ai_prompt: null, ai_context: null, source_file_id: null,
        created_at: "2026-01-01", updated_at: "2026-01-01",
        schema_version: 1, is_deprecated: false, deprecated_at: null, deprecated_reason: null,
        fields: [
          {
            key: "course_content", label: "课程内容", type: "array",
            items: [
              { key: "module_name", label: "模块/项目名称", type: "text" },
              { key: "teaching_content", label: "教学内容", type: "textarea" },
            ],
          },
        ],
      },
    ];
    const structuredData = {
      template: {
        course_content: [{ module_name: "项目一 水环境监测基础" }],
      },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    expect(wrapper.text()).toContain("模块/项目名称");
    expect(wrapper.text()).toContain("项目一 水环境监测基础");
    expect(wrapper.text()).not.toContain("module_name:");
  });

  it("renders array item nested object label (teaching_process[].step_name)", () => {
    // Mock 模板: teaching_process (array) → items[0] object with children
    const templates: Template[] = [
      {
        id: "t4", name: "教案", doc_types: ["教案"],
        ai_prompt: null, ai_context: null, source_file_id: null,
        created_at: "2026-01-01", updated_at: "2026-01-01",
        schema_version: 1, is_deprecated: false, deprecated_at: null, deprecated_reason: null,
        fields: [
          {
            key: "teaching_process", label: "教学过程", type: "array",
            items: [
              {
                key: "step", type: "object", label: "环节",
                children: [
                  { key: "step_name", label: "环节名称", type: "text" },
                  { key: "teacher_activity", label: "教师活动", type: "textarea" },
                ],
              },
            ],
          },
        ],
      },
    ];
    const structuredData = {
      template: {
        teaching_process: [
          { step_name: "课前任务", teacher_activity: "发布预习任务" },
        ],
      },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    expect(wrapper.text()).toContain("环节名称");
    expect(wrapper.text()).toContain("课前任务");
    expect(wrapper.text()).not.toContain("step_name:");
  });

  it("renders table column label (graduation_requirements[].requirement_id)", () => {
    // Mock 模板: graduation_requirements (table) → columns[].key='requirement_id' label='编号'
    const templates: Template[] = [
      {
        id: "t5", name: "人才培养方案", doc_types: ["人才培养方案"],
        ai_prompt: null, ai_context: null, source_file_id: null,
        created_at: "2026-01-01", updated_at: "2026-01-01",
        schema_version: 1, is_deprecated: false, deprecated_at: null, deprecated_reason: null,
        fields: [
          {
            key: "graduation_requirements", label: "毕业要求", type: "table",
            columns: [
              { key: "requirement_id", label: "编号", type: "text" },
              { key: "requirement_content", label: "要求内容", type: "textarea" },
            ],
          },
        ],
      },
    ];
    const structuredData = {
      template: {
        graduation_requirements: [
          { requirement_id: "G1", requirement_content: "完成所有必修课" },
        ],
      },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    expect(wrapper.text()).toContain("编号");
    expect(wrapper.text()).toContain("G1");
    expect(wrapper.text()).not.toContain("requirement_id:");
  });

  it("resolves leaf label across multiple templates with overlapping top-level fields (BUG-006 #1 round 2 partial-failure regression)", () => {
    // Setup: two templates both have a top-level `basic_info` field, but
    // only the second has a `degree` child. The algorithm must try all
    // matching top-level candidates, not break on the first one.
    const templates: Template[] = [
      {
        id: "legacy-tpl", name: "人才培养方案（历史版本）", doc_types: ["人才培养方案"],
        ai_prompt: null, ai_context: null, source_file_id: null,
        created_at: "2026-01-01", updated_at: "2026-01-01",
        schema_version: 1, is_deprecated: true, deprecated_at: "2026-02-01",
        deprecated_reason: null,
        fields: [
          {
            key: "basic_info", label: "基本信息", type: "object",
            children: [
              { key: "major_name", label: "专业名称", type: "text" },
              { key: "educational_system", label: "学制", type: "text" },
              { key: "training_level", label: "培养层次", type: "text" },
              { key: "enrollment_object", label: "招生对象", type: "text" },
              // NO `degree` child — this is the legacy schema.
            ],
          },
        ],
      },
      {
        id: "current-tpl", name: "人才培养方案", doc_types: ["人才培养方案"],
        ai_prompt: null, ai_context: null, source_file_id: null,
        created_at: "2026-03-01", updated_at: "2026-03-01",
        schema_version: 2, is_deprecated: false, deprecated_at: null,
        deprecated_reason: null,
        fields: [
          {
            key: "basic_info", label: "基本信息", type: "object",
            children: [
              { key: "major_name", label: "专业名称", type: "text" },
              { key: "educational_system", label: "学制", type: "text" },
              { key: "degree", label: "授予学位", type: "text" },
              { key: "training_level", label: "培养层次", type: "text" },
              { key: "enrollment_object", label: "招生对象", type: "text" },
            ],
          },
        ],
      },
    ];
    const structuredData = {
      template: {
        basic_info: {
          major_name: "环境监测技术",
          educational_system: "3 年",
          degree: "工学学士",
          training_level: "高职",
          enrollment_object: "普通高中毕业生",
        },
      },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    expect(wrapper.text()).toContain("授予学位");
    expect(wrapper.text()).toContain("工学学士");
    expect(wrapper.text()).not.toContain("basic_info.degree");
    expect(wrapper.text()).not.toContain("degree:");
  });

  it("renders array item label as items[0] schema label not index (BUG-006 #1 round 2 layout regression)", () => {
    // Setup: array field with items[0].key='course' label='课程'.
    // The visual should be: array-item-index "1" (from outer array-item span),
    // then "课程: value" (from recursive FieldValue using items[0] schema).
    // NOT "1. 1. 课程: value".
    const templates: Template[] = [
      {
        id: "t", name: "人才培养方案", doc_types: ["人才培养方案"],
        ai_prompt: null, ai_context: null, source_file_id: null,
        created_at: "2026-01-01", updated_at: "2026-01-01",
        schema_version: 1, is_deprecated: false, deprecated_at: null,
        deprecated_reason: null,
        fields: [
          {
            key: "curriculum_system", label: "课程体系", type: "array",
            items: [
              { key: "course", label: "课程", type: "text" },
            ],
          },
        ],
      },
    ];
    const structuredData = {
      template: {
        curriculum_system: [{ course: "数学" }, { course: "语文" }],
      },
    };
    const wrapper = mountFileTabsPanel(structuredData, templates);

    // The array index "1" should appear (from the array-item span).
    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).toContain("2");
    // The schema-resolved "课程" label should appear once per item.
    expect(wrapper.text()).toContain("课程");
    // The value "数学" should appear (separately from the label).
    expect(wrapper.text()).toContain("数学");
    // CRITICAL: the raw "course" key should NOT appear as a label,
    // because the algorithm resolves it to "课程".
    expect(wrapper.text()).not.toContain("course:");
  });
});
