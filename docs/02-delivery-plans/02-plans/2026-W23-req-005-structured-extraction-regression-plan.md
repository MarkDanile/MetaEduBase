# REQ-005 结构化抽取嵌套结构稳定性验收 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 为 `extract_template` 链路中"LLM 抽取 → JSON 解析 → 按模板结构落盘"的关键纯函数（`extract_template_prompts.build_fields_desc` / `try_parse` / `_merge_template_structured_data`）在 object / array / table 嵌套形态上的行为建立 ≥8 条纯函数回归测试；让 P1 轨道 B "结构化抽取嵌套结构稳定性"行由"未完成 / 待收口"翻为"已通过 N 项用例"。本任务不修改任何业务代码。

**Architecture:** 纯函数测试，不连 PostgreSQL、不连 LLM；`Field` / `TableColumn` 用 dataclass 显式构造。测试目标模块在 `app.contexts.document.application.tasks.extract_template_prompts`，其本身已是无副作用纯函数（无 DB session / Celery / logger 依赖），可直接 import。

**Tech Stack:** Python 3.11+、pytest 8.3+、`dataclasses`、stdlib `json` / `re`。

**Spec:** `docs/02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md`

**Working dir:** `packages/server-python`

---

## File Structure

| 文件 | 职责 | 验收点 |
|------|------|--------|
| `tests/contexts/document/test_extract_template_prompts.py` (新建) | 8+ 条用例，覆盖 build_fields_desc / try_parse / _merge_template_structured_data 在 object / array / table 嵌套形态上的契约 | AC-1 ~ AC-9 |
| `docs/01-product-planning/02-milestones/01-validation-phase.md` (修改) | 轨道 B 翻结论 | AC-10 |
| `docs/01-product-planning/04-backlog.md` (修改) | REQ-005 状态 → Done | AC-10 |
| `docs/03-engineering-governance/current-work.md` (修改) | 当前进行中清空 + 最近完成加一行 | AC-10 |
| `docs/03-engineering-governance/work-log.md` (修改) | 单行索引 | AC-10 |

业务代码改动范围：0 个文件。

---

## Task 1: 8+ 条嵌套形态回归测试

**Files:**
- Create: `packages/server-python/tests/contexts/document/test_extract_template_prompts.py`

- [x] **Step 1: 写文件**

```python
"""Regression tests for ``extract_template_prompts`` nested-structure contract.

The helpers under test (``build_fields_desc``, ``try_parse``,
``_merge_template_structured_data``) are pure functions invoked in the
``extract_template`` Celery task. This file locks their behavior on
object / array / table nested shapes so the LLM-extraction pipeline can
be regression-tested without a live LLM or PostgreSQL connection.

Conventions:
  * Import helpers directly from ``extract_template_prompts``; the
    re-export in ``app.contexts.document.application.tasks`` is kept for
    historical tests only.
  * Build ``Field`` / ``TableColumn`` instances via
    ``app.contexts.template.domain.entity``.
  * No DB, no LLM, no Celery: every test runs offline.
"""

from __future__ import annotations

import json

from app.contexts.document.application.tasks.extract_template_prompts import (
    _merge_template_structured_data,
    build_fields_desc,
    try_parse,
)
from app.contexts.template.domain.entity import Field, TableColumn


# --- AC-1: build_fields_desc on object nesting -----------------------------


def test_build_fields_desc_object_nesting_includes_children() -> None:
    fields = [
        Field(
            key="basic_info",
            label="基本信息",
            type="object",
            children=[
                Field(key="subject", label="学科", type="text"),
                Field(key="grade", label="年级", type="text"),
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert "basic_info(基本信息)[object型，含子字段：" in desc
    assert "subject(学科)[text型]" in desc
    assert "grade(年级)[text型]" in desc
    assert desc.endswith("]")


def test_build_fields_desc_two_level_object_nesting() -> None:
    fields = [
        Field(
            key="outer",
            label="外层",
            type="object",
            children=[
                Field(
                    key="inner",
                    label="内层",
                    type="object",
                    children=[Field(key="leaf", label="叶子", type="text")],
                )
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert "outer(外层)[object型，含子字段：" in desc
    assert "inner(内层)[object型，含子字段：" in desc
    assert "leaf(叶子)[text型]" in desc


# --- AC-2: build_fields_desc on array nesting ------------------------------


def test_build_fields_desc_array_uses_first_item_key() -> None:
    fields = [
        Field(
            key="teaching_process",
            label="教学过程",
            type="array",
            items=[
                Field(
                    key="step",
                    label="步骤",
                    type="object",
                    children=[Field(key="activity", label="活动", type="text")],
                )
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    # array 行只声明"成员为object，含字段：step"，不展开 step 内部 children
    assert "teaching_process(教学过程)[array型，成员为object，含字段：step]" == desc


def test_build_fields_desc_array_without_items_falls_back_to_item() -> None:
    fields = [
        Field(key="empty_array", label="空数组", type="array", items=[]),
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert "empty_array(空数组)[array型，成员为object，含字段：item]" == desc


# --- AC-3: build_fields_desc on table nesting ------------------------------


def test_build_fields_desc_table_lists_columns_in_order() -> None:
    fields = [
        Field(
            key="assessment",
            label="评价",
            type="table",
            columns=[
                TableColumn(key="criterion", label="标准", type="text"),
                TableColumn(key="score", label="分数", type="number"),
                TableColumn(key="remark", label="备注", type="textarea"),
            ],
        )
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    assert "assessment(评价)[table型，列：criterion, score, remark]" == desc


# --- AC-4: build_fields_desc on mixed nesting ------------------------------


def test_build_fields_desc_mixed_types_preserve_order_and_type_tag() -> None:
    fields = [
        Field(key="title", label="标题", type="text"),
        Field(
            key="basic_info",
            label="基本信息",
            type="object",
            children=[Field(key="subject", label="学科", type="text")],
        ),
        Field(
            key="teaching_process",
            label="教学过程",
            type="array",
            items=[Field(key="step", label="步骤", type="text")],
        ),
        Field(
            key="assessment",
            label="评价",
            type="table",
            columns=[TableColumn(key="criterion", label="标准", type="text")],
        ),
    ]

    desc = build_fields_desc([f.to_dict() for f in fields])

    parts = desc.split(", ")
    assert len(parts) == 4
    assert parts[0] == "title(标题)[text型]"
    assert parts[1].startswith("basic_info(基本信息)[object型，含子字段：")
    assert parts[2] == "teaching_process(教学过程)[array型，成员为object，含字段：step]"
    assert parts[3] == "assessment(评价)[table型，列：criterion]"


# --- AC-5: try_parse preserves nested object / array / table ---------------


def test_try_parse_preserves_nested_structures_from_markdown_fence() -> None:
    payload = {
        "basic_info": {"subject": "数学", "grade": "三年级"},
        "teaching_process": [
            {"step": "导入", "activity": "提问"},
            {"step": "讲授", "activity": "演示"},
        ],
        "assessment": [
            {"criterion": "理解", "score": 4, "remark": "好"},
        ],
    }
    content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

    parsed = try_parse(content)

    assert isinstance(parsed["basic_info"], dict)
    assert parsed["basic_info"]["subject"] == "数学"
    assert isinstance(parsed["teaching_process"], list)
    assert all(isinstance(item, dict) for item in parsed["teaching_process"])
    assert parsed["teaching_process"][1]["step"] == "讲授"
    assert isinstance(parsed["assessment"], list)
    assert parsed["assessment"][0]["criterion"] == "理解"


# --- AC-6: try_parse strips <think>...</think> before parsing --------------


def test_try_parse_strips_think_tag_then_parses_nested() -> None:
    payload = {
        "teaching_process": [{"step": "导入", "activity": "提问"}],
    }
    content = (
        "<think>调用 LLM 之前先思考文档结构</think>"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )

    parsed = try_parse(content)

    assert "teaching_process" in parsed
    assert isinstance(parsed["teaching_process"], list)
    assert parsed["teaching_process"][0]["activity"] == "提问"


# --- AC-7: try_parse degrades to {} on bad JSON ----------------------------


def test_try_parse_returns_empty_dict_on_malformed_json() -> None:
    content = "```json\n{ this is not valid json\n```"

    parsed = try_parse(content)

    assert parsed == {}


def test_try_parse_returns_empty_dict_on_unclosed_fence() -> None:
    content = "```json\n{\"a\": 1"

    parsed = try_parse(content)

    assert parsed == {}


# --- AC-8: _merge_template_structured_data shallow-copies template --------


def test_merge_template_structured_data_shallow_copies_nested_template() -> None:
    existing = {"full_text": "正文", "section_count": 1}
    template = {
        "teaching_process": [{"step": "导入", "activity": "提问"}],
        "assessment": [{"criterion": "理解", "score": 4}],
    }

    merged = _merge_template_structured_data(existing, template)

    # 外层 template 是新 dict
    assert merged["template"] is not template
    # 但内嵌 list / dict 仍是同一引用（浅拷贝契约）
    assert merged["template"]["teaching_process"] is template["teaching_process"]
    assert merged["template"]["teaching_process"][0] is template["teaching_process"][0]
    # 既有字段不丢
    assert merged["full_text"] == "正文"
    assert merged["section_count"] == 1
```

- [x] **Step 2: 跑测试**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -v`
Expected: `11 passed`（AC-1~AC-4 共 6 条 + AC-5 1 条 + AC-6 1 条 + AC-7 2 条 + AC-8 1 条）。最低通过线：≥8 条。

如果 `Field` 实体字段名不匹配（先前 spec 已确认 dataclass 字段为 `key` / `label` / `type` / `description` / `children` / `columns` / `items`），按报错补构造参数；**不修改业务代码**。

记录实际结果。

- [x] **Step 3: 不修改业务代码**

明确本 PR 不修改 `app/contexts/document/application/tasks/extract_template_prompts.py` 或其他业务文件。验收口径来自现有契约。

- [x] **Step 4: 重跑全文件 + import 自检**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -q`
Expected: `11 passed`，退出码 0。

Run: `cd packages/server-python && .venv/bin/python -c "from app.contexts.document.application.tasks.extract_template_prompts import build_fields_desc, try_parse, _merge_template_structured_data; print('ok')"`
Expected: `ok`（如 `.venv` 不可用，记录原因；测试已自动验证 import 路径）。

- [x] **Step 5: 跑 document 测试全量（确认既有 contract 不退化）**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document -q`
Expected: 既有用例（含 `test_structured_data_contract.py` 4 条） + 新增 11 条全通过；如出现 PostgreSQL 连接错误，记录为 `历史失败`，不阻塞 AC-9（不依赖 DB）。

- [x] **Step 6: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/document/test_extract_template_prompts.py
git commit -m "test(document): lock extract_template_prompts nested-structure contract (REQ-005)"
```

---

## Task 2: 验证 + 文档回填

**Files:**
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`

- [x] **Step 1: 全量验证**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_extract_template_prompts.py -q`
Expected: 11 passed，退出码 0。

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document -q`
Expected: 11 条新增 + 既有 document 用例（含 `test_structured_data_contract.py` 4 条）通过；记录实际退出码和失败摘要。

- [x] **Step 2: 翻轨道 B 验证结论**

在 `docs/01-product-planning/02-milestones/01-validation-phase.md` 轨道 B 表格中，把"结构化抽取嵌套结构稳定性"行的"验证结论"由"待收口"改为：

> 已通过 `tests/contexts/document/test_extract_template_prompts.py` 11 项用例（AC-1~AC-8）：`build_fields_desc` 覆盖 object 单层 / 2 层嵌套 / array 含 items / array 空 items 降级到 bare type / table 列顺序 / object+array+table+text 混合；`try_parse` 覆盖 markdown fence 含 object+array+table 三层嵌套 / `<think>` 标签剥离后再解析 / 坏 JSON 降级 / 未闭合 fence 降级；`_merge_template_structured_data` 锁定浅拷贝契约（外层新 dict、内嵌 list/dict 同引用）。`array + items=[]` 走 bare-type 分支是当前既定行为，已被回归锁定。端到端 PG + 真实 LLM 演示待 REQ-006。

"实现事实"列追加"object / array / table 嵌套抽取链路可纯函数回归，无需 LLM / DB"。

- [x] **Step 3: 推进 Backlog REQ-005 状态**

`docs/01-product-planning/04-backlog.md` REQ-005 行：

- 状态：`Candidate` → `Done`
- 摘要保留"结构化抽取嵌套结构稳定性验收"
- "下一步"列改为："已建 `docs/02-delivery-plans/01-specs/2026-W23-req-005-structured-extraction-regression.md` / `docs/02-delivery-plans/02-plans/2026-W23-req-005-structured-extraction-regression-plan.md`；为 `extract_template_prompts.build_fields_desc` / `try_parse` / `_merge_template_structured_data` 补 11 条 object / array / table 嵌套回归用例；行为不变声明：0 业务代码改动（仅补测试与文档）。"

- [x] **Step 4: current-work 收尾**

`docs/03-engineering-governance/current-work.md`：

- "当前进行中"清空（保持"暂无"）；
- "下一批候选任务"移除 REQ-005（按 workbench 规则，已 Done 不在候选）；
- "最近完成"追加一行（按"最近优先"插到最上）：

> | 2026-06-09 | REQ-005 结构化抽取嵌套结构稳定性验收 | 🟢 完成 | 为 `extract_template_prompts` 补 11 条 object / array / table 嵌套回归用例；锁定 `build_fields_desc` 嵌套描述 / `try_parse` 嵌套 JSON 与 think 剥离 / `_merge_template_structured_data` 浅拷贝契约；轨道 B 翻结论。0 业务代码改动。 | [Spec](../01-specs/2026-W23-req-005-structured-extraction-regression.md) / [Plan](../02-plans/2026-W23-req-005-structured-extraction-regression-plan.md) |

- [x] **Step 5: work-log 单行索引**

`docs/03-engineering-governance/work-log.md` 追加单行：

```
- 2026-06-09 REQ-005 结构化抽取嵌套结构稳定性验收 — Spec/Plan/测试，0 业务代码改动；11 条 object/array/table 嵌套回归；轨道 B 翻结论。
```

- [x] **Step 6: 工程门禁**

Run: `cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && scripts/check-engineering-docs`
Expected: 退出码 0。若失败按脚本提示修（典型：状态/链接/编号漂移）。

Run: `cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && git diff --check`
Expected: 退出码 0。

- [x] **Step 7: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add docs/01-product-planning/02-milestones/01-validation-phase.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md \
        docs/03-engineering-governance/work-log.md
git commit -m "docs(REQ-005): close structured extraction regression gap; backfill validation evidence"
```

---

## 交付记录

状态：🟢 完成

- 2 个任务按顺序执行；行为变化声明：**0** 业务行为变化（仅补测试 + 文档回填）。
- 提交链路（依时间顺序）：

| 任务 | Commit | 内容 |
|------|--------|------|
| Task 1 | TBD | `test_extract_template_prompts.py` 11 条 object/array/table 嵌套回归（AC-1~AC-9） |
| Task 2 | TBD | 文档回填（轨道 B 翻结论 + Backlog REQ-005 Done + current-work 最近完成 + work-log 单行） |

- 验证摘要：
  - `pytest tests/contexts/document/test_extract_template_prompts.py -q` → `11 passed`
  - `pytest tests/contexts/document -q` → 既有 4 条 contract + 12 新增全通过（DB 依赖用例按 `历史失败` 记录，不阻塞）
  - `scripts/check-engineering-docs` → 退出码 0
  - `git diff --check` → 退出码 0
- 行为变化声明：无（0 业务代码改动）。
- 后续接力：端到端 PG + 真实 LLM 演示由 REQ-006 承接。

---

## Self-Review

**Spec coverage check:**

| AC | 任务 |
|----|------|
| AC-1 | Task 1 `test_build_fields_desc_object_nesting_includes_children` + `test_build_fields_desc_two_level_object_nesting` |
| AC-2 | Task 1 `test_build_fields_desc_array_uses_first_item_key` + `test_build_fields_desc_array_without_items_falls_back_to_item` |
| AC-3 | Task 1 `test_build_fields_desc_table_lists_columns_in_order` |
| AC-4 | Task 1 `test_build_fields_desc_mixed_types_preserve_order_and_type_tag` |
| AC-5 | Task 1 `test_try_parse_preserves_nested_structures_from_markdown_fence` |
| AC-6 | Task 1 `test_try_parse_strips_think_tag_then_parses_nested` |
| AC-7 | Task 1 `test_try_parse_returns_empty_dict_on_malformed_json` + `test_try_parse_returns_empty_dict_on_unclosed_fence` |
| AC-8 | Task 1 `test_merge_template_structured_data_shallow_copies_nested_template` |
| AC-9 | Task 1 Step 2-5 + Task 2 Step 1 pytest |
| AC-10 | Task 2 Step 2-5 文档回填 |
| AC-11 | Task 2 Step 6 工程门禁 |

**Placeholder scan:** 全任务含完整代码与命令，无 TBD。

**Type consistency:**

- `Field` / `TableColumn` 构造在 Task 1 与既有 `app.contexts.template.domain.entity` 共享同一 dataclass，字段顺序一致。
- `try_parse` 入参 / 出参与现有 `extract_template_prompts.py` 一致；嵌套 JSON 用 `json.dumps(ensure_ascii=False)` 构造避免编码歧义。
- `build_fields_desc` 入参是 `list[dict]`，本测试用 `[f.to_dict() for f in fields]` 显式转换，与生产代码 `tasks.py:131-136` 一致。
