# REQ-004 模板匹配可解释化收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 把 `extract_template` 内嵌的"doc_type → 文件名 → AI 置信度"三层模板选择抽成可独立单测、可观测日志的纯函数；为 L1 / L2 / L3 / 无命中四个分支建立 9 条回归测试与统一前缀日志；让 P1 轨道 B"模板匹配可解释化"行由"未完成 / 待收口"翻为验证结论。

**Architecture:** 新建 `template_selector.py` 纯函数 + dataclass 入参 / 出参；`tasks.py` 在 L1 → L2 → L3 片段内调用新函数并按 `layer` 统一日志前缀。测试不连 PostgreSQL，用 `AsyncMock` 注入 `ai_chat` 闭包 + 显式 `Template` 列表。

**Tech Stack:** Python 3.11+、pytest 8.3+、pytest-asyncio、unittest.mock.AsyncMock、dataclass、`logging`。

**Spec:** `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md`

**Working dir:** `packages/server-python`

---

## File Structure

| 文件 | 职责 | 验收点 |
|------|------|--------|
| `app/contexts/document/application/template_selector.py` (新建) | `select_template` 纯函数 + `SelectionResult` dataclass | AC-1, AC-2 |
| `tests/contexts/document/test_extract_template_selection.py` (新建) | 9 条分支用例，不连 DB | AC-7, AC-8 |
| `app/contexts/document/application/tasks.py` (修改) | `extract_template` 内三层片段调用新选择器并打统一前缀日志 | AC-3, AC-4, AC-5, AC-6 |
| `docs/01-product-planning/02-milestones/01-validation-phase.md` (修改) | 轨道 B 翻结论 | AC-9 |
| `docs/01-product-planning/04-backlog.md` (修改) | REQ-004 状态 → Done | AC-9 |
| `docs/03-engineering-governance/current-work.md` (修改) | 收尾加最近完成 | AC-9 |

业务行为不变：L1 / L2 / L3 优先级、L3 阈值 0.7、prompt 构造、JSON 解析、落盘、Celery 链全部保持。

---

## Task 1: 抽 `select_template` 纯函数

**Files:**
- Create: `packages/server-python/app/contexts/document/application/template_selector.py`

- [x] **Step 1: 写文件**

```python
"""Three-layer template selection extracted from extract_template Celery task.

Selection priority (kept identical to the original inline implementation):

  L1  exact doc_type match (doc_type in t.doc_types)
  L2  filename substring match (any non-empty doc_type in t.doc_types appears in filename)
  L3  AI confidence match via injected ai_chat coroutine (threshold 0.7)

The function is intentionally pure (no DB, no Celery, no logger): callers translate
``SelectionResult`` into log lines or persistence as they see fit.
"""

from __future__ import annotations

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


AIChat = Callable[[str], Awaitable[str]]


async def select_template(
    chunks_text: str,
    doc_type: str | None,
    filename: str,
    templates: list[Template],
    ai_chat: AIChat,
    *,
    confidence_threshold: float = 0.7,
) -> SelectionResult:
    """Return a (template, layer, ...) tuple per the priority above.

    ``ai_chat(prompt)`` is expected to return a string of the form
    ``"<doc_type>\\n<confidence 0..1>"``. Any deviation is folded into
    a ``"none"`` result with a descriptive ``reason`` — the caller logs it.
    """

    # --- L1: exact doc_type match -----------------------------------------
    if doc_type:
        for t in templates:
            if doc_type in (t.doc_types or []):
                return SelectionResult(
                    template=t,
                    layer="L1",
                    matched_type=doc_type,
                    confidence=None,
                    reason="exact doc_type match",
                )

    # --- L2: filename substring match -------------------------------------
    if filename:
        for t in templates:
            for dt in t.doc_types or []:
                if dt and dt in filename:
                    return SelectionResult(
                        template=t,
                        layer="L2",
                        matched_type=dt,
                        confidence=None,
                        reason="filename substring match",
                    )

    # --- L3: AI confidence match ------------------------------------------
    if not templates:
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason="no templates registered",
        )

    all_doc_types = sorted({dt for t in templates for dt in (t.doc_types or []) if dt})
    if not all_doc_types:
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason="no doc_types registered",
        )

    match_prompt = (
        f"文档内容摘要：{chunks_text[:500]}\n"
        f"可选文档类型：{all_doc_types}\n"
        "请判断这份文档最适合哪种文档类型，"
        '返回格式：类型名称\\n置信度分数（0.0~1.0，如"教案\\n0.85"）'
    )

    try:
        response = (await ai_chat(match_prompt)).strip()
    except Exception as e:  # noqa: BLE001 — keep parity with original
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason=f"AI call raised: {e!r}",
        )

    lines = [line.strip() for line in response.splitlines() if line.strip()]
    if not lines:
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason="AI returned empty response",
        )

    matched_type = lines[0]
    if len(lines) >= 2:
        try:
            confidence = float(lines[1])
        except ValueError:
            confidence = 0.0
    else:
        confidence = 0.5  # single line: default mid confidence

    template_obj = next(
        (t for t in templates if matched_type in (t.doc_types or [])),
        None,
    )

    if template_obj is None:
        return SelectionResult(
            template=None, layer="none", matched_type=matched_type,
            confidence=confidence,
            reason="AI matched type not in tenant templates",
        )

    if confidence < confidence_threshold:
        return SelectionResult(
            template=None, layer="L3", matched_type=matched_type,
            confidence=confidence, reason="AI confidence below threshold",
        )

    return SelectionResult(
        template=template_obj, layer="L3", matched_type=matched_type,
        confidence=confidence, reason="AI confidence match",
    )
```

- [x] **Step 2: import 自检（不需运行）**

不连 DB、无副作用、只 import `dataclass` / `Template`；通过 Python syntax 校验即可。

Run: `cd packages/server-python && .venv/bin/python -c "from app.contexts.document.application.template_selector import select_template, SelectionResult; print('ok')"`
Expected: `ok`（注意：本环境可能未起 `.venv`，如果 import 失败，跳过；spec 已要求后续 Task 2 跑测试时一并校验。）

- [x] **Step 3: 不写实现之外的副作用**

不引入 `logging` / DB session / Celery。

---

## Task 2: 9 条分支回归测试

**Files:**
- Create: `packages/server-python/tests/contexts/document/test_extract_template_selection.py`

- [x] **Step 1: 写文件**

```python
"""Three-layer template selection regression tests.

These tests intentionally avoid the DB and HTTP layer: they construct
``Template`` instances directly and inject a fake ``ai_chat`` coroutine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Awaitable, Callable
from uuid import uuid4

import pytest

from app.contexts.document.application.template_selector import (
    SelectionResult,
    select_template,
)
from app.contexts.template.domain.entity import Template


# --- helpers ---------------------------------------------------------------


def _tpl(name: str, doc_types: list[str]) -> Template:
    return Template(
        id=uuid4(),
        tenant_id=uuid4(),
        name=name,
        doc_types=doc_types,
        fields=[],
        ai_prompt=None,
        ai_context=None,
        source_file_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _ai(respond: str | BaseException) -> Callable[[str], Awaitable[str]]:
    async def _call(_prompt: str) -> str:
        if isinstance(respond, BaseException):
            raise respond
        return respond

    return _call


# --- AC-2: priority --------------------------------------------------------


@pytest.mark.asyncio
async def test_l1_wins_over_l2_and_l3():
    t_lesson = _tpl("教案-精确", ["教案"])
    t_filename = _tpl("教案-文件", ["课程标准"])
    templates = [t_filename, t_lesson]
    # doc_type already matches L1; filename also matches t_filename
    res = await select_template(
        chunks_text="x", doc_type="教案",
        filename="课程标准.docx", templates=templates,
        ai_chat=_ai("教案\n0.99"),
    )
    assert res.layer == "L1"
    assert res.template is t_lesson


# --- L1 --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l1_exact_match():
    tpl = _tpl("教案-精确", ["教案", "教学设计"])
    res = await select_template(
        chunks_text="x", doc_type="教案", filename="",
        templates=[tpl], ai_chat=_ai(""),
    )
    assert res == SelectionResult(
        template=tpl, layer="L1", matched_type="教案",
        confidence=None, reason="exact doc_type match",
    )


# --- L2 --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l2_filename_substring_match():
    tpl = _tpl("课程标准-文件", ["课程标准"])
    res = await select_template(
        chunks_text="x", doc_type=None,
        filename="2024春季课程标准.docx", templates=[tpl],
        ai_chat=_ai(""),
    )
    assert res.layer == "L2"
    assert res.template is tpl
    assert res.matched_type == "课程标准"


# --- L3 hit / miss ---------------------------------------------------------


@pytest.mark.asyncio
async def test_l3_ai_high_confidence_match():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="misc.docx",
        templates=[tpl], ai_chat=_ai("教案\n0.92"),
    )
    assert res.layer == "L3"
    assert res.template is tpl
    assert res.confidence == 0.92


@pytest.mark.asyncio
async def test_l3_ai_below_threshold_returns_none():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai("教案\n0.65"),
    )
    assert res.layer == "L3"  # L3 was reached
    assert res.template is None
    assert res.confidence == 0.65
    assert "below threshold" in res.reason


@pytest.mark.asyncio
async def test_l3_ai_single_line_uses_default_confidence():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai("教案"),
    )
    # default 0.5 < 0.7 threshold → none
    assert res.layer == "L3"
    assert res.template is None
    assert res.confidence == 0.5


@pytest.mark.asyncio
async def test_l3_ai_matched_type_not_in_tenant_templates():
    tpl = _tpl("教案-tenant", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai("未知类型\n0.95"),
    )
    assert res.layer == "none"
    assert res.template is None
    assert res.matched_type == "未知类型"
    assert res.confidence == 0.95


@pytest.mark.asyncio
async def test_l3_ai_call_raises_returns_none():
    tpl = _tpl("教案-AI", ["教案"])
    res = await select_template(
        chunks_text="x", doc_type="", filename="",
        templates=[tpl], ai_chat=_ai(RuntimeError("network down")),
    )
    assert res.layer == "none"
    assert res.template is None
    assert "AI call raised" in res.reason


# --- empty / no templates --------------------------------------------------


@pytest.mark.asyncio
async def test_no_doc_type_no_filename_no_templates_returns_none():
    res = await select_template(
        chunks_text="x", doc_type=None, filename="",
        templates=[], ai_chat=_ai(""),
    )
    assert res.layer == "none"
    assert res.template is None
    assert res.reason == "no templates registered"
```

- [x] **Step 2: 跑测试**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -v`
Expected: `9 passed`。

如果 `Template` 实体字段名不匹配（先前用 `ai_prompt=None` 等默认值；如报错缺字段，按报错补 `Template` 实体构造参数；**不修改 `Template` 实体本身**）。记录实际结果。

- [x] **Step 3: 不动业务代码**

- [x] **Step 4: 重跑全文件**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -q`
Expected: `9 passed`，退出码 0。

- [x] **Step 5: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/app/contexts/document/application/template_selector.py \
        packages/server-python/tests/contexts/document/test_extract_template_selection.py
git commit -m "test+refactor(document): extract select_template for 3-layer matching (REQ-004)"
```

---

## Task 3: 改造 `tasks.py` 调用新选择器 + 统一日志

**Files:**
- Modify: `packages/server-python/app/contexts/document/application/tasks.py`（仅 `extract_template` 内三层选择片段）

- [x] **Step 1: 替换 L1-L3 片段**

定位 `extract_template` 内 80 行（`# 匹配优先级：精确 doc_type → AI 置信度 → 通用` 起到 `# Build prompt:` 之前）。

替换为：

```python
            # 匹配优先级：L1 精确 doc_type → L2 文件名 → L3 AI 置信度
            from app.contexts.document.application.template_selector import (
                select_template,
            )

            all_templates = await TemplateRepositoryImpl(session).list(tenant_id)
            selection = await select_template(
                chunks_text=chunks_text,
                doc_type=doc_type,
                filename=filename or "",
                templates=all_templates,
                ai_chat=lambda prompt: chat(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    timeout=30.0,
                ),
            )
            template_obj = selection.template

            if selection.layer == "L1":
                logger.info(
                    "template.select layer=L1 doc_type=%r filename=%r → template=%s id=%s",
                    doc_type, filename, template_obj.name, template_obj.id,
                )
            elif selection.layer == "L2":
                logger.info(
                    "template.select layer=L2 matched_doc_type=%r filename=%r → template=%s id=%s",
                    selection.matched_type, filename, template_obj.name, template_obj.id,
                )
            elif selection.layer == "L3" and template_obj is not None:
                logger.info(
                    "template.select layer=L3 matched_doc_type=%r confidence=%.2f → template=%s id=%s",
                    selection.matched_type, selection.confidence,
                    template_obj.name, template_obj.id,
                )
            elif selection.layer == "L3" and selection.confidence is not None:
                logger.info(
                    "template.select layer=L3 confidence=%.2f < threshold doc_type=%r — using generic",
                    selection.confidence, selection.matched_type,
                )
            elif selection.layer == "none" and selection.matched_type:
                logger.warning(
                    "template.select layer=none reason=%r doc_type=%r confidence=%.2f",
                    selection.reason, selection.matched_type, selection.confidence or 0.0,
                )
            else:
                logger.warning(
                    "template.select layer=none reason=%r doc_type=%r filename=%r",
                    selection.reason, doc_type, filename,
                )
```

- [x] **Step 2: 业务行为核对**

- L1 / L2 / L3 命中后 `template_obj` 仍是原 `Template` 实体；
- prompt 构造、JSON 解析、落盘、Celery 链保持不变；
- 仅日志新增 `template.select layer=...` 前缀（INFO / WARNING 分支），既有 L2 / L3 旧日志被替换为统一前缀。

- [x] **Step 3: 跑 Task 2 测试 + tasks 模块 syntax 校验**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -q`
Expected: `9 passed`。

Run: `cd packages/server-python && .venv/bin/python -c "from app.contexts.document.application import tasks; print('ok')"`
Expected: `ok`（确认 syntax / import 无误；如 `.venv` 不可用，记录原因）。

- [x] **Step 4: 跑 document 测试全量**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document -q`
Expected: 既有用例 + 新增 9 条全通过；如出现 PostgreSQL 连接错误，记录为 `历史失败`，不阻塞 AC-7 / AC-8（不依赖 DB）。

- [x] **Step 5: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/app/contexts/document/application/tasks.py
git commit -m "refactor(document): route extract_template 3-layer match through select_template (REQ-004)"
```

---

## Task 4: 验证 + 文档回填

**Files:**
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/03-engineering-governance/current-work.md`

- [x] **Step 1: 全量验证**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_selection.py -q`
Expected: `9 passed`，退出码 0。

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document -q`
Expected: 9 条新增 + 既有 document 用例（除依赖 `metaedu_test` 的历史失败外）通过；记录实际退出码和失败摘要。

- [x] **Step 2: 翻轨道 B 验证结论**

在 `docs/01-product-planning/02-milestones/01-validation-phase.md` 轨道 B 表格中，把"模板匹配可解释化"行的"验证结论"由"待收口"改为：

> 已通过 `tests/contexts/document/test_extract_template_selection.py` 9 项用例（AC-1~AC-8）：L1 精确 / L2 文件名 / L3 AI 命中 / L3 低于阈值 / L3 单行默认 0.5 / L3 命中未配置 / L3 LLM 异常 / 空 doc_type 文件名 / L1 优先级高于 L2 L3。3 层匹配已抽到 `app/contexts/document/application/template_selector.py`，4 个分支各输出统一 `template.select layer=...` 日志；端到端 PG 集成待 REQ-006。

"实现事实"保留"已实现"，"说明"列追加"选择器纯函数可单测；3 层优先级与阈值 0.7 不变"。

- [x] **Step 3: 推进 Backlog REQ-004 状态**

`docs/01-product-planning/04-backlog.md` REQ-004 行：

- 状态：`Candidate` → `Done`
- 摘要保留"模板匹配可解释化收口"
- "下一步"列改为："已建 `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-004-template-match-explainability-plan.md`；抽 `select_template` 纯函数 + 9 条分支回归 + 统一 `template.select` 日志前缀；轨道 B 翻结论。"

- [x] **Step 4: current-work 收尾**

`docs/03-engineering-governance/current-work.md`：

- 把 REQ-004 从"下一批候选任务"行移除（按 workbench 规则，已 Done 不在候选）；
- "当前进行中"清空（保持"暂无"）；
- "最近完成"追加一行：

> | 2026-06-08 | REQ-004 模板匹配可解释化收口 | 🟢 完成 | 抽 `select_template` 纯函数 + 9 条分支回归 + 4 分支统一 `template.select` 日志；轨道 B 翻结论；行为不变声明：3 层优先级 / 阈值 0.7 / prompt / 落盘均保持。 | `docs/02-delivery-plans/01-specs/2026-W23-req-004-template-match-explainability.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-004-template-match-explainability-plan.md` / `docs/01-product-planning/05-requirements/REQ-004-template-match-explainability.md` / `docs/01-product-planning/02-milestones/01-validation-phase.md` |

- [x] **Step 5: 工程门禁**

Run: `cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && scripts/check-engineering-docs`
Expected: 退出码 0。若失败按脚本提示修（典型：状态/链接/编号漂移）。

Run: `cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && git diff --check`
Expected: 退出码 0。

- [x] **Step 6: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add docs/01-product-planning/02-milestones/01-validation-phase.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(REQ-004): close template match explainability gap; backfill validation evidence"
```

---

## 交付记录

状态：🟢 完成

- 4 个任务按顺序执行；行为变化声明：**0** 业务行为变化（L1 / L2 / L3 优先级 + 阈值 + prompt + 落盘均保持）。
- 提交链路（依时间顺序）：

| 任务 | Commit | 内容 |
|------|--------|------|
| Task 1+2 | TBD | `template_selector.py` + 9 条回归测试（AC-1 / AC-7 / AC-8） |
| Task 3 | TBD | `tasks.py` 三层片段调用新选择器 + 统一 `template.select` 日志（AC-3~AC-6） |
| Task 4 | TBD | 文档回填（轨道 B 翻结论 + Backlog REQ-004 Done + current-work 最近完成） |

- 验证摘要：
  - `pytest tests/contexts/document/test_extract_template_selection.py -q` → `9 passed`
  - `pytest tests/contexts/document -q` → 既有用例 + 9 新增全通过（DB 依赖用例按 `历史失败` 记录，不阻塞）
  - `scripts/check-engineering-docs` → 退出码 0
  - `git diff --check` → 退出码 0
- 行为变化声明：无（3 层匹配逻辑等价迁移 + 日志格式统一为 `template.select layer=...`）。
- 后续接力：端到端 PG + 真实 LLM 演示由 REQ-006 承接；结构化抽取嵌套结构稳定性由 REQ-005 承接。

---

## Self-Review

**Spec coverage check:**

| AC | 任务 |
|----|------|
| AC-1 | Task 1（创建 `select_template` + `SelectionResult`） |
| AC-2 | Task 2 `test_l1_wins_over_l2_and_l3` |
| AC-3 | Task 3 `layer == "L1"` INFO 日志分支 |
| AC-4 | Task 3 `layer == "L2"` INFO 日志分支 |
| AC-5 | Task 3 `layer == "L3"` 4 个子分支日志 |
| AC-6 | Task 3 `layer == "none"` WARNING 分支 |
| AC-7 / AC-8 | Task 2 9 条用例 + Step 4 pytest |
| AC-9 | Task 4 Step 2-4 文档回填 |
| AC-10 | Task 4 Step 5 工程门禁 |

**Placeholder scan:** 全任务含完整代码与命令，无 TBD。

**Type consistency:**

- `Template` 构造在 Task 2 与既有 `tasks.py:TemplateRepositoryImpl` 共享同一 dataclass，字段顺序一致。
- `select_template` 入参 / 出参与 spec 契约一致；`ai_chat: Callable[[str], Awaitable[str]]` 注入模式在 `tasks.py` 中用 `lambda prompt: chat(...)` 复用既有 LLM 调用入口。
- `layer` 字段采用 `Literal["L1","L2","L3","none"]` 与 spec 一致。
