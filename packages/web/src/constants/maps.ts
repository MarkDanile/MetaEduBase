export const domainMap: Record<string, string> = {
  electronics_info: "电子与信息",
  smart_manufacturing: "智能制造",
  finance_commerce: "财经商贸",
  medical_health: "医药健康",
  education_sports: "教育与体育",
  civil_engineering: "土木建筑",
  transportation: "交通运输",
  agriculture: "农林牧渔",
  art_design: "文化艺术",
  public_service: "公共管理",
};

export const levelMap: Record<string, string> = {
  professional: "专业",
  course: "课程",
  chapter: "章节",
  knowledge_point: "知识点",
  skill_point: "技能点",
  operation_step: "操作步骤",
};

// REQ-060 D-1: roleMap 统一到后端 RoleEnum 7 角色（BUG-017 冻结）
export const roleMap: Record<string, string> = {
  super_admin: "超级管理员",
  data_admin: "数据管理员",
  admin: "管理员",
  leader: "招商负责人",
  teacher: "教师",
  employee: "员工",
  student: "学生",
};

export const roleShortMap: Record<string, string> = {
  super_admin: "超管",
  data_admin: "数据",
  admin: "管理",
  leader: "招商",
  teacher: "老师",
  employee: "员工",
  student: "同学",
};

export const resourceTypeMap: Record<string, string> = {
  document: "文档",
  video: "视频",
  image: "图片",
  audio: "音频",
  other: "其他",
};
