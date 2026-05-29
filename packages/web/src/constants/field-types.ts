export const FIELD_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
  { value: 'object', label: '对象组' },
  { value: 'table', label: '表格' },
  { value: 'array', label: '数组' },
] as const

export type FieldType = typeof FIELD_TYPES[number]['value']

export const COLUMN_TYPES = [
  { value: 'text', label: '文本' },
  { value: 'textarea', label: '多行文本' },
  { value: 'number', label: '数字' },
] as const