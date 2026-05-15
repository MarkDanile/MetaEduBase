// Resource pipeline task types (6 steps)
export const DOC_TASK_STEPS = [
  { type: "parse", label: "文档解析", icon: "FileSearch" },
  { type: "chunk", label: "结构切片", icon: "Scissors" },
  { type: "embed", label: "向量化", icon: "Cpu" },
  { type: "index_tsv", label: "全文索引", icon: "Search" },
  { type: "extract_template", label: "模板抽取", icon: "LayoutTemplate" },
  { type: "extract_kg", label: "知识图谱", icon: "GitBranch" },
] as const

// Dataset pipeline task types (3 steps)
export const DS_TASK_STEPS = [
  { type: "ds_parse", label: "数据解析", icon: "FileSpreadsheet" },
  { type: "ds_embed", label: "向量化", icon: "Cpu" },
  { type: "ds_extract_kg", label: "知识图谱", icon: "GitBranch" },
] as const

// Task status display
export const TASK_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "等待中", color: "amber" },
  running: { label: "进行中", color: "blue" },
  success: { label: "已完成", color: "green" },
  failed: { label: "失败", color: "red" },
}

// File status display
export const FILE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  uploaded: { label: "已上传", color: "amber" },
  processing: { label: "处理中", color: "blue" },
  processed: { label: "已完成", color: "green" },
  failed: { label: "失败", color: "red" },
}

// KG status display
export const KG_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: "待构建", color: "amber" },
  building: { label: "构建中", color: "blue" },
  done: { label: "已完成", color: "green" },
  failed: { label: "失败", color: "red" },
}

// Doc type options
export const DOC_TYPE_OPTIONS = [
  { value: "教案", label: "教案" },
  { value: "授课计划", label: "授课计划" },
  { value: "课程标准", label: "课程标准" },
  { value: "试卷", label: "试卷" },
  { value: "其他", label: "其他" },
] as const
