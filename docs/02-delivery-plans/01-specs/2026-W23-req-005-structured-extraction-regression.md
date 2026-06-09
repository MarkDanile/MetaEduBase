# REQ-005 结构化抽取嵌套结构稳定性验收 — Spec

> Spec 入口：REQ-005（Backlog `Candidate` → 进入 `Ready` / `Planned` 的依据）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md`。
> Parent：REQ-004 模板匹配可解释化收口（已 Done）所遗留的"嵌套抽取仍依赖真实样例验收"信号（见 [W23 迭代 Review](../../01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md#review) 与 [P1 里程碑轨道 B](../../01-product-planning/02-milestones/01-validation-phase.md)）。

## 目标

为 `extract_template` 链路中"LLM 抽取 → JSON 解析 → 按模板结构落盘"的关键纯函数建立嵌套结构（object / array / table）回归。轨道 B "结构化抽取嵌套结构稳定性"行由"未完成 / 待收口"翻为"已通过 N 项用例"，阶段一关闭前无需真实 LLM 端到端也能证明 helper 在嵌套形态上的契约稳定。

## 范围

包含：

- 新增 `packages/server-python/tests/contexts/document/test_extract_template_prompts.py`，针对 `extract_template_prompts.build_fields_desc` / `try_parse` / `_merge_template_structured_data` 在 object / array / table 嵌套形态上的行为建立回归。
- 不修改任何业务代码：现有 `extract_template_prompts.py` 与 `_merge_template_structured_data` 已具备被纯函数测试的能力，本次只补"未覆盖的嵌套形态"用例。
- 文档回填：轨道 B 表格中"结构化抽取嵌套结构稳定性"行；Backlog REQ-005 状态 `Candidate` → `Done`；`current-work.md` 最近完成行；`work-log.md` 单行索引。

不包含：

- 端到端 PG + 真实 LLM 演示验收（独立 REQ-006）。
- 模板匹配选择器本身（REQ-004 / REQ-008 已覆盖）。
- `_build_parsed_structured_data` 现有 contract（`test_structured_data_contract.py` 已覆盖，行为不变）。
- `try_parse` 解析规则的扩展或新解析路径（只验证既有行为在嵌套输入下不退化）。
- 业务代码改动、prompt 文本调整、JSON Schema 校验、`init_by_ai` 或模板 API 契约。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | `build_fields_desc` 在 object 嵌套上输出稳定 | 给定 `fields=[Field(type="object", children=[Field(type="text", ...)])]`，输出形如 `key(label)[object型，含子字段：child_key(child_label)[text型]]`；含 2 层嵌套时递归描述子字段。 | 子字段被吞掉 / 标签错位 / 缺嵌套前缀 |
| AC-2 | `build_fields_desc` 在 array 嵌套上输出稳定 | 给定 `fields=[Field(type="array", items=[Field(type="object", children=[...])])]`，输出形如 `key(label)[array型，成员为object，含字段：item_key]`，**不**展开子字段。 | 误把 item 子字段展平 / 错把 type 写到行尾 |
| AC-3 | `build_fields_desc` 在 table 嵌套上输出稳定 | 给定 `fields=[Field(type="table", columns=[TableColumn(key=..., label=...)])]`，输出形如 `key(label)[table型，列：col1, col2]`。 | 列名缺失 / 列顺序错 / 把 type 写成 "table" 以外的串 |
| AC-4 | `build_fields_desc` 在混合嵌套上输出稳定 | 单字段列表含 object / array / table / text 各一例时，4 个描述按原顺序输出、4 种类型标识符全部正确。 | 顺序乱 / 类型标识符互换 |
| AC-5 | `try_parse` 解析嵌套 object / array / table | 输入含 ```json fenced JSON ```，且 JSON 内含 object（`basic_info`）、array（`teaching_process`）、table（`assessment`）三层嵌套时，输出对象**保持原嵌套结构**（`isinstance(v, dict) / list` 验证）。 | 嵌套被拍平 / list 元素不是 dict / table 行丢失 |
| AC-6 | `try_parse` 容错 think 标签后再解析 | 输入前缀包含 `<think>...</think>` 后接 markdown fence，输出对象结构与去掉 think 后的解析结果一致（验证 think 剥离不影响嵌套结构）。 | think 标签未剥离导致 `json_start` 找不到 `{` |
| AC-7 | `try_parse` 嵌套失败降级 | 输入形如 `{` 不闭合的坏 JSON，输出 `{}`（不抛异常、不污染既有 `template` 容器）。 | 抛 `JSONDecodeError` / 返回部分片段 |
| AC-8 | `_merge_template_structured_data` 在嵌套输入上保持浅拷贝 | 传入 `template_data` 含 `{"teaching_process": [{"step": "1"}]}`，返回对象 `merged["template"]["teaching_process"]` 是**新 list**（与入参 `is` 不等），但**列表元素 dict 仍是同一引用**（现有浅拷贝契约）。 | 改成深拷贝或共享引用 / 顺序错乱 |
| AC-9 | 命令可复现 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -q` 退出码 0；新文件至少 8 条用例（AC-1~AC-8）。 | 退出码非 0 / 用例数不足 |
| AC-10 | 文档回填 | 轨道 B "结构化抽取嵌套结构稳定性"行由"未完成 / 待收口"翻为"已通过 N 用例"结论；Backlog REQ-005 状态 `Candidate` → `Done`；`current-work.md` / `work-log.md` 同步。 | 未回填 |
| AC-11 | 工程门禁 | `scripts/check-engineering-docs` 退出码 0。 | 退出码非 0 |

## 接口与依赖

测试目标模块（**不修改**业务行为）：

- `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py:build_fields_desc`
- `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py:try_parse`
- `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py:_merge_template_structured_data`

测试 / 改动文件：

- 新增：`packages/server-python/tests/contexts/document/test_extract_template_prompts.py`（AC-1 ~ AC-9）
- 修改：`docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-10）
- 修改：`docs/01-product-planning/04-backlog.md`（AC-10）
- 修改：`docs/03-engineering-governance/current-work.md`（AC-10 收尾后）
- 修改：`docs/03-engineering-governance/work-log.md`（AC-10 单行索引）

测试工具沿用现有风格：

- 纯函数测试：直接 `from app.contexts.document.application.tasks.extract_template_prompts import build_fields_desc, try_parse, _merge_template_structured_data`，避免依赖 DB / LLM。
- `Field` / `TableColumn` 实体用 `app.contexts.template.domain.entity` 的 dataclass 显式构造。
- 既有 `tests/conftest.py` 不动；新测试**不引入** `client` / `auth_headers` fixture。

## 文件计划

新增：

- `packages/server-python/tests/contexts/document/test_extract_template_prompts.py`（AC-1 ~ AC-8 用例）

修改：

- `docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-10 轨道 B 行）
- `docs/01-product-planning/04-backlog.md`（AC-10 状态翻 Done）
- `docs/03-engineering-governance/current-work.md`（AC-10 收尾后）
- `docs/03-engineering-governance/work-log.md`（AC-10 单行索引）

业务代码改动范围：0 个文件（仅补测试 + 文档）。

## 风险与边界

- `try_parse` 当前使用 `re.search(r"```(?:json)?\s*(\{.*?\})\s*```", ...)`，`.*?` 是非贪婪匹配，**不会跨过嵌套 `{` 错配**。本 spec 不改变解析行为，只验证"含嵌套的 JSON 能被原样返回"。
- `_merge_template_structured_data` 当前是 `dict(template_data)` 浅拷贝：外层 dict 新建，嵌套值仍是同一引用。本 spec AC-8 锁定该浅拷贝契约；若未来需深拷贝，单独技术债评估。
- `build_fields_desc` 中 array 类型的描述符故意只取 `items[0]` 的 key 作为"含字段"信息，不递归展开；这是与 prompt 复杂度平衡的现状，不在本 spec 改动。
- 测试不调用 LLM 也不连接 DB，可在 `metaedu_test` 不可用的本地环境直接运行。

## 不在范围 / 后续任务

| ID | 说明 | 归属 |
|----|------|------|
| REQ-006 | 端到端 PG + 真实 LLM 演示验收 | 单独 task |
| TD-??? | 若 LLM 实际响应在 object / array / table 嵌套形态上偏离本 spec 锁定的契约（如 `try_parse` 把数组元素拍平成字符串），入账 | 触发现入账 |
