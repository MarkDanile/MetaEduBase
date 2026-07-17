# BUG-015: QueryPanel 输入框冗余 + 查询背景强制填写

Status: 🟣 Shaping
Priority: P2
Milestone: P3
Domain: AI Workspace / Data Platform / QueryPanel / UX
Source: 2026-07-17 数据库-中高职教育数据库 详情页面-问数 tab 用户测试反馈
Related: REQ-052 / REQ-054 / REQ-056

## 现象

在"中高职教育数据库"详情页问数 tab 测试时，用户反馈 2 个问题：

1. **为什么有这么多选项？** 问数面板有 3 个输入框：
   - 自然语言问题（核心入口）
   - 企业全称（已确认）
   - 查询背景（必填，≥5 字）

   "企业全称"在教育库语义下不存在（教育主题没有"企业"概念），用户看到这个字段会困惑。

2. **输入后查询失败。** 测试数据：
   - 输入框 1：获得奖学金的人员数量是多少？
   - 输入框 2：（空）
   - 输入框 3：获得奖学金的人员数量是多少？
   - 实体类型：未选（教育库没数据集指定 entity_type）

   失败原因：用户没意识到 entity_type 必填 + 不知道该填什么。

## 根因

REQ-052 设计 AskRequest 时假设了"产业园区"场景：
- `confirmed_company_name` 是为园区资管"企业"概念设计
- `business_purpose` 强制必填是审计治理要求
- 但 REQ-054 引入 catalog（多主题）后，教育/医疗/金融等其他主题没有"企业"概念

REQ-052 §12 审计要求：每条查询写入 query_audit_log（含 user_id / business_purpose / query_plan / result_count），但不要求 business_purpose 强制必填。

## 目标

1. 移除"企业全称"输入框（不通用）
2. 简化"查询背景"为可选（不强制字长）
3. audit_log 仍记录 user_id + question + query_plan + result_count（核心审计信息齐全）
4. entity_type 智能提示：上传时若是新 entity_type，warning 已实现；问数时下拉为空时提示更明确

## 验收标准

- AC-1: QueryPanel 移除 "企业全称" 输入框
- AC-2: AskRequest 移除 `confirmed_company_name` 字段
- AC-3: "查询背景" 改为可选（前端不强制 minlength=5；后端 business_putable 改 nullable）
- AC-4: audit_log 仍记录 user_id + question + query_plan + result_count
- AC-5: entity_type 下拉空时提示更明确（含"如何上传"指引）
- AC-6: 现有 REQ-056 测试不破坏（215+ tests pass）

## 非目标

- 不做 entity_type 自动推断（LLM 推断列 V2 范围）
- 不改 LLM 行为（不增加"自动问数"按钮）
- 不重做 QueryPanel UI 设计

## 建议实施顺序

1. 后端：`AskRequest` 移除 `confirmed_company_name`；`business_purpose` 改 Optional
2. 后端：`query_audit_log.business_purpose` 改 nullable（alembic 020_nullable_business_purpose）
3. 后端：`QueryService._audit` 不再强制 business_purpose
4. 前端：QueryPanel.vue 移除 2 个 input，更新 placeholder + hint
5. 前端：data-query.ts service `AskRequest` 同步移除
6. 现有测试更新（business_purpose 必填断言改为可选）
7. 新测试：query_audit_log 接受 NULL business_purpose
8. ruff 0 / check-engineering-docs 0

## Open Questions

- query_audit_log 改 nullable 后，旧数据怎么办？——保持兼容（nullable 列已有数据不丢失）
- 前端 history store 是否需要清理 companyName 字段？——是（不要保留 dead field）

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-07-17 | 登记 | 中高职教育数据库测试反馈，3 个输入框冗余 + 查询背景强制填写增加摩擦；登记 BUG-015 走流程。 |
