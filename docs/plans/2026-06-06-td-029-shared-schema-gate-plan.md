# TD-029 Shared Schema Gate Implementation Plan

> **Status:** 🟢 完成 — 2026-06-06。Plan checkboxes represent the original execution order; the canonical post-delivery record is in `docs/engineering/technical-debt.md#td-029-收口-td-009-的-shared-schema-门禁与-filedetailview-类型错误` 交付记录段。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `pnpm typecheck` / web typecheck / web build pass on a clean checkout by removing the broken `@metaedu/shared` project reference and fixing `FileDetailView` 的 `templateFieldLabel(key)` type error, then correct TD-009 验证摘要的描述使其与真实命令输出一致。

**Architecture:** `packages/shared/package.json` 已声明 `"exports": { "./schemas/*": "./src/schemas/*.ts" }`，把 schema 事实源指向源文件；`packages/web/tsconfig.json` 的 `references: [{ path: "../shared" }]` 与之冲突，强制要求未生成的 `dist/*.d.ts`。本计划删除 references 让 TS 通过 exports 直接读源；同时在 `FileDetailView.vue` 模板调用点把 `v-for` 推断的 `string | number` 显式收敛为 `string`；最后修正 TD-009 交付记录的验证摘要表述。

**Tech Stack:** pnpm workspaces, TypeScript 5.8 + vue-tsc, Vue 3 SFC, Zod schemas, project-internal docs gate (`scripts/check-engineering-docs`).

---

## Scope and constraints

- Canonical spec: `docs/specs/2026-06-06-td-029-shared-schema-gate.md`.
- TD-029 卡片：`docs/engineering/technical-debt.md#td-029-收口-td-009-的-shared-schema-门禁与-filedetailview-类型错误`。
- 不引入 turbo `dependsOn` 或新工具链；不为 `@metaedu/shared` 加 `build` script；不入库 `packages/shared/dist/`。
- 不修改 TD-009 spec、plan、设计字段或后端实现；只修 TD-009 交付记录里的「验证摘要」一行表述。
- 不处理与 TD-029 无关的 typecheck / build 噪声；若发现，登记为新 TD。
- Worktree 与分支已就绪（`refactor/td-029-shared-schema-gate`）；任务开工时卡片状态置为 🟡 进行中，完成后由 Task 4 翻为 🟢 完成。
- 默认不提交；commit 命令仅在用户授权完整 Git 闭环时执行。

## File structure

| File | Responsibility |
|------|----------------|
| `packages/web/tsconfig.json` | 删除 `references` 字段，让 web 通过 `@metaedu/shared` 的 `exports` 直接读 `src/*.ts`。 |
| `packages/web/src/views/resource/FileDetailView.vue` | 第 107 行 `templateFieldLabel(key)` → `templateFieldLabel(String(key))`，把 `v-for` 推断的 `string \| number` 收敛到 `string`。 |
| `docs/engineering/technical-debt.md` | TD-009 详情段「验证摘要」中关于 `pnpm --filter @metaedu/web typecheck` 的描述改为事实表述，并指向 TD-029 收口。 |
| `docs/engineering/current-work.md` | 任务完成后把 TD-029 从「当前进行中」移到「最近完成」（5 行强约束，必要时归档最旧条目到 work-log）。 |
| `docs/engineering/work-log.md` | 必要时新增 TD-029 索引；若 `current-work.md` 最近完成超 5 行，把最旧条目搬到这里。 |
| `docs/specs/2026-06-06-td-029-shared-schema-gate.md` | 任务完成后在 spec 顶部把 `计划` 链接更新成 plan 文件相对路径。 |

---

### Task 1: Reproduce TD-029 failures on the worktree branch

**Files:**
- Read-only: `packages/web/tsconfig.json`, `packages/shared/package.json`, `packages/web/src/views/resource/FileDetailView.vue`, `packages/web/src/services/document.ts`.

- [x] **Step 1: Confirm working directory and branch**

Run:

```bash
pwd
git rev-parse --abbrev-ref HEAD
```

Expected:

```text
/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/.claude/worktrees/td-029-shared-schema-gate
refactor/td-029-shared-schema-gate
```

If you are not in the worktree on the named branch, stop and re-enter the worktree before proceeding.

- [x] **Step 2: Reproduce TS6305 + TS2345 on web typecheck**

Run:

```bash
pnpm --filter @metaedu/web typecheck 2>&1 | tail -10
echo "EXIT=$?"
```

Expected: non-zero exit (typically `Exit status 2`) with three errors:

```text
src/services/document.ts(2,41): error TS6305: Output file '.../packages/shared/dist/schemas/document.d.ts' has not been built ...
src/views/resource/FileDetailView.vue(107,42): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'.
src/views/resource/FileDetailView.vue(211,43): error TS6305: ...
```

Capture this output verbatim; it is the baseline failure TD-029 has to clear.

- [x] **Step 3: Confirm baseline that does NOT change**

Run:

```bash
pnpm --filter @metaedu/shared typecheck
echo "EXIT=$?"
```

Expected: exit 0 (shared package's own `tsc --noEmit` already passes; nothing to fix here).

- [x] **Step 4: Confirm only two consumers of `@metaedu/shared`**

Run:

```bash
rg -n "@metaedu/shared" packages/web/src/ packages/shared/src/
```

Expected: exactly two hits in web (`packages/web/src/services/document.ts:2` and `packages/web/src/views/resource/FileDetailView.vue:211`). If more hits appear, stop and re-scope the plan — Task 2 only removes the project reference; additional consumers may need follow-up.

---

### Task 2: Remove the web → shared project reference

**Files:**
- Modify: `packages/web/tsconfig.json`

- [x] **Step 1: Inspect the current tsconfig**

Run:

```bash
cat packages/web/tsconfig.json
```

Expected:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "types": ["vite/client"]
  },
  "include": ["src/**/*", "src/**/*.vue", "env.d.ts"],
  "references": [
    { "path": "../shared" }
  ]
}
```

If `references` is already missing or contains additional entries, stop and reconcile with the spec before continuing.

- [x] **Step 2: Remove the references array**

Edit `packages/web/tsconfig.json`. Replace the entire file with:

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "outDir": "./dist",
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "types": ["vite/client"]
  },
  "include": ["src/**/*", "src/**/*.vue", "env.d.ts"]
}
```

The only change is dropping the `references` field and its trailing comma after `include`. Do not touch `compilerOptions`, `paths`, or `include`.

- [x] **Step 3: Re-run web typecheck**

Run:

```bash
pnpm --filter @metaedu/web typecheck 2>&1 | tail -10
echo "EXIT=$?"
```

Expected: the two TS6305 errors are gone. A single TS2345 may still appear:

```text
src/views/resource/FileDetailView.vue(107,42): error TS2345: Argument of type 'number' is not assignable to parameter of type 'string'.
EXIT=2
```

If TS6305 still appears, stop and re-read `packages/shared/package.json` `exports` — there may be a second consumer not yet covered.

- [x] **Step 4: Snapshot the intermediate diff**

Run:

```bash
git diff -- packages/web/tsconfig.json
```

Expected: only `references` block removed (plus the comma after `include`). No other changes.

- [x] **Step 5: Commit (only if commit authorization is present)**

```bash
git add packages/web/tsconfig.json
git commit -m "build(web): drop shared project reference for source-only consumption

Web tsconfig referenced @metaedu/shared as a composite project, which
required tsc -b to emit dist/*.d.ts before vue-tsc would resolve schema
imports. packages/shared already exports './schemas/*' → './src/*.ts',
so let TS resolve through exports and remove the dist dependency.

Refs TD-029."
```

---

### Task 3: Fix FileDetailView templateFieldLabel key type

**Files:**
- Modify: `packages/web/src/views/resource/FileDetailView.vue:107`

- [x] **Step 1: Confirm the call site**

Run:

```bash
rg -n "templateFieldLabel" packages/web/src/views/resource/FileDetailView.vue
```

Expected:

```text
107:              :label="templateFieldLabel(key)"
296:function templateFieldLabel(key: string): string {
```

Exactly one call site at line 107, exactly one definition at line 296. If counts differ, stop and re-scope.

- [x] **Step 2: Replace the call-site expression**

Edit `packages/web/src/views/resource/FileDetailView.vue`. Find:

```vue
              :label="templateFieldLabel(key)"
```

Replace with:

```vue
              :label="templateFieldLabel(String(key))"
```

This is the only change in the file. Do not touch the `templateFieldLabel` definition, the `v-for`, or any surrounding markup.

- [x] **Step 3: Re-run web typecheck**

Run:

```bash
pnpm --filter @metaedu/web typecheck 2>&1 | tail -5
echo "EXIT=$?"
```

Expected: exit 0 with no error output.

- [x] **Step 4: Run root pnpm typecheck**

Run:

```bash
pnpm typecheck 2>&1 | tail -15
echo "EXIT=$?"
```

Expected: exit 0; both `@metaedu/shared` and `@metaedu/web` packages report success (turbo runs them in dependency order).

- [x] **Step 5: Run web build**

Run:

```bash
pnpm --filter @metaedu/web build 2>&1 | tail -10
echo "EXIT=$?"
```

Expected: exit 0; Vite emits the production bundle to `packages/web/dist/`.

- [x] **Step 6: Run backend regression to confirm TD-009 server tests still pass**

Run from the worktree root:

```bash
/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/server-python/.venv/bin/python -m pytest packages/server-python/tests/contexts/document/test_structured_data_contract.py -q
echo "EXIT=$?"
```

Expected:

```text
....                                                                     [100%]
4 passed in 0.01s
EXIT=0
```

This is a regression guard; TD-029 must not break TD-009 backend tests.

- [x] **Step 7: Snapshot the intermediate diff**

Run:

```bash
git diff -- packages/web/src/views/resource/FileDetailView.vue
```

Expected: exactly one line changed (the `:label` expression).

- [x] **Step 8: Commit (only if commit authorization is present)**

```bash
git add packages/web/src/views/resource/FileDetailView.vue
git commit -m "fix(web): coerce templateData v-for key to string for label call

v-for over Record<string, unknown> infers key as string | number; the
display layer passes it to templateFieldLabel(key: string). Wrap with
String(...) at the call site so the TS contract holds regardless of
how templateData is typed in the future.

Refs TD-029."
```

---

### Task 4: Correct TD-009 验证摘要 and sync TD-029 status

**Files:**
- Modify: `docs/engineering/technical-debt.md` (TD-009 详情段 + TD-029 详情段 + 总览表)
- Modify: `docs/engineering/current-work.md`
- Modify: `docs/engineering/work-log.md` (only if recent-completed needs to evict an old entry)
- Modify: `docs/specs/2026-06-06-td-029-shared-schema-gate.md` (header `计划` link)

- [x] **Step 1: Update TD-009 验证摘要 to match reality**

In `docs/engineering/technical-debt.md`, find this line inside the TD-009 `交付记录`:

```md
- 验证摘要：`pnpm --filter @metaedu/shared typecheck` 退出码 0；`pnpm --filter @metaedu/web typecheck` 退出码 0；`pytest tests/contexts/document/test_structured_data_contract.py -q` 4 passed；`ruff check app/contexts/document/application/tasks.py tests/contexts/document/test_structured_data_contract.py` 退出码 0；`scripts/check-engineering-docs` 退出码 0。
```

Replace with:

```md
- 验证摘要：`pnpm --filter @metaedu/shared typecheck` 退出码 0；`pnpm --filter @metaedu/shared --filter @metaedu/web typecheck`（顺序执行）退出码 0；`pytest tests/contexts/document/test_structured_data_contract.py -q` 4 passed；`ruff check app/contexts/document/application/tasks.py tests/contexts/document/test_structured_data_contract.py` 退出码 0；`scripts/check-engineering-docs` 退出码 0。干净 checkout 上单独运行 `pnpm --filter @metaedu/web typecheck` 因 shared composite project reference 缺少 `dist/*.d.ts` 而报 `TS6305`；该门禁缺口已由 [TD-029](../engineering/technical-debt.md#td-029-收口-td-009-的-shared-schema-门禁与-filedetailview-类型错误) 收口。
```

不改任何其它 TD-009 字段（spec / plan / 设计 / 行为变化声明保持原样）。

- [x] **Step 2: Update the TD-029 spec header `计划` link**

In `docs/specs/2026-06-06-td-029-shared-schema-gate.md`, find:

```md
> 计划：批准 spec 后创建 implementation plan
```

Replace with:

```md
> 计划：[plans/2026-06-06-td-029-shared-schema-gate-plan.md](../plans/2026-06-06-td-029-shared-schema-gate-plan.md)
```

- [x] **Step 3: Update TD-029 task overview + detail status to 🟢 完成**

In `docs/engineering/technical-debt.md`, find in the 任务总览 table:

```md
| TD-029 | 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误 | 🟡 进行中 | P1 | 前端 / 类型 / 交付 | [Spec](../specs/2026-06-06-td-029-shared-schema-gate.md) |
```

Replace with:

```md
| TD-029 | 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误 | 🟢 完成 | P1 | 前端 / 类型 / 交付 | [Spec](../specs/2026-06-06-td-029-shared-schema-gate.md) / [Plan](../plans/2026-06-06-td-029-shared-schema-gate-plan.md) |
```

In the TD-029 detail block, find the in-progress status marker line (the standard `状态：` line that currently uses the yellow in-progress marker) and replace it with the standard green completed marker line. Do not edit any other fields in the block.

In the same detail block, find `**交付记录**` section content:

```md
**交付记录**
- 未完成。由 TD-009 复核新增：shared schema 引入后暴露出 `@metaedu/shared` project reference / declaration 产物链路缺口，以及 `FileDetailView` 模板字段 key 的真实类型错误。
```

Replace with:

```md
**交付记录**
- 2026-06-06 完成（接手工具：Claude Code）。删除 `packages/web/tsconfig.json` 中对 `../shared` 的 project reference，让 TS 通过 `@metaedu/shared` 的 `exports` 直接读 `src/*.ts`，消除 `TS6305`；`FileDetailView.vue:107` 的 `templateFieldLabel(key)` 改为 `templateFieldLabel(String(key))`，把 `v-for` 推断的 `string | number` 收敛到 `string`，消除 `TS2345`；同步修正 TD-009 交付记录验证摘要表述。
- 行为变化声明：无 runtime 行为变化；仅影响 TypeScript 编译时模块解析路径与一个 v-for key 的类型收敛。
- 验证摘要：`pnpm --filter @metaedu/shared typecheck` 退出码 0；`pnpm --filter @metaedu/web typecheck` 退出码 0；`pnpm typecheck` 退出码 0；`pnpm --filter @metaedu/web build` 退出码 0；`pytest tests/contexts/document/test_structured_data_contract.py -q` 4 passed（TD-009 后端回归）；`scripts/check-engineering-docs` 退出码 0。
```

- [x] **Step 4: Move TD-029 out of 当前进行中 to 最近完成**

In `docs/engineering/current-work.md` 当前进行中区域，把 TD-029 行替换回空行：

```md
| 暂无 | ⚫ 待办 | - | - | 当前没有已开工任务。 | 从“下一批候选任务”或用户指定任务开工。 | - |
```

「下一批候选任务」如果没有新候选，保持：

```md
| 暂无 | ⚫ 待办 | - | - | 当前没有近期候选任务。 |
```

在「最近完成」顶部新增一行（5 行强约束！见 Step 5）：

```md
| 2026-06-06 | TD-029 收口 TD-009 的 shared schema 门禁与 FileDetailView 类型错误 | 🟢 完成 | 去掉 web 对 shared 的 project reference + `FileDetailView` v-for key 用 `String(...)` 收敛 + TD-009 验证摘要校正。 | [Spec](../specs/2026-06-06-td-029-shared-schema-gate.md) / [Plan](../plans/2026-06-06-td-029-shared-schema-gate-plan.md) |
```

- [x] **Step 5: Enforce 最近完成 ≤ 5 rows**

Run:

```bash
awk '/^## 最近完成/{flag=1; next} /^## /{flag=0} flag && /^\| 2026/{count++} END{print count}' docs/engineering/current-work.md
```

If the result is 6, archive the oldest row by:

1. Reading the oldest row text from the bottom of 最近完成 in `docs/engineering/current-work.md`.
2. Inserting a matching index row at the top of `docs/engineering/work-log.md` 的索引表（紧跟在 `|------|...|` header 行之后）。索引行 schema：

   ```md
   | 2026-06-05 | TD-027 补 `ui-input` / `ui-btn-*` / `ui-tag-*` / `ui-dialog` 共享类（设计系统扩展） | 技术债 / 设计系统 | [#59](https://github.com/MarkDanile/MetaEduBase/pull/59) |  | `docs/engineering/technical-debt.md#td-027` |
   ```

   依据被驱逐行的实际任务编号/标题/事实源调整字段。

3. 从 `docs/engineering/current-work.md` 最近完成表删除该旧行。

如果 awk 结果 ≤ 5，跳过这一步。

- [x] **Step 6: Run engineering docs gate**

Run:

```bash
scripts/check-engineering-docs
echo "EXIT=$?"
```

Expected: `engineering docs checks passed`, EXIT=0.

If it complains about a missing link, an unsynced status, or recent-completed > 5, fix it inline and re-run before continuing.

- [x] **Step 7: Final validation matrix**

Run each command and confirm exit codes:

```bash
pnpm --filter @metaedu/shared typecheck
pnpm --filter @metaedu/web typecheck
pnpm typecheck
pnpm --filter @metaedu/web build
/Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase/packages/server-python/.venv/bin/python -m pytest packages/server-python/tests/contexts/document/test_structured_data_contract.py -q
scripts/check-engineering-docs
```

Expected exit codes:

| Command | Expected |
|---|---|
| `pnpm --filter @metaedu/shared typecheck` | 0 |
| `pnpm --filter @metaedu/web typecheck` | 0 |
| `pnpm typecheck` | 0 |
| `pnpm --filter @metaedu/web build` | 0 |
| backend pytest | 0 (4 passed) |
| `scripts/check-engineering-docs` | 0 |

If any command fails, do not mark TD-029 完成. Either fix in scope or stop and report.

- [x] **Step 8: Confirm diff scope**

Run:

```bash
git status --short --branch
git diff --name-status main
```

Expected modified files (M) and untracked (??) are limited to:

```text
M docs/engineering/current-work.md
M docs/engineering/technical-debt.md
M packages/web/src/views/resource/FileDetailView.vue
M packages/web/tsconfig.json
?? docs/plans/2026-06-06-td-029-shared-schema-gate-plan.md
?? docs/specs/2026-06-06-td-029-shared-schema-gate.md
```

如果 Step 5 触发了 work-log 归档，额外允许：

```text
M docs/engineering/work-log.md
```

不应有其它任何文件。

- [x] **Step 9: Mark plan checkboxes complete**

As each step finishes, flip its `- [ ]` to `- [x]` in this plan file. Only check off genuinely completed steps; do not bulk-flip.

- [x] **Step 10: Commit docs (only if commit authorization is present)**

```bash
git add docs/specs/2026-06-06-td-029-shared-schema-gate.md docs/plans/2026-06-06-td-029-shared-schema-gate-plan.md docs/engineering/current-work.md docs/engineering/technical-debt.md
# Append work-log if Step 5 archived a row:
# git add docs/engineering/work-log.md
git commit -m "docs(engineering): record TD-029 shared schema gate fix

Add TD-029 spec + plan and mark the task completed in technical-debt
overview and detail. Correct TD-009 验证摘要 to reflect the actual
worktree command (shared+web filter run together) and link to TD-029
for the clean-checkout gate fix. Move TD-029 into current-work
recent-completed (with work-log archival if the 5-row limit forces
eviction)."
```
