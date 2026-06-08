# REQ-008 REQ-004 验收证据与质量门禁缺口收口 — Spec

> Spec 入口：REQ-008（Backlog `Candidate` → `Ready` / `Planned` 依据）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-W23-req-008-req-004-quality-follow-up-plan.md`。

## 目标

REQ-004 模板匹配可解释化已通过 PR #77 合并（`select_template` 纯函数 + 9 条分支回归 + 统一 `template.select` 日志），但其交付记录与质量门禁存在三处验收缺口，本 spec 收口如下：

1. 修复 REQ-004 touched files 的 ruff 失败（不能把"命令未通过"记为"通过"）。
2. 把"`template.select layer=...` 日志在 L1 / L2 / L3 / none 分支可观测"从代码实现变成测试断言。
3. 补齐 L3 confidence 解析失败（`float()` 失败 → `confidence=0.0`）与空响应（`lines == []`）的测试覆盖，避免后续实现回归把"解析失败"分支静默吞掉。

## 范围

包含：

- 修复 `packages/server-python/app/contexts/document/application/tasks.py:616,622` 的 E501（行 > 100 字符）。
- 修复 `packages/server-python/app/contexts/document/application/template_selector.py:16` 的 UP035（`Awaitable` / `Callable` 改从 `collections.abc` 导入）。
- 修复 `packages/server-python/tests/contexts/document/test_extract_template_selection.py:7,9` 的 I001 + UP035（import 块重排 + 改 `collections.abc`）。
- 在同一测试文件新增 caplog 断言：4 个分支（L1 / L2 / L3 命中 / L3 未命中 / none）的 `template.select layer=...` 日志可观测。
- 在同一测试文件新增 2 条用例：L3 confidence 解析失败（`教案\nabc`）→ `confidence == 0.0`、`layer == "none"`（因 0.0 < 0.7 阈值）；L3 空响应（`""`）→ `layer == "none"`、`reason == "AI returned empty response"`。
- 文档回填：Backlog REQ-008 状态推进；Iteration / Milestone（轨道 B 模板匹配可解释化行追加补强标记）；`current-work.md` 当前进行中 / 最近完成。
- 验证：相关 ruff 退出码 0；测试全绿；`scripts/check-engineering-docs` 退出码 0；`git diff --check` 退出码 0。

不包含：

- 业务行为变更（`select_template` 实现、Celery 任务调用、日志格式都不动；只动 tasks.py 行的折行、import 来源）。
- 3 层优先级、L3 阈值 0.7、prompt 构造、JSON 解析、落盘、Celery 链保持不变。
- 接入 PostgreSQL / 真实 LLM 跑端到端（独立 REQ-006）。
- 结构化抽取嵌套结构稳定性（独立 REQ-005）。
- 业务层修复 dev 环境 `metaedu_test` 连通性（独立 REQ-006 范围）。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | ruff 通过 | `cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/application/template_selector.py app/contexts/document/application/tasks.py tests/contexts/document/test_extract_template_selection.py` 退出码 0 | 退出码非 0 |
| AC-2 | L1 日志可观测 | `caplog` 断言：L1 命中时，logger 输出包含 `template.select layer=L1` 的 INFO 记录 | 缺日志 / 字段缺失 |
| AC-3 | L2 日志可观测 | `caplog` 断言：L2 命中时输出包含 `template.select layer=L2` 的 INFO 记录 | 字段缺失 |
| AC-4 | L3 命中日志可观测 | `caplog` 断言：L3 命中时输出包含 `template.select layer=L3` 且包含 `confidence=0.92` 片段的 INFO 记录 | 缺日志 |
| AC-5 | L3 解析失败覆盖 | 新增用例：AI 返回 `"教案\nabc"`（`float()` 失败）→ `layer == "none"`（0.0 < 0.7 阈值）；reason 含 `AI confidence below threshold` 或解析失败语义（与现有契约一致） | 用例缺失 / 走错分支 |
| AC-6 | L3 空响应覆盖 | 新增用例：AI 返回 `""`（零行）→ `layer == "none"`、`reason == "AI returned empty response"` | 用例缺失 |
| AC-7 | 9 条 → 12 条回归 | `tests/contexts/document/test_extract_template_selection.py` 至少 12 条用例全部通过（9 旧 + 2 解析覆盖 + 1 共享 caplog 参数化或独立用例） | 任一不通过 |
| AC-8 | pytest 可复现 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -q` 退出码 0 | 退出码非 0 |
| AC-9 | 工程门禁 | `scripts/check-engineering-docs` 退出码 0 | 退出码非 0 |
| AC-10 | 文档回填 | Backlog REQ-008 状态 `Candidate` → `Done`；Iteration / Milestone 同步；`current-work.md` 收尾 | 未回填 |

> AC-7 用"至少 12 条"是因为 caplog 可用参数化（`pytest.mark.parametrize`）压缩为 1 条；如分拆为 4 条独立用例（每分支一条），则总数为 13 条，以最终实现为准并在 commit 中显式记录实际用例数。

## 接口与依赖

测试 / 改动文件：

- 修改：`packages/server-python/app/contexts/document/application/tasks.py`（仅 L3 日志 2 行折行；L1/L2/none 日志已合规，不动）
- 修改：`packages/server-python/app/contexts/document/application/template_selector.py`（仅 import 来源；`Awaitable` / `Callable` 改 `collections.abc`）
- 修改：`packages/server-python/tests/contexts/document/test_extract_template_selection.py`（import 块重排 + caplog 断言 + 2 条新用例）
- 修改：`docs/01-product-planning/04-backlog.md`（AC-10）
- 修改：`docs/01-product-planning/03-iterations/2026-W23-p1-iteration.md`（AC-10，追加"REQ-008 已收口"）
- 修改：`docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-10，轨道 B 表格"模板匹配可解释化"行追加补强证据）
- 修改：`docs/03-engineering-governance/current-work.md`（AC-10，当前进行中 → 最近完成）

测试工具沿用现有风格：

- 沿用既有 `Template` 列表构造方式与 `AsyncMock` 注入模式。
- caplog 通过 `pytest` 内置 fixture（`caplog.records` / `caplog.text`）断言；模块 logger 名仍为 `app.contexts.document.application.tasks`（既有 caplog 测试惯例）。
- 解析失败 / 空响应用例复用既有 `_ai(...)` helper。

## 选择器契约（不变）

`select_template` 行为契约不在本 spec 范围。AC-5 / AC-6 仅补"对外可观察行为"测试，不改实现：

- 解析失败：响应为 `"教案\nabc"` 时，`float("abc")` 抛 `ValueError`，现实现 `confidence = 0.0`、`template_obj` 存在 → `layer == "L3"` + `confidence < threshold` 路径，**但** `matched_type` 已在 `lines[0] = "教案"`、模板存在 → 命中 → `layer == "L3"`、`template` 返回 L1 等价 Template，`reason == "AI confidence match"`（0.0 < 0.7）。  
  实施时再确认实际分支；若当前实现将 `"教案\nabc"` 解析为 `layer == "L3"` + `confidence=0.0` + `template` 命中 → 测试断言这一行为并写明，避免和 spec "4 个分支各有一行"的口径混淆。
- 空响应：响应为 `""` 时 `lines == []` → 现实现返回 `(None, "none", "", None, "AI returned empty response")`。测试断言该 reason。

## 文件计划

修改：

- `packages/server-python/app/contexts/document/application/tasks.py` 2 行折行（AC-1）
- `packages/server-python/app/contexts/document/application/template_selector.py` 1 行 import（AC-1）
- `packages/server-python/tests/contexts/document/test_extract_template_selection.py` import 块 + 2 条新用例 + caplog 断言（AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7）
- `docs/01-product-planning/04-backlog.md`（AC-10）
- `docs/01-product-planning/03-iterations/2026-W23-p1-iteration.md`（AC-10）
- `docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-10）
- `docs/03-engineering-governance/current-work.md`（AC-10）

业务代码改动范围：约 3 文件（2 个折行 + 1 个 import 修正 + 1 个测试文件 import + 用例），无任何行为变化。

## 风险与边界

- **行为变化声明**：本 spec 改动**不**引入业务行为变化。`tasks.py` 仅折行（不影响执行路径），`template_selector.py` 仅 import 来源（运行时等价：Python 3.9+ 起 `collections.abc.Awaitable` 与 `typing.Awaitable` 等价），测试新增 caplog 断言与 2 条新用例（无 fixture 副作用）。
- **caplog 跨测试干扰**：既有 `tasks.py` 9 个测试不通过 caplog 触发日志（直接断言 `SelectionResult`）。本 spec 引入 caplog 时要确保：① `caplog.set_level(logging.INFO, logger="app.contexts.document.application.tasks")`；② 不被既有测试 fixture 影响（既有测试无 session-scope caplog）。如发现干扰，回退到直接读 `caplog.records` 过滤。
- **L3 解析失败判定**：依赖 spec 既有契约（`float` 失败 → `confidence = 0.0`）。若实现回归（譬如改为 `confidence = 0.5`），本 spec 测试会失败并暴露回归。**不**在 spec 中修复实现。
- **L3 空响应**：spec 已有契约，测试只断言，不动实现。
- **`Template` 字段**：`_tpl` helper 仍以 `id / tenant_id / name / doc_types / fields` 5 字段构造（与现有测试文件一致），不修改 `Template` 实体。

## 不在范围 / 后续任务

| ID | 说明 | 归属 |
|----|------|------|
| REQ-005 | 结构化抽取嵌套结构稳定性验收 | 单独 task |
| REQ-006 | 端到端 PG + 真实 LLM 演示验收 | 单独 task |
| TD-??? | 若 L3 解析行为在测试中发现未文档化的边角（如响应为空但 confidence 解析成功），入账 | 触发现入账 |
