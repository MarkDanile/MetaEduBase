# REQ-055: 实体关系发现与本体演化

Status: ⚪ Idea
Priority: P1
Milestone: P3
Domain: AI Workspace / Data Platform / Ontology / 产业园区
Source: REQ-054 复查反馈 - entity_types 从预设白名单改为动态发现后，需要 V2/V3 智能层
Related: REQ-054 / REQ-052 / REQ-046
External:
- Palantir Foundry Ontology（本体从数据中发现，不是预设）

## 背景

REQ-054 V1 实现了 entity_types 从"预设白名单"到"动态发现"的转变：
- 创建 catalog 时不声明 entity_types（零门槛）
- 上传数据集时 entity_type 自由填写 + 持久化到 `datasets.entity_type`
- catalog.entity_types 从 datasets 聚合 DISTINCT entity_type
- 新 entity_type 首次出现 -> warning 提示

但 V1 只是"用户声明 + 系统记录"，没有智能层。用户真正想要的是（REQ-054 复查原话）：

> "后续可以上传数据集，并且分析数据集中各个实体之间的关系，动态聚合相关的 entity_type。如资产项目、合同级别、客户级别、账单级别等。若出现孤儿实体数据，则需要提醒到用户，该实体类型是否与本主题有脱离关系。而不是一开始就要定义好。"

这需要 V2（LLM 辅助关系发现）+ V3（孤儿检测 + 治理）两层能力。

## 目标

建设 catalog 级别的实体关系发现与本体演化能力，让平台从"用户手动声明 entity_type"升级为"系统自动发现实体关系 + 孤儿检测 + 治理建议"。

核心目标：

- **V2 - LLM 辅助关系发现**：上传数据集后，LLM 看字段名 + 样本数据，推断 entity_type + 列映射 + 跨数据集关系。
- **V2 - 实体关系图可视化**：catalog 详情页展示"实体关系图"（customer -> contract -> bill）。
- **V2 - semantic_model 自动生成草稿**：LLM 根据字段名 + 样本生成 column_mapping 草稿，用户确认。
- **V3 - 孤儿实体检测**：上传的数据集如果字段无法关联到该 catalog 下任何其他数据集 -> 标记"孤儿" + 提醒。
- **V3 - entity_type 合并/重命名**：发现 `company` 和 `customer` 其实是同一个 -> 合并。
- **V3 - 关系图健康度**：评分（孤儿比例 / 关联密度 / 字段匹配率）。
- **V3 - 主题归属建议**：孤儿实体可能属于另一个主题，建议"是否迁移到教育数据库"。

## 能力边界

| 层级 | 能力 | 说明 |
|------|------|------|
| V2 关系发现 | LLM 推断 entity_type + 列映射 | 上传 CSV 后 LLM 看字段名 + 样本，建议 entity_type + column_mapping |
| V2 关系发现 | 跨数据集关系推断 | 字段名匹配（customer_id / company_name）+ LLM 判断，推断外键关系 |
| V2 可视化 | 实体关系图 | catalog 详情页展示实体关系图（节点 = entity_type，边 = 关系） |
| V2 语义层 | semantic_model 草稿自动生成 | LLM 生成 column_mapping 草稿，用户确认后激活 |
| V3 治理 | 孤儿实体检测 | 字段无法关联到已有实体 -> 标记孤儿 + 提醒 |
| V3 治理 | entity_type 合并/重命名 | 发现重复/相似 entity_type -> 合并建议 |
| V3 治理 | 关系图健康度 | 评分（孤儿比例 / 关联密度 / 字段匹配率） |
| V3 治理 | 主题归属建议 | 孤儿实体可能属于另一个 catalog -> 迁移建议 |

## 与 REQ-054 的关系

| 能力 | REQ-054 V1（已实施） | REQ-055（本次） |
|------|------|------|
| entity_type 来源 | 用户上传时自由填写 | LLM 辅助推断 |
| entity_type 注册 | 系统记录到 datasets.entity_type | 同 + LLM 建议列映射 |
| 跨数据集关系 | 不感知 | 自动发现外键关系 |
| 孤儿检测 | 简单版（首次出现 warning） | 完整版（字段关联分析 + 主题归属建议） |
| 语义层 | 手动配置 | LLM 自动生成草稿 |
| 可视化 | 语义层 tab 占位 | 实体关系图 |

## 推荐实现路径

### V2: LLM 辅助关系发现

- 上传 CSV 后，取前 N 行样本 + 字段名，调 LLM 推断 entity_type + column_mapping
- 跨数据集字段名匹配（customer_id / company_name / bill_id）-> 推断外键关系
- 实体关系图可视化（AntV G6 或类似）
- semantic_model 草稿自动生成 + 用户确认 UI

### V3: 孤儿检测 + 治理

- 孤儿检测算法：字段无法关联到已有实体关系图 -> 标记孤儿
- LLM 判断主题归属（"学生成绩"是否属于"产业园区"主题）
- entity_type 合并/重命名 UI
- 关系图健康度评分
- 主题迁移建议

## 验收标准（待塑形时细化）

| ID | 内容 |
|----|------|
| AC-1 | 上传 CSV 后 LLM 推断 entity_type + column_mapping，准确率 ≥80% |
| AC-2 | 跨数据集外键关系自动发现，召回率 ≥70% |
| AC-3 | 实体关系图可视化（节点 + 边 + 交互） |
| AC-4 | semantic_model 草稿自动生成，用户确认后激活 |
| AC-5 | 孤儿实体检测 + 提醒 |
| AC-6 | entity_type 合并/重命名 |
| AC-7 | 关系图健康度评分 |

## 非目标

- 不做全自动（LLM 推断结果必须用户确认）
- 不做跨 catalog 实体对齐（V1 各 catalog 独立，REQ-054 已定）
- 不做实时关系发现（上传后异步分析）
- 不替换 REQ-054 V1 的"用户声明 + 系统记录"（V2 是增强，不是替换）

## Open Questions

- LLM 推断 entity_type 的准确率如何保证？需要多少样本？
- 跨数据集字段匹配的算法：纯字段名匹配 vs LLM 语义匹配 vs 混合？
- 实体关系图用什么库？AntV G6 vs D3 vs 其他？
- 孤儿检测的阈值：多少字段不匹配算孤儿？
- 主题归属建议：LLM 判断 vs 规则引擎？

## Delivery Record

| 日期 | 动作 | 事实 |
|------|------|------|
| 2026-07-08 | 登记 | REQ-054 复查反馈 - entity_types 动态发现 V1 已实施（PR #422），V2/V3 智能层登记为 REQ-055。 |
