# REQ-004 模板匹配可解释化收口 — Spec

> Spec 入口：REQ-004（Backlog `Candidate` → 进入 `Ready` / `Planned` 的依据）。本文件是验收口径与边界的事实源；实施拆分见 `docs/02-delivery-plans/02-plans/2026-W23-req-004-template-match-explainability-plan.md`。

## 目标

把 `extract_template` Celery 任务内的"doc_type → 文件名 → AI 置信度"三层模板选择逻辑从内嵌代码抽成可独立单测、可观测日志的纯函数，并为 L1 / L2 / L3 / 无命中四个分支建立回归测试与可解释日志。轨道 B "模板匹配可解释化"行由"未完成 / 待收口"翻为"已通过 N 项用例"。

## 范围

包含：

- 新增 `packages/server-python/app/contexts/document/application/template_selector.py`，导出 `select_template(chunks_text, doc_type, filename, templates, ai_chat)`，返回 `SelectionResult(template: Template | None, layer: Literal["L1","L2","L3","none"], matched_type: str, confidence: float | None, reason: str)`。`ai_chat: Callable[[str], Awaitable[str]]` 由调用方注入，便于测试时替换。
- `extract_template` Celery 任务调用 `select_template` 替代内嵌代码；命中分支和未命中分支都按统一格式写 INFO / WARNING 日志。
- 业务行为不变：命中模板后 prompt 构造、JSON 解析、`structured_data["template"]` 落盘、KCelery 链全部保持。
- 新增 `packages/server-python/tests/contexts/document/test_extract_template_selection.py`，覆盖 9 个分支（见 AC-3）。
- 文档回填：轨道 B 表格中"模板匹配可解释化"行；Backlog REQ-004 状态；`current-work.md` 最近完成行。

不包含：

- 改变三层优先级或 L3 阈值（保持 0.7）。
- 接入真实 PostgreSQL / 真实 LLM 跑端到端（独立 REQ-006）。
- `Template` 领域模型、Repository、`doc_types` 字段类型或数据库 schema 变更。
- 调整 `init_by_ai` 行为或模板 API 契约。
- 结构化抽取嵌套结构稳定性（独立 REQ-005）。

## 验收标准

| ID | 验收点 | 通过条件 | 失败条件 |
|----|--------|----------|----------|
| AC-1 | 选择器可独立调用 | `app/contexts/document/application/template_selector.py` 存在并导出 `select_template` 与 `SelectionResult`；不依赖 Celery / DB session | 命名错 / 引入 session 依赖 |
| AC-2 | 三层优先级不变 | 同一输入同时存在 L1 / L2 / L3 候选时，输出 `layer == "L1"` 且 `template` 为 L1 命中项 | 选择错层 |
| AC-3 | L1 命中日志 | L1 命中时，`extract_template` 输出包含 `template.select layer=L1 ...` 的 INFO 日志 | 缺日志 |
| AC-4 | L2 命中日志 | L2 命中时输出 `template.select layer=L2 ...`；L2 当前已 log，验证保留并加 `layer=` 字段 | 字段缺失 |
| AC-5 | L3 命中日志 | L3 命中时输出 `template.select layer=L3 confidence=...`；命中未配置 / 低于阈值 / 异常 / 解析失败 4 个分支都各有一行 | 缺分支日志 |
| AC-6 | 无命中日志 | L1 / L2 / L3 都未命中时输出 `template.select layer=none reason=...` 的 WARNING | 完全无日志 |
| AC-7 | 9 条回归用例 | `tests/contexts/document/test_extract_template_selection.py` 至少 9 条用例全部通过 | 任一不通过 |
| AC-8 | 命令可复现 | `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -q` 退出码 0 | 退出码非 0 |
| AC-9 | 文档回填 | 轨道 B "模板匹配可解释化"行由"未完成 / 待收口"翻为"已通过 N 用例"结论；Backlog REQ-004 状态 `Candidate` → `Done` | 轨道 B "模板匹配可解释化"行仍写"未完成 / 待收口"，或 Backlog REQ-004 状态非 `Done` |
| AC-10 | 工程门禁 | `scripts/check-engineering-docs` 退出码 0 | 退出码非 0 |

## 接口与依赖

测试目标模块（不可改业务行为）：

- `packages/server-python/app/contexts/document/application/tasks.py:extract_template`（修改实现以调用新选择器，不改变 prompt / 落盘 / Celery 链）
- `packages/server-python/app/contexts/document/application/template_selector.py`（新建）

测试 / 改动文件：

- 新增：`packages/server-python/app/contexts/document/application/template_selector.py`
- 新增：`packages/server-python/tests/contexts/document/test_extract_template_selection.py`
- 修改：`packages/server-python/app/contexts/document/application/tasks.py`（仅在三层选择片段调用新函数；其余段落保持）
- 修改：`docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-9）
- 修改：`docs/01-product-planning/04-backlog.md`（AC-9）
- 修改：`docs/03-engineering-governance/current-work.md`（AC-9 收尾后回填最近完成）

测试工具沿用现有风格：

- 纯函数测试：构造 `Template` 列表（含 `id` / `doc_types` / `fields`），传入 `select_template`；`ai_chat` 用 `AsyncMock(return_value=...)` 注入。
- `Template` 实例用最简单的 `Template(id=..., tenant_id=..., name=..., doc_types=[...], fields=[...], ai_prompt=None, ai_context=None, source_file_id=None, created_at=..., updated_at=...)` 直接构造，避免依赖 DB。
- 既有 `tests/conftest.py` 不动；新测试**不引入** `client` / `auth_headers` fixture（纯函数测试不需 HTTP）。

## 选择器契约

```python
# app/contexts/document/application/template_selector.py
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal
from app.contexts.template.domain.entity import Template

Layer = Literal["L1", "L2", "L3", "none"]

@dataclass
class SelectionResult:
    template: Template | None
    layer: Layer
    matched_type: str
    confidence: float | None
    reason: str

async def select_template(
    chunks_text: str,
    doc_type: str | None,
    filename: str,
    templates: list[Template],
    ai_chat: Callable[[str], Awaitable[str]],
    *,
    confidence_threshold: float = 0.7,
) -> SelectionResult: ...
```

行为契约（与现有 `tasks.py:584-663` 等价）：

- L1：若 `doc_type` 存在且非空串，在 `templates` 中找第一个 `doc_type in t.doc_types` 的模板；命中返回 `SelectionResult(t, "L1", doc_type, None, "exact doc_type match")`。
- L2：若 L1 未命中且 `filename` 非空，遍历 `templates`，对每个 `t.doc_types` 中非空字符串 `dt`，若 `dt in filename` 则命中；返回 `SelectionResult(t, "L2", matched_dt, None, "filename substring match")`。第一个命中即返回（保持现有"先到先得"语义）。
- L3：若 L2 未命中，构建 `all_doc_types = sorted({dt for t in templates for dt in t.doc_types if dt})` 并调用 `ai_chat(prompt)`；解析响应：
  - 两行：类型 + 置信度；置信度 ≥ 阈值且租户下有该类型模板 → 返回 `SelectionResult(t, "L3", matched_type, confidence, "AI confidence match")`。
  - 两行：置信度 < 阈值 → 返回 `(None, "L3", matched_type, confidence, "AI confidence below threshold")`。
  - 两行：置信度 ≥ 阈值但租户下无该类型模板 → 返回 `(None, "none", matched_type, confidence, "AI matched type not in tenant templates")`。
  - 一行：类型 + 默认 0.5 置信度；按相同阈值判定。
  - 零行 / 解析失败 / LLM 异常：返回 `(None, "none", "", None, "<error reason>")`。
- 三层都未命中：返回 `(None, "none", "", None, "no template matched")`。

`tasks.py` 改造点：

- 在 L1 命中时增加 `logger.info("template.select layer=L1 doc_type=%r → template=%s id=%s", doc_type, t.name, t.id)`。
- 已有 L2 / L3 日志统一加 `layer=` 字段前缀。
- 无命中时输出 `logger.warning("template.select layer=none reason=%r doc_type=%r filename=%r", reason, doc_type, filename)`。

## 文件计划

新增：

- `packages/server-python/app/contexts/document/application/template_selector.py`（AC-1, AC-2, AC-3, AC-4, AC-5, AC-6）
- `packages/server-python/tests/contexts/document/test_extract_template_selection.py`（AC-7, AC-8）

修改：

- `packages/server-python/app/contexts/document/application/tasks.py:extract_template` 内 3 层选择片段（约 80 行）替换为对 `select_template` 的调用 + 统一日志；其余段落保持
- `docs/01-product-planning/02-milestones/01-validation-phase.md`（AC-9）
- `docs/01-product-planning/04-backlog.md`（AC-9）
- `docs/03-engineering-governance/current-work.md`（AC-9 收尾后）

业务代码改动范围：约 1 个文件 + 新建 1 个文件 + 1 个测试文件；prompt 构造、JSON 解析、落盘、Celery 链不动。

## 风险与边界

- 现有 `tasks.py` 中 L1 → L2 → L3 顺序与新 `select_template` 契约必须保持等价；任何优先级反转都属于行为变化，需要在 plan / commit 中显式声明"已行为变化声明检查"。
- L3 LLM 响应解析依赖 `chat()` 真实输出格式（类型\n置信度），新选择器保持原有解析规则，**不引入新解析路径**。
- 业务 Celery 任务日志前缀当前是模块默认 `app.contexts.document.application.tasks`；新选择器日志建议加 `template.select` 前缀便于过滤；二者模块名不同，不影响既有 log 消费方。
- `Template` 实体构造方式与既有 `tasks.py` 调用 `TemplateRepositoryImpl` 路径不同：纯函数测试用 dataclass 显式构造；不进 DB，避免依赖 `metaedu_test`。
- 当前 `tasks.py:extract_template` 注释"匹配优先级：精确 doc_type → AI 置信度 → 通用"中"L2 文件名"未提及，新选择器实现后须在 `tasks.py` 头部或 `template_selector.py` docstring 同步注释，避免文档漂移。

## 不在范围 / 后续任务

| ID | 说明 | 归属 |
|----|------|------|
| REQ-005 | 结构化抽取嵌套结构稳定性验收 | 单独 task |
| REQ-006 | 端到端 PG + 真实 LLM 演示验收 | 单独 task |
| TD-030（已锁定） | L3 解析行为已在 REQ-008（`tests/contexts/document/test_extract_template_selection.py` 12+ 用例）覆盖：空响应 / 解析失败 0.0 落入低于阈值 / LLM 异常分支；若后续发现未文档化边角（如响应为空但 confidence 解析成功），按 `docs/03-engineering-governance/technical-debt.md` 入账并分配新 `TD-xxx` 编号 | 已由 REQ-008 覆盖；触发现入账 |
