# TD-009 Structured Data Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `FileDTO.structured_data` an explicit shared contract container so frontend template extraction display is schema-narrowed and backend task writes are covered by focused tests.

**Architecture:** Add a small Zod schema/helper in `packages/shared` for the structured-data container, then consume that shared type/helper from the frontend document service and `FileDetailView`. On the backend, keep the public `FileDTO.structured_data` response model compatible (`dict | None`) but extract pure helper functions for parse/extract structured-data writes and lock them with pytest.

**Tech Stack:** TypeScript 5.8, Zod 3.24, Vue 3.5, FastAPI/Pydantic DTOs, Python 3.12+, pytest, pnpm workspaces.

---

## Scope and constraints

- Canonical spec: `docs/specs/2026-06-05-td-009-structured-data-contract.md`.
- Technical debt card: `docs/engineering/technical-debt.md#td-009`.
- Do not introduce cross-language schema generation.
- Do not change LLM prompts, task order, SQL update semantics, user-visible labels, or template field value validation.
- Do not make backend `FileDTO.structured_data` a strict Pydantic response model in this slice.
- Do not commit unless the user explicitly asks for commits. Commit commands below are checkpoints to run only when commit authorization is present.

## File structure

| File | Responsibility |
|------|----------------|
| `packages/shared/src/schemas/document.ts` | New shared Zod schema, exported type, and narrow helpers for document structured-data container. |
| `packages/shared/src/schemas/index.ts` | Re-export document schema from shared schema barrel. |
| `packages/web/src/services/document.ts` | Consume shared `FileStructuredData` type in `FileDTO`. |
| `packages/web/src/views/resource/FileDetailView.vue` | Use shared helper to narrow `structured_data.template` before display; remove direct cast. |
| `packages/server-python/app/contexts/document/application/tasks.py` | Add pure helpers for parsed structured-data construction and template merge; use them in existing SQL write paths. |
| `packages/server-python/tests/contexts/document/test_structured_data_contract.py` | New focused tests for backend structured-data helper contract. |
| `docs/specs/2026-06-05-td-009-structured-data-contract.md` | Update plan link/status after implementation plan exists. |
| `docs/engineering/current-work.md` | Keep TD-009 progress, next step, and validation results current. |
| `docs/engineering/technical-debt.md` | Keep TD-009 fact source, status, and delivery record current. |

---

### Task 1: Add shared structured-data schema

**Files:**
- Create: `packages/shared/src/schemas/document.ts`
- Modify: `packages/shared/src/schemas/index.ts`

- [ ] **Step 1: Write the failing export check**

Modify `packages/shared/src/schemas/index.ts` to export the document schema before the file exists:

```ts
export * from "./document";
export * from "./knowledge";
export * from "./resource";
export * from "./user";
```

- [ ] **Step 2: Run shared typecheck to verify it fails**

Run:

```bash
pnpm --filter @metaedu/shared typecheck
```

Expected: FAIL with a TypeScript module resolution error equivalent to:

```text
Cannot find module './document' or its corresponding type declarations.
```

- [ ] **Step 3: Add the shared schema and helpers**

Create `packages/shared/src/schemas/document.ts` with exactly this content:

```ts
import { z } from "zod";

export const JsonObjectSchema = z.record(z.string(), z.unknown());

export const FileStructuredDataSchema = z
  .object({
    full_text: z.string().optional(),
    section_count: z.number().optional(),
    template: JsonObjectSchema.optional(),
  })
  .passthrough();

export type FileStructuredData = z.infer<typeof FileStructuredDataSchema>;

export function parseFileStructuredData(value: unknown): FileStructuredData | null {
  if (value == null) return null;
  const result = FileStructuredDataSchema.safeParse(value);
  return result.success ? result.data : null;
}

export function getTemplateStructuredData(value: unknown): Record<string, unknown> | null {
  return parseFileStructuredData(value)?.template ?? null;
}
```

- [ ] **Step 4: Run shared typecheck to verify it passes**

Run:

```bash
pnpm --filter @metaedu/shared typecheck
```

Expected: PASS with exit code 0.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git diff -- packages/shared/src/schemas/document.ts packages/shared/src/schemas/index.ts
```

Expected: diff only creates `document.ts` and adds the export line.

If commit authorization is present, commit only these files:

```bash
git add packages/shared/src/schemas/document.ts packages/shared/src/schemas/index.ts
git commit -m "feat(shared): add structured data contract schema"
```

---

### Task 2: Consume shared schema in frontend document display

**Files:**
- Modify: `packages/web/src/services/document.ts`
- Modify: `packages/web/src/views/resource/FileDetailView.vue`

- [ ] **Step 1: Confirm the current unsafe cast exists**

Run:

```bash
rg -n "structured_data as Record<string, unknown>|\[\"template\"\] as Record<string, unknown>" packages/web/src/views/resource/FileDetailView.vue
```

Expected: at least one hit in `FileDetailView.vue` near the `templateData` computed helper.

- [ ] **Step 2: Update the frontend document DTO type**

In `packages/web/src/services/document.ts`, add this import after the existing `api` import:

```ts
import type { FileStructuredData } from "@metaedu/shared/schemas/document";
```

Change the `FileDTO` field from:

```ts
  structured_data: Record<string, unknown> | null;
```

to:

```ts
  structured_data: FileStructuredData | null;
```

- [ ] **Step 3: Update `FileDetailView` to narrow through the helper**

In `packages/web/src/views/resource/FileDetailView.vue`, add this import near the other imports:

```ts
import { getTemplateStructuredData } from "@metaedu/shared/schemas/document";
```

Replace the current `templateData` computed block:

```ts
const templateData = computed(() => {
  if (!file.value?.structured_data) return null;
  return (file.value.structured_data as Record<string, unknown>)["template"] as Record<string, unknown> | null ?? null;
});
```

with:

```ts
const templateData = computed(() => getTemplateStructuredData(file.value?.structured_data));
```

- [ ] **Step 4: Verify the unsafe cast is gone**

Run:

```bash
rg -n "structured_data as Record<string, unknown>|\[\"template\"\] as Record<string, unknown>" packages/web/src/views/resource/FileDetailView.vue
```

Expected: no output and exit code 1 from `rg`.

- [ ] **Step 5: Run frontend and shared typechecks**

Run:

```bash
pnpm --filter @metaedu/shared typecheck
pnpm --filter @metaedu/web typecheck
```

Expected: both commands exit 0.

- [ ] **Step 6: Checkpoint**

Run:

```bash
git diff -- packages/web/src/services/document.ts packages/web/src/views/resource/FileDetailView.vue
```

Expected: diff only changes `structured_data` typing and `templateData` narrowing.

If commit authorization is present, commit only these files plus the shared files if Task 1 was not committed separately:

```bash
git add packages/web/src/services/document.ts packages/web/src/views/resource/FileDetailView.vue
git commit -m "feat(web): narrow structured data template contract"
```

---

### Task 3: Lock backend structured-data write shape with helper tests

**Files:**
- Create: `packages/server-python/tests/contexts/document/test_structured_data_contract.py`
- Modify: `packages/server-python/app/contexts/document/application/tasks.py`

- [ ] **Step 1: Write failing backend tests**

Create `packages/server-python/tests/contexts/document/test_structured_data_contract.py` with exactly this content:

```python
"""Structured-data container contract tests for document tasks.

TD-009 keeps the public FileDTO response compatible while locking the
internal JSON container shape written by parse/extract tasks.
"""

import json

import pytest

from app.contexts.document.application.tasks import (
    _build_parsed_structured_data,
    _merge_template_structured_data,
)


def test_build_parsed_structured_data_uses_stable_container_keys() -> None:
    data = _build_parsed_structured_data("## 第一章\n内容", 3)

    assert data == {
        "full_text": "## 第一章\n内容",
        "section_count": 3,
    }
    assert isinstance(data["full_text"], str)
    assert isinstance(data["section_count"], int)


def test_merge_template_structured_data_preserves_parse_fields() -> None:
    existing = {"full_text": "正文", "section_count": 2, "custom": ["keep"]}
    template = {"title": "课程标准", "sections": ["一", "二"]}

    data = _merge_template_structured_data(existing, template)

    assert data == {
        "full_text": "正文",
        "section_count": 2,
        "custom": ["keep"],
        "template": {"title": "课程标准", "sections": ["一", "二"]},
    }
    assert data["template"] is not template


def test_merge_template_structured_data_accepts_legacy_json_string() -> None:
    existing = json.dumps({"full_text": "正文", "section_count": 1}, ensure_ascii=False)

    data = _merge_template_structured_data(existing, {"summary": "摘要"})

    assert data == {
        "full_text": "正文",
        "section_count": 1,
        "template": {"summary": "摘要"},
    }


def test_merge_template_structured_data_requires_template_object() -> None:
    with pytest.raises(TypeError, match="template_data must be a dict"):
        _merge_template_structured_data({}, ["not", "object"])  # type: ignore[arg-type]
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py -q
```

Expected: FAIL during import because `_build_parsed_structured_data` and `_merge_template_structured_data` are not defined.

- [ ] **Step 3: Add pure helpers to `tasks.py`**

In `packages/server-python/app/contexts/document/application/tasks.py`, add these helpers after `_check_pipeline_stale` and before the `parse_document` task:

```python
def _build_parsed_structured_data(full_text: str, section_count: int) -> dict[str, object]:
    """Build the stable structured_data container written by parse_document."""
    return {"full_text": full_text, "section_count": section_count}


def _merge_template_structured_data(
    existing: object,
    template_data: dict[str, object],
) -> dict[str, object]:
    """Merge template extraction output into the structured_data container."""
    if not isinstance(template_data, dict):
        raise TypeError("template_data must be a dict")

    if isinstance(existing, str):
        existing = json.loads(existing)

    if isinstance(existing, dict):
        merged: dict[str, object] = dict(existing)
    else:
        merged = {}

    merged["template"] = dict(template_data)
    return merged
```

- [ ] **Step 4: Use `_build_parsed_structured_data` in parse write path**

In `parse_document`, replace the inline JSON data construction:

```python
                    "data": json.dumps({
                        "full_text": parsed.full_text,
                        "section_count": len(parsed.sections),
                    }),
```

with:

```python
                    "data": json.dumps(
                        _build_parsed_structured_data(
                            parsed.full_text,
                            len(parsed.sections),
                        )
                    ),
```

- [ ] **Step 5: Use `_merge_template_structured_data` in extract write path**

In `extract_template`, replace this block:

```python
            if isinstance(existing_raw, str):
                existing_data = json.loads(existing_raw)
            else:
                existing_data = dict(existing_raw)
            existing_data["template"] = template_data
```

with:

```python
            existing_data = _merge_template_structured_data(existing_raw, template_data)
```

- [ ] **Step 6: Run the focused backend tests**

Run:

```bash
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py -q
```

Expected: PASS with 4 passed.

- [ ] **Step 7: Run ruff on touched backend files**

Run:

```bash
cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/application/tasks.py tests/contexts/document/test_structured_data_contract.py
```

Expected: PASS with exit code 0.

- [ ] **Step 8: Checkpoint**

Run:

```bash
git diff -- packages/server-python/app/contexts/document/application/tasks.py packages/server-python/tests/contexts/document/test_structured_data_contract.py
```

Expected: diff only adds two pure helpers, replaces the two structured-data write constructions, and adds focused tests.

If commit authorization is present, commit only these files:

```bash
git add packages/server-python/app/contexts/document/application/tasks.py packages/server-python/tests/contexts/document/test_structured_data_contract.py
git commit -m "test(document): lock structured data container shape"
```

---

### Task 4: Sync docs and run final validation

**Files:**
- Modify: `docs/specs/2026-06-05-td-009-structured-data-contract.md`
- Modify: `docs/engineering/current-work.md`
- Modify: `docs/engineering/technical-debt.md`
- Modify: `docs/plans/2026-06-05-td-009-structured-data-contract-plan.md`

- [ ] **Step 1: Update the spec plan link**

In `docs/specs/2026-06-05-td-009-structured-data-contract.md`, change the header plan line to:

```md
> 计划：[plans/2026-06-05-td-009-structured-data-contract-plan.md](../plans/2026-06-05-td-009-structured-data-contract-plan.md)
```

- [ ] **Step 2: Update TD-009 current-work progress before final validation**

In `docs/engineering/current-work.md`, keep TD-009 in “当前进行中” until validation finishes. Use this row shape after implementation and before final status change:

```md
| TD-009 减少前后端契约漂移 | 🟡 进行中 | P2 | API / 类型 | shared structured_data schema、前端 template 窄化、后端写入 shape helper/tests 已完成。 | 运行完成门禁并同步技术债交付记录。 | 待记录最终验证命令。 |
```

- [ ] **Step 3: Run full required validation**

Run these commands in order:

```bash
pnpm --filter @metaedu/shared typecheck
pnpm --filter @metaedu/web typecheck
cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py -q
cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/application/tasks.py tests/contexts/document/test_structured_data_contract.py
scripts/check-engineering-docs
```

Expected:

- Shared typecheck exits 0.
- Web typecheck exits 0.
- Focused pytest reports `4 passed`.
- Ruff exits 0.
- Engineering docs check prints `engineering docs checks passed`.

If any command fails, do not mark TD-009 complete. Fix the failure if it belongs to this task; otherwise record the failure with the exact command and summary.

- [ ] **Step 4: Verify contract-specific grep checks**

Run:

```bash
rg -n "FileStructuredData|getTemplateStructuredData|FileStructuredDataSchema" packages/shared/src/schemas/document.ts packages/web/src/services/document.ts packages/web/src/views/resource/FileDetailView.vue
rg -n "structured_data as Record<string, unknown>|\[\"template\"\] as Record<string, unknown>" packages/web/src/views/resource/FileDetailView.vue
rg -n "_build_parsed_structured_data|_merge_template_structured_data" packages/server-python/app/contexts/document/application/tasks.py packages/server-python/tests/contexts/document/test_structured_data_contract.py
```

Expected:

- First command shows shared schema/helper usage in shared and frontend.
- Second command has no output and exits 1.
- Third command shows helper definitions/usages and tests.

- [ ] **Step 5: Update TD-009 technical-debt delivery record**

After all validation passes, update `docs/engineering/technical-debt.md` TD-009 detail status from in-progress to completed using the standard green completed marker.

In the TD-009 `交付记录` section, replace `未完成。` with a concise record:

```md
- 2026-06-05 完成（接手工具：Claude Code）。本轮选择结构化抽取结果容器作为契约族：`packages/shared` 新增 `FileStructuredDataSchema` / `FileStructuredData` / `getTemplateStructuredData`；前端 `FileDTO.structured_data` 复用 shared 类型，`FileDetailView` 读取 `template` 前通过 shared helper 窄化；后端抽出 parse/extract structured_data 写入 helper 并补聚焦测试。
- 行为变化声明：正常 `template` object 展示不变；如果后端或历史数据把 `structured_data.template` 写成非 object，前端不再强转展示，而是按无抽取结果处理。
- 验证摘要：`pnpm --filter @metaedu/shared typecheck` 退出码 0；`pnpm --filter @metaedu/web typecheck` 退出码 0；`cd packages/server-python && .venv/bin/python -m pytest tests/contexts/document/test_structured_data_contract.py -q` 4 passed；`cd packages/server-python && .venv/bin/python -m ruff check app/contexts/document/application/tasks.py tests/contexts/document/test_structured_data_contract.py` 退出码 0；`scripts/check-engineering-docs` 退出码 0。
```

Also update the task overview row for TD-009 from `🟡 进行中` to `🟢 完成` and keep the spec/plan fact source.

- [ ] **Step 6: Update current-work final state**

Move TD-009 out of “当前进行中”. Set the current row back to the empty state:

```md
| 暂无 | ⚫ 待办 | - | - | 当前没有已开工任务。 | 从“下一批候选任务”或用户指定任务开工。 | - |
```

Remove TD-009 from “下一批候选任务” if it is still listed there. If no next candidate is selected, use the empty candidate row:

```md
| 暂无 | ⚫ 待办 | - | - | 当前没有近期候选任务。 |
```

Add a new top row to “最近完成”:

```md
| 2026-06-05 | TD-009 减少前后端契约漂移 | 🟢 完成 | 结构化抽取结果容器契约显式化：shared schema/type/helper、前端 template 窄化、后端写入 shape 测试。 | [Spec](../specs/2026-06-05-td-009-structured-data-contract.md) / [Plan](../plans/2026-06-05-td-009-structured-data-contract-plan.md) |
```

Keep only the most recent 5 rows in “最近完成”. If adding TD-009 makes 6 rows, move the oldest row into `docs/engineering/work-log.md` before deleting it from current-work.

- [ ] **Step 7: Mark plan checkboxes complete**

As implementation finishes, change each completed checkbox in this plan from `- [ ]` to `- [x]`. Keep only genuinely completed steps checked.

- [ ] **Step 8: Re-run engineering docs check after status updates**

Run:

```bash
scripts/check-engineering-docs
```

Expected: `engineering docs checks passed` and exit code 0.

- [ ] **Step 9: Final diff check**

Run:

```bash
git diff --name-status
git status --short --branch
```

Expected changed files are limited to TD-009 implementation and required docs:

```text
M	docs/engineering/current-work.md
M	docs/engineering/technical-debt.md
M	docs/specs/2026-06-05-td-009-structured-data-contract.md
A	docs/plans/2026-06-05-td-009-structured-data-contract-plan.md
M	packages/server-python/app/contexts/document/application/tasks.py
A	packages/server-python/tests/contexts/document/test_structured_data_contract.py
A	packages/shared/src/schemas/document.ts
M	packages/shared/src/schemas/index.ts
M	packages/web/src/services/document.ts
M	packages/web/src/views/resource/FileDetailView.vue
```

If current-work recent-completed pruning requires a work-log update, include `docs/engineering/work-log.md` in the expected diff and explain why.

If commit authorization is present, commit all final TD-009 changes:

```bash
git add docs/engineering/current-work.md docs/engineering/technical-debt.md docs/specs/2026-06-05-td-009-structured-data-contract.md docs/plans/2026-06-05-td-009-structured-data-contract-plan.md packages/server-python/app/contexts/document/application/tasks.py packages/server-python/tests/contexts/document/test_structured_data_contract.py packages/shared/src/schemas/document.ts packages/shared/src/schemas/index.ts packages/web/src/services/document.ts packages/web/src/views/resource/FileDetailView.vue
git commit -m "feat(contract): add structured data container schema"
```
