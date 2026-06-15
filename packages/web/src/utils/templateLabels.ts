// BUG-006 #1: 模板字段 label 解析工具.
//
// 真因 3 层:
// 1. templates[*].fields 只查 top-level, 不递归 children
// 2. dot-path 不支持 (basic_info.major_name 找不到 label)
// 3. hard-coded map 只列 16 个 legacy course 模板 key
//
// 5 步查找顺序 (优先级递减):
//   1. 模板 fields top-level exact match
//   2. 模板 fields 递归 children 搜索
//   3. dot-path 拆解: fullKey 含 ".", 找 top field, 递归 children
//   4. hard-coded map (legacy course 模板)
//   5. fallback: return fullKey 本身

import type { Template, Field } from "@/services/template";

/** 硬编码 label: 历史 course 模板 (course_name / semester 等 16 个) 在 templates
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

/** 递归在 fields 树中查找 targetKey 对应的 label. */
function findLabelInFields(
  fields: ReadonlyArray<Field>,
  targetKey: string,
): string | null {
  for (const f of fields) {
    if (f.key === targetKey) return f.label;
    if (Array.isArray(f.children) && f.children.length > 0) {
      const found = findLabelInFields(f.children, targetKey);
      if (found) return found;
    }
  }
  return null;
}

/**
 * 解析一个 field key 到对应的中文 label, 支持嵌套对象字段 (dot-path 形如
 * "basic_info.major_name").
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
  const fullKey = prefix ? `${prefix}.${key}` : key;

  // 1. top-level exact match
  for (const t of templates) {
    const field = t.fields.find((f) => f.key === fullKey);
    if (field) return field.label;
  }

  // 2. recursive children search (在所有 templates 的 fields 树里)
  for (const t of templates) {
    const found = findLabelInFields(t.fields, fullKey);
    if (found) return found;
  }

  // 3. dot-path: "basic_info.major_name" -> 找 basic_info 然后递归 children
  if (fullKey.includes(".")) {
    const [first, ...rest] = fullKey.split(".");
    const restPath = rest.join(".");
    for (const t of templates) {
      const topField = t.fields.find((f) => f.key === first);
      if (topField?.children && topField.children.length > 0) {
        const found = findLabelInFields(topField.children, restPath);
        if (found) return found;
      }
    }
  }

  // 4. hard-coded map (legacy course 模板兼容)
  return HARDCODED_LABELS[fullKey] ?? fullKey;
}
