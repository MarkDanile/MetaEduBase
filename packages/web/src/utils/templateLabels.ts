// BUG-006 #1 round 2: 模板字段 label 解析工具.
//
// 真因 4 层:
// 1. round 1 修复只覆盖 field.children[] (object 子字段), 不覆盖 field.items[]
//    (array item 模板) 和 field.columns[] (table 列).
// 2. templates[*].fields 只查 top-level, 不递归 children
// 3. dot-path 不支持 (basic_info.major_name 找不到 label)
// 4. hard-coded map 只列 18 个 legacy course 模板 key
//
// 5 步查找顺序 (优先级递减):
//   1. 沿 keyPath 走 schema 树 (children / items[0].key / items[0].children / columns)
//   2. keyPath.length === 1 时, 走老 dot-path + 全树递归 (兼容)
//   3. hard-coded map (legacy course 模板)
//   4. fallback: return keyPath.join(".")

import type { Template, Field } from "@/services/template";

/** 硬编码 label: 历史 course 模板 (course_name / semester 等 18 个) 在 templates
 * 表里没有显式 label, 但前端要继续显示中文. 这些是历史数据, 保留兼容. */
const HARDCODED_LABELS: Readonly<Record<string, string>> = {
  course_name: "课程名称",
  course_code: "课程代码",
  semester: "授课学期",
  department: "开课单位",
  teacher: "主讲教师",
  target_class: "授课班级",
  total_hours: "课程总学时",
  theory_hours: "理论学时",
  practice_hours: "实践学时",
  exam_mode: "考核方式",
  textbook: "教材及参考书",
  course_description: "课程简介",
  teaching_objectives: "教学目标",
  teaching_content_outline: "教学内容纲要",
  teaching_schedule: "教学进度安排",
  evaluation_plan: "课程评价方案",
  title: "文档标题",
  summary: "摘要",
  sections: "主要章节",
  keywords: "关键词",
};

/** 最小可遍历节点: 有 key + label, 可选 children / items 嵌套.
 * Field 满足, TableColumn 满足 (无 children/items, 找 leaf 即可). */
interface KeyedNode {
  key: string;
  label: string;
  children?: ReadonlyArray<KeyedNode>;
  items?: ReadonlyArray<KeyedNode>;
}

/** 把 Field[] 展平成 KeyedNode[]: 把 items[0] (item 模板) 和 columns 也并入候选.
 * 因为 findFieldNode 接受的是 homogeneous 数组, 但 schema 树是异构的
 * (Field.item 下的 items[0] 自己是一个 Field, columns 是 TableColumn, 它们共享
 * key/label 结构). */
function flattenCandidates(node: Field): KeyedNode[] {
  const out: KeyedNode[] = [];
  if (Array.isArray(node.children)) {
    for (const c of node.children) out.push(c as KeyedNode);
  }
  if (Array.isArray(node.items) && node.items.length > 0) {
    const item0 = node.items[0];
    if (item0) {
      out.push(item0 as KeyedNode);
      if (Array.isArray(item0.children)) {
        for (const c of item0.children) out.push(c as KeyedNode);
      }
    }
  }
  if (Array.isArray(node.columns)) {
    for (const c of node.columns) out.push(c as unknown as KeyedNode);
  }
  return out;
}

/** 在 KeyedNode 树中查找 targetKey 对应的节点. 递归 children, items, items[0].children. */
function findFieldNode(
  fields: ReadonlyArray<KeyedNode>,
  targetKey: string,
): KeyedNode | null {
  for (const f of fields) {
    if (f.key === targetKey) return f;
    if (Array.isArray(f.children) && f.children.length > 0) {
      const found = findFieldNode(f.children, targetKey);
      if (found) return found;
    }
    if (Array.isArray(f.items) && f.items.length > 0) {
      const item0 = f.items[0];
      if (item0) {
        if (item0.key === targetKey) return item0;
        if (Array.isArray(item0.children) && item0.children.length > 0) {
          const found = findFieldNode(item0.children, targetKey);
          if (found) return found;
        }
      }
    }
  }
  return null;
}

/**
 * BUG-006 #1 round 2: 沿 keyPath 走 templates schema 树, 找到对应 FieldNode.
 * 支持 object (children), array (items[0].key + items[0].children), table (columns).
 *
 * @param keyPath e.g. ["basic_info", "major_name"] / ["course_content", "module_name"]
 *                / ["graduation_requirements", "requirement_id"]
 * @returns FieldNode at the path, or null if any segment is missing
 */
function getFieldNodeAtPath(
  templates: ReadonlyArray<Pick<Template, "fields">>,
  keyPath: ReadonlyArray<string>,
): Field | null {
  if (keyPath.length === 0) return null;

  // Find keyPath[0] at top-level
  let current: Field | null = null;
  for (const t of templates) {
    const found = t.fields.find((f) => f.key === keyPath[0]);
    if (found) {
      current = found;
      break;
    }
  }
  if (!current) return null;

  // Walk the rest of the path
  for (let i = 1; i < keyPath.length; i++) {
    const seg = keyPath[i];
    if (!seg) return null;
    const next = findFieldNode(flattenCandidates(current), seg);
    if (!next) return null;
    // next 可能是 TableColumn (只用来取 label, 不会再深入), 也可能是 Field.
    // 这里需要把 next 当作 Field 继续走 keyPath[i+1..], 但 TableColumn 没有
    // children / items / columns, 所以如果后面还有 path segment, 下一轮
    // flattenCandidates 会得到 [], 走不下去 — 这是正确的: table 列下不会有
    // 嵌套.
    current = next as Field;
  }

  return current;
}

/**
 * BUG-006 #1 round 2: 解析一个 field keyPath 到对应的中文 label, 支持嵌套
 * 对象 / 数组 / 表格字段.
 *
 * @param templates 模板数组 (通常传整个 useTemplatesQuery 返的列表)
 * @param keyPath e.g. ["basic_info", "major_name"] for object children;
 *                ["course_content", "module_name"] for array item fields;
 *                ["graduation_requirements", "requirement_id"] for table columns.
 * @returns 模板配置的 label, 或 hard-coded map 的中文, 或最终 fallback 到 keyPath.join(".")
 */
export function getTemplateFieldLabelByPath(
  templates: ReadonlyArray<Pick<Template, "fields">>,
  keyPath: ReadonlyArray<string>,
): string {
  // 1. 沿 keyPath 走 schema 树
  const node = getFieldNodeAtPath(templates, keyPath);
  if (node) return node.label;

  // 2. keyPath.length === 1 时, 走老全树递归 (兼容)
  if (keyPath.length === 1) {
    const key = keyPath[0]!;
    for (const t of templates) {
      const found = findFieldNode(t.fields as ReadonlyArray<KeyedNode>, key);
      if (found) return found.label;
    }
  }

  // 3. hard-coded map fallback (legacy course 模板)
  const last = keyPath[keyPath.length - 1] ?? "";
  return HARDCODED_LABELS[last] ?? keyPath.join(".");
}

/**
 * 解析一个 field key 到对应的中文 label, 支持嵌套对象字段 (dot-path 形如
 * "basic_info.major_name"). 老 API, 委托到 getTemplateFieldLabelByPath.
 *
 * @param templates 模板数组 (通常传整个 useTemplatesQuery 返的列表)
 * @param key 单层 key (例如 "major_name")
 * @param prefix 父字段 key 上下文 (例如 "basic_info"), 用于构造 dot-path
 * @returns 模板配置的 label, 或 hard-coded map 的中文, 或最终 fallback 到 fullKey
 */
export function getTemplateFieldLabel(
  templates: ReadonlyArray<Pick<Template, "fields">>,
  key: string,
  prefix: string = "",
): string {
  if (prefix) {
    return getTemplateFieldLabelByPath(templates, [...prefix.split("."), key]);
  }
  return getTemplateFieldLabelByPath(templates, [key]);
}
