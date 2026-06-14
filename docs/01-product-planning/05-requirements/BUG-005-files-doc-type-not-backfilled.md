# BUG-005: `parse` 任务完成后未回写 `files.doc_type` / `template_id` → 100% files.doc_type NULL

Status: 🔵 Ready
Priority: P1
Milestone: P1 RAG 治理 / 模板溯源
Source: 2026-06-14 全链路评估人才培养方案文件时发现（用户提供样本 + Claude Code 真 PG 审计）

## 背景

`parse` 任务完成后已经产生 `structured_data.template.matched_type`（如 `人才培养方案`）和 `structured_data.template.id`（如 `50070278-...`），但 `files.doc_type` 字段始终未回写——dev 库 1 条样本 `files.doc_type=NULL`、全库 `file_metadata` 覆盖率 0%（`scripts/ai/evidence_coverage_report.py`）。

这导致：

1. `evidence_coverage_report` 的 `file_metadata` 指标**永远是 0%**，掩盖真实的抽取质量。
2. `files.doc_type` 在 DB 层是"应当填充"的事实源（REQ-009 / TD-009 contract）但实际未生效。
3. AI Chat 模板溯源、跨文件模板统计、`ResourceLibrary` 列表 doc_type 筛选受影响。
4. 与 `BUG-004` 同类模式——`structured_data` 抽取正确但**反向回写**到 `files` 表失败。

## 复现路径

1. 上传 `01-人才培养方案环境监测技术专业.pdf` 到 Resource Library。
2. 等 parse + extract_template 任务成功（`files.status = 'processed'` + `files.structured_data` 包含 `template.matched_type = '人才培养方案'`）。
3. 真 PG 查询：
   ```sql
   SELECT
     filename,
     doc_type,
     status,
     structured_data->'template'->>'matched_type' AS sd_matched_type,
     structured_data->'template'->>'id' AS sd_template_id
   FROM metaedu.files
   WHERE filename LIKE '%人才培养%';
   ```
4. 期望：`doc_type = '人才培养方案'`（与 `sd_matched_type` 一致）+ 某种 `template_id` 字段（`files.template_id` 字段**当前不存在**，需新增）。
5. 实际：`doc_type = NULL`（即使 `sd_matched_type = '人才培养方案'` 已正确抽取）。

## 期望行为

- `parse` 或 `extract_template` 任务成功结束后：
  - `files.doc_type = structured_data.template.matched_type`（如有）或 `structured_data.template.basic_info.doc_type`（如有）
  - 新增 `files.template_id` 字段（uuid FK → `templates.id`）= `structured_data.template.id`
  - 缺模板时 `files.doc_type = ''` 而非 NULL（保持 NOT NULL 约束如存在）
- `evidence_coverage_report` 的 `file_metadata` 覆盖率在新增样本后**应非 0%**。
- 不引入新 bug：保持现有 `parse.py` / `extract_template.py` 业务行为不变；仅追加 1~3 行回写。

## 初步怀疑点

- `parse.py:115-130`（_build_parsed_structured_data 调用 + chain to chunk）—— 未写 `files.doc_type`。
- `extract_template.py:_do`（同 TD-057 slice 5）—— 也未写。
- 可能根因（待验证）：
  1. **`files` 表没有 `template_id` 字段**（schema 已确认无），需 alembic 迁移
  2. `parse.py` 完成 parse 后**未做反向回写**，把"模板匹配"和"文件归类"两件事分开
  3. 模板匹配逻辑 `filename substring match` 在 parse 完成后即可确定（早于 extract_template），**没有**反写链路

## 影响范围

- 1 个 alembic 迁移（新增 `files.template_id` 字段 + index）
- `parse.py` 或 `extract_template.py` 修改 1~3 行（回写 doc_type + template_id）
- 历史数据 backfill：1 条（dev 库），prod 待用户审计
- 测试：1 个 mock pytest（verify 回写）

## 关联债

- TD-009：前后端契约漂移（`files.doc_type` 字段在 DTO 定义中已存在，本 BUG 是回写缺失，不是契约缺失）
- TD-044（已完成）：建立 P1 RAG 基线 `file_metadata 0%`——本 BUG 修复后可重测基线
- TD-046（已完成）：P1 RAG 数据债批次——本 BUG 修复后需更新 backfill 工具以补 `files.template_id` 列

## 完成标准

- `files.doc_type` 在 parse 成功且有 matched_type 后被回写
- `files.template_id` 新字段已迁移 + 回写
- `evidence_coverage_report` 跑出 `file_metadata > 0%`（新增样本后）
- 1 mock pytest 锁死回写逻辑
- 不引入新 bug：保持现有 chunk / embed / extract_template 任务通过

## 验证方式

- 重新上传 1 个 PDF 走完 pipeline → 查 `files.doc_type` 与 `files.template_id` 均填充
- 跑 `scripts/ai/evidence_coverage_report.py` → `file_metadata` 覆盖率 ≥ 1 / N
- `pytest` 全 mock-based 414+ 仍 pass
- `ruff clean` / `git diff --check clean` / `check-engineering-docs` 退出码 0
- alembic upgrade head 顺利（真 PG 测试）
- alembic downgrade -1 + upgrade head 幂等

## 交付记录

- 2026-06-14 登记（入手工具：Claude Code / 全链路评估 2026-06-14）。
- 本 BUG 5 字段齐全（事实源 / 证据 / 复现 / 期望 / 怀疑点），按 bug fix 模式入账 🔵 Ready。
- 实际修复留维护者下个 PR。
