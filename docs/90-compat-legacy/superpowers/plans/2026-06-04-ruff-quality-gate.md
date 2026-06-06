# TD-012: 后端全量 ruff 质量门禁 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `packages/server-python` 的 `ruff check app/ tests/` 退出码为 0，并使其成为稳定可用的后端静态检查门禁。

**Architecture:** 一次性 1 个 PR 治理 148 个 ruff 错误，路径分四层：(1) ruff 自动修复层 → (2) E501 折行层 → (3) B008 FastAPI Depends 改写层 → (4) 其它规则手工处理层（SIM/B/UP/N/E741）。零业务逻辑变更；不改 ruff 规则集；不动 mypy。

**Tech Stack:** ruff >= 0.9.0（已配置 `pyproject.toml`），Python 3.12，FastAPI Annotated 语法（用于 B008 治理），PEP 695 泛型（用于 UP046）。

**来源 spec:** [docs/90-compat-legacy/superpowers/specs/2026-06-04-ruff-quality-gate-design.md](../../01-specs/2026-06-04-ruff-quality-gate-design.md)

**当前基线（2026-06-04 勘测）：** 148 个 ruff 错误，按规则分布：E501 107 / B008 17 / F401 11 / I001 3 / E402 2 / SIM105 2 / B007 1 / B905 1 / E741 1 / N806 1 / SIM117 1 / UP046 1。

**提交策略（用户已确认）：** 1 个 PR，1 个 squash commit。所有改动集中于一个原子 commit，便于 review 一次性看全 148 处的"零行为变更"声明。Plan 内部按 layer 顺序推进；若中途需要回滚，按 layer 边界回退即可。

---

## Task 1: 自动修复层（spec 步骤 1+2）

**Files:**
- Modify: `packages/server-python/app/celery_app.py`（E402 / F401 / I001）
- Modify: `packages/server-python/app/shared/llm/chat.py`（F401 / I001）
- Modify: `packages/server-python/tests/conftest.py`（I001）
- Modify: 其它 ruff 报告"fixable with `--fix`"的项

**目标:** 让 `ruff check --fix` 与 `ruff check --fix --unsafe-fixes` 处理所有自动可修项，仅剩需手工修复的 E501 / B008 / SIM / UP 等。

### Step 1.1: 切到任务分支并确认基线

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git checkout main
git pull --ff-only
git checkout -b refactor/td-012-ruff-quality-gate
```

期望: 新分支从最新 main 切出。运行 `git status --short` 期望为空。

### Step 1.2: 记录自动修复前基线

```bash
cd packages/server-python
.venv/bin/python -m ruff check app/ tests/ --output-format=concise 2>&1 | tee /tmp/td012-baseline.txt
```

期望: `Found 148 errors.`、11 个 fixable（celery_app.py）、3 个 unsafe fixable、合计 14 个可自动修复项。

### Step 1.3: 执行 `--fix`（安全自动修复）

```bash
cd packages/server-python
.venv/bin/python -m ruff check --fix app/ tests/ 2>&1 | tail -20
```

期望: 报告修复的项数。运行后再次 `ruff check app/ tests/` 应减少 11 个 fixable 项。

### Step 1.4: 复核 `--fix` 后的 diff，确认未触碰业务代码

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git diff --stat
git diff packages/server-python/app/celery_app.py packages/server-python/app/shared/llm/chat.py packages/server-python/tests/conftest.py
```

期望: diff 仅包含 import 排序、import 合并、F401 删除；**不包含**函数体、字符串、注释变更。若 diff 命中任何业务函数体，回退该文件：

```bash
git checkout -- packages/server-python/app/celery_app.py
```

并把对应项转为人工处理（仅当 `--fix` 错误地命中了非 import 区域时）。

### Step 1.5: 评估 `--unsafe-fixes` 范围

```bash
cd packages/server-python
.venv/bin/python -m ruff check --fix --unsafe-fixes --no-show-fixes --statistics app/ tests/ 2>&1 | tail -30
```

期望: 看到 3 个 unsafe 修复项的位置（仅 F401 类型的"unused import in `__init__.py`/re-export"模式才需要 unsafe）。

逐项阅读将要删除的 import：
- 若被删 import 仅作为 `importlib.import_module(...)` 的字符串名引用，**不要**删除。
- 若被删 import 是模块顶部 `from x import y` 且 `y` 确实未在文件中以 `y` 名称使用，删除安全。

记录这 3 个 import 路径，写入 `/tmp/td012-unsafe-imports.txt`。

### Step 1.6: 执行 `--unsafe-fixes`

```bash
cd packages/server-python
.venv/bin/python -m ruff check --fix --unsafe-fixes app/ tests/ 2>&1 | tail -20
```

### Step 1.7: 复核 unsafe diff，逐项确认

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git diff --stat
```

对每个被删的 import：
- `grep -rn "<deleted_symbol>" packages/server-python/` 确认符号未被字符串引用
- `grep -rn "<deleted_module>" packages/server-python/` 确认模块未被动态导入

若任何一项命中"被字符串/动态 import 引用"，回退该文件：

```bash
git checkout -- <file_path>
```

并把对应 F401 标记为"需要人工处理"——后续在 Task 4 通用规则手工步骤中确认是否保留 import。

### Step 1.8: 手工处理 celery_app.py 残留的 E402

期望: `app/celery_app.py` 现在应只剩 2 个 E402（在注释块后 import 触发的），但 spec 规定不静默 `# noqa: E402`。处理方式：把 `app/celery_app.py` 顶部"Manually import all tasks..."等说明性注释改写为模块 docstring。

读取当前文件：
```bash
cd packages/server-python
sed -n '1,45p' app/celery_app.py
```

把文件开头（line 1-21 附近的注释块）改写为：

```python
"""Celery application bootstrap.

Manually import all tasks to ensure they are registered with the worker.

Document tasks
==============
parse_document, chunk_document, embed_chunks, index_tsvector,
extract_template, extract_knowledge_graph

Structured data tasks
=====================
ds_parse, ds_embed, ds_extract_kg, ds_build_cross_dataset_edges
"""
from app.contexts.document.tasks import (
    parse_document,
    chunk_document,
    embed_chunks,
    index_tsvector,
    extract_template,
    extract_knowledge_graph,
)

from app.contexts.structured_data.tasks import (
    ds_parse,
    ds_embed,
    ds_extract_kg,
    ds_build_cross_dataset_edges,
)
```

注意：原文件中的注释列表与 import 列表一一对应；改写时**保持 import 顺序与符号不变**，仅把 `# ...` 注释换成 docstring + 紧随其后的 import。这样既消除了 E402，也保留了原注册语义。

### Step 1.9: 验证 Task 1 完成状态

```bash
cd packages/server-python
.venv/bin/python -m ruff check app/ tests/ --statistics 2>&1 | tail -20
```

期望: 错误数从 148 下降到约 130-134（移除 14 个自动修复 + 2 个 E402）。剩余应为 E501 / B008 / SIM / B007 / B905 / E741 / N806 / SIM117 / UP046 / 极少数 F401。

记录剩余数字到 `/tmp/td012-after-auto-fix.txt`。

---

## Task 2: E501 折行层（spec 步骤 3）

**Files:**
- Modify: 多个 `app/` 与 `tests/` 文件中 E501 命中行（见 Step 2.1 重新锁定清单）

**目标:** 修复所有剩余 E501 行。零业务逻辑变更；不缩短变量名绕过；不可拆字符串允许 `# noqa: E501` + 理由注释。

### Step 2.1: 重新锁定 E501 清单

```bash
cd packages/server-python
.venv/bin/python -m ruff check --select E501 --output-format=concise app/ tests/ 2>&1 | tee /tmp/td012-e501-list.txt
```

按文件聚合：
```bash
grep -E '\.py:' /tmp/td012-e501-list.txt | awk -F: '{print $1}' | sort | uniq -c | sort -rn
```

期望（基于基线 107 个的合理预估）：`app/contexts/document/application/tasks.py` 仍是最大头（约 30 个），其次 `app/contexts/structured_data/application/tasks.py`（约 15），`app/contexts/template/interfaces/api/router.py`（约 10-15），其它分散在各文件。

### Step 2.2: 按"大文件优先"分批处理

依次处理以下文件（每个文件处理完立即 ruff 验证 0 E501，再进入下一个）：

#### 子步骤 2.2.1: `app/contexts/document/application/tasks.py`

```bash
cd packages/server-python
.venv/bin/python -m ruff check --select E501 app/contexts/document/application/tasks.py 2>&1
```

逐行折行。优先策略：
- 二元运算符（`+`、`,`、`and`/`or`）在运算符**前**或**后**换行（项目内已有约定时遵循；无约定时使用"运算符在前"风格，参考 PEP 8）。
- 函数调用：在第一个参数后换行，让每个参数独占一行。
- 集合字面量（dict / list / tuple）：在 `,` 后换行，每个元素独占一行。
- 长字符串：按 spec — 优先 Python 隐式拼接（`"a" "b"`），其次变量绑定，最后 `# noqa: E501` + 注释。

**禁止:**
- 缩短变量名绕过长度限制
- 把多行表达式合并为单行长字符串
- 修改函数语义、默认值、参数顺序

期望: 该文件 E501 计数为 0。

#### 子步骤 2.2.2: `app/contexts/structured_data/application/tasks.py`

同上策略。

#### 子步骤 2.2.3: `app/contexts/template/interfaces/api/router.py`

注意：本文件同时命中 B008（Task 3 处理）与 E501。B008 改写为 `Annotated[...]` 时可能自然缩短行；E501 与 B008 可以合并在同一次编辑中处理，但 ruff 验证要分开跑。

#### 子步骤 2.2.4: 其它含 E501 的小文件

包括但不限于（按 Step 2.1 实际清单）:
- `app/contexts/knowledge/infrastructure/models.py`
- `app/contexts/structured_data/infrastructure/dataset_repository.py`
- `app/contexts/knowledge/domain/repositories.py`
- `app/contexts/document/infrastructure/chunk_repository.py`
- `app/contexts/knowledge/infrastructure/knowledge_repository.py`
- `tests/conftest.py`
- `tests/contexts/resource/test_resource.py`
- `tests/contexts/knowledge/test_knowledge.py`
- `tests/contexts/ai/test_ai_chat.py`
- `tests/contexts/structured_data/test_datasets.py`
- 等等

每个文件单独 ruff 验证 0 E501 后再继续。

### Step 2.3: 验证 Task 2 完成

```bash
cd packages/server-python
.venv/bin/python -m ruff check --select E501 app/ tests/
echo "exit=$?"
```

期望: 退出码 0，无 E501 报告。

### Step 2.4: 全量 ruff 验证（确认 E501 修复未引入新错误）

```bash
cd packages/server-python
.venv/bin/python -m ruff check app/ tests/ --statistics 2>&1 | tail -20
```

期望: 错误总数下降到约 25-30（仅 B008 / SIM / B007 / B905 / E741 / N806 / SIM117 / UP046 / 极少数 F401）。

---

## Task 3: B008 治理（spec 步骤 4）

**Files:**
- Modify: `packages/server-python/app/contexts/identity/interfaces/api/dependencies.py:16-17`（2 处）
- Modify: `packages/server-python/app/contexts/resource/interfaces/api/router.py:63`（1 处）
- Modify: `packages/server-python/app/contexts/template/interfaces/api/router.py:23-109`（14 处）

**目标:** 把 17 处 B008 改为 FastAPI 现代惯用语法（`Annotated[...]`），消除"默认参数函数调用"警告。

### Step 3.1: 锁定 B008 清单

```bash
cd packages/server-python
.venv/bin/python -m ruff check --select B008 --output-format=concise app/ tests/ 2>&1
```

期望: 17 个 B008 项，集中在 3 个文件。

### Step 3.2: 处理 `dependencies.py` 的 2 处

读取当前文件：
```bash
cd packages/server-python
sed -n '1,30p' app/contexts/identity/interfaces/api/dependencies.py
```

按现有 import 结构，将 `from typing import Annotated` 加入 import（若尚未导入），并把：

```python
def some_func(x: SomeType = Depends(get_y)):
    ...
```

改为：

```python
def some_func(x: Annotated[SomeType, Depends(get_y)]):
    ...
```

注意：保持函数签名其它部分、类型注解、返回类型、装饰器不变。

### Step 3.3: 处理 `resource/router.py:63` 的 `File(...)` 调用

读取上下文：
```bash
cd packages/server-python
sed -n '55,75p' app/contexts/resource/interfaces/api/router.py
```

这是 `File = UploadFile = ...` 类用法，需具体判断。FastAPI `File` 在新版本中也是 `Annotated[UploadFile, File(...)]` 形式；若现有代码已经使用 `File(...)` 默认值，则按 `Annotated` 改写。

注意：spec 中明确"`File` 1 处"——按实际函数签名判断是把 `File` 当 default 还是当 default 后的另一个参数。

### Step 3.4: 处理 `template/router.py` 的 14 处

读取上下文：
```bash
cd packages/server-python
sed -n '20,115p' app/contexts/template/interfaces/api/router.py
```

这是最大的 B008 群。按 FastAPI 现代风格，对每个路由 handler：

```python
@router.post(...)
async def foo(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ...
):
    ...
```

改为：

```python
@router.post(...)
async def foo(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    ...
):
    ...
```

需要在文件顶部加 `from typing import Annotated`（如未导入）。

注意：保持路由装饰器、函数体、参数顺序完全不变。

### Step 3.5: 验证 B008 治理

```bash
cd packages/server-python
.venv/bin/python -m ruff check --select B008 app/ tests/
echo "exit=$?"
```

期望: 退出码 0，无 B008 报告。

### Step 3.6: 全量 ruff 验证

```bash
cd packages/server-python
.venv/bin/python -m ruff check app/ tests/ --statistics 2>&1 | tail -20
```

期望: 错误数下降到约 8-12（SIM / B / UP / N / E741 / 极少数 F401）。

---

## Task 4: 其它非 E501/B008 规则（spec 步骤 5）

**Files:** 多个文件，每个规则 1-2 处（见 Step 4.1 锁定清单）

**目标:** 修复 SIM105 / SIM117 / B007 / B905 / E741 / N806 / UP046 共 8 处。

### Step 4.1: 锁定剩余错误清单

```bash
cd packages/server-python
.venv/bin/python -m ruff check --select SIM,B007,B905,E741,N806,UP046 app/ tests/ --output-format=concise 2>&1 | tee /tmp/td012-misc-list.txt
```

期望（基线已知，Task 1-3 后数字可能略变）:

| 规则 | 位置 | 处理 |
|------|------|------|
| SIM105 | `app/contexts/document/application/tasks.py:829` | `try: json.loads(...) except JSONDecodeError: pass` 改 `contextlib.suppress(JSONDecodeError)` |
| SIM105 | `app/contexts/template/interfaces/api/router.py:61` | `try: ... except Exception: pass` 改 `contextlib.suppress(Exception)` |
| B007 | `app/contexts/structured_data/application/tasks.py:609` | 循环变量 `ds_id` 改 `_` |
| B905 | `app/contexts/document/application/tasks.py:466` | `zip(a, b)` 改 `zip(a, b, strict=True)` |
| E741 | `app/contexts/document/application/tasks.py:632` | 变量 `l` 改 `line` 或类似 |
| N806 | `app/shared/parsing/docx_parser.py:21` | 变量 `_HEADING_STYLE` 改 `_heading_style`（注意：保留下划线前缀以表达"模块私有"） |
| SIM117 | `tests/contexts/ai/test_ai_chat.py:52` | 嵌套 `with` 合并为单 `with` 多 context |
| UP046 | `app/shared/domain/repository.py:7` | `Generic[T]` 改 PEP 695 `class Repository[T]:` |

### Step 4.2: 逐项手工处理

每一项按 ruff 建议 + spec 原则改写：
- SIM105：导入 `from contextlib import suppress`，替换 try/except
- B007：循环变量改 `_`
- B905：加 `strict=True`（若语义需要严格对齐，spec 默认可用 `strict=True`）
- E741：变量名改清晰命名（`l` → `line`，`O` → `obj`，`I` → `idx`）
- N806：函数内全大写变量改小写
- SIM117：合并 `with` 语句
- UP046：使用 PEP 695 泛型语法 `class Repository[T]:`（注意 Python >= 3.12，本项目 requires-python=">=3.12"，已满足）

### Step 4.3: 验证 Task 4

```bash
cd packages/server-python
.venv/bin/python -m ruff check --select SIM,B007,B905,E741,N806,UP046 app/ tests/
echo "exit=$?"
```

期望: 退出码 0。

---

## Task 5: 端到端 ruff + pytest 验证

**目标:** 全量 ruff 退出码 0；pytest 不引入新失败。

### Step 5.1: 全量 ruff 退出码验证

```bash
cd packages/server-python
.venv/bin/python -m ruff check app/ tests/
echo "exit=$?"
```

期望: 退出码 0，无错误报告。

### Step 5.2: pytest 回归

```bash
cd packages/server-python
.venv/bin/python -m pytest -q 2>&1 | tail -30
echo "exit=$?"
```

期望:
- 退出码 0（数据库可用时），所有测试通过
- 若本地 PostgreSQL 不可用，集成测试失败模式应与 TD-001 / TD-002 已记录的失败模式一致（66 个集成测试因 DB 不可用失败），归因到 TD-004
- 若数据库可用：87 passed（与 TD-002-FOLLOWUP 记录的 baseline 一致）

### Step 5.3: 失败归因判断

若 pytest 失败：
- 失败信息显示"connection refused" / "asyncpg" / "postgresql" → 归因 TD-004（数据库环境可复现），不阻塞本任务
- 失败信息显示具体 Python 错误（ImportError、AttributeError、TypeError 等）→ 立即停止并回查：本次 ruff 修复是否引入了语义变更？若是，定位 diff 并修复。

### Step 5.4: 确认 ruff 报告"无 fixable"

```bash
cd packages/server-python
.venv/bin/python -m ruff check app/ tests/ 2>&1 | tail -3
```

期望: 末尾没有 `[*] N fixable with the --fix option`（若仍有，重复 Task 1 步骤）。

---

## Task 6: 状态同步（technical-debt.md + current-work.md）

**Files:**
- Modify: `docs/03-engineering-governance/technical-debt.md`（TD-012 卡片）
- Modify: `docs/03-engineering-governance/current-work.md`（新增任务卡片 + 移除候选列表中的 TD-012）

### Step 6.1: 更新 technical-debt.md 中的 TD-012

把 TD-012 卡片：

```md
### TD-012: 治理后端全量 ruff 质量门禁

状态：⚫ 待办
```

改为：

```md
### TD-012: 治理后端全量 ruff 质量门禁

状态：🟢 完成
优先级：P1
领域：后端 / 测试 / 交付
证据：（保留原证据）
问题：（保留原问题）
完成标准：（保留原完成标准）
验证方式：（保留原验证方式）
备注：2026-06-04 按流程开始处理。2026-06-04 完成。PR #XX，merge commit `<hash>`。改动：spec 落盘到 docs/90-compat-legacy/superpowers/specs/2026-06-04-ruff-quality-gate-design.md；自动修复 14 个 F401/I001；手工修复 X 个 E501 / 17 个 B008 / X 个其它规则。验证：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0；`cd packages/server-python && .venv/bin/python -m pytest -q` 87 passed（或 DB 不可用，归因 TD-004）。
```

具体数字（X）由实施时实际命中数填入。

### Step 6.2: 在 current-work.md 登记任务卡片

在"最近完成"区（按时间倒序）新增任务卡片：

```md
### TD-012: 治理后端全量 ruff 质量门禁

状态：🟢 完成
类型：技术债
领域：Backend / Testing / Delivery
当前执行模式：plan-do
最近接手工具：Claude Code
分支：`refactor/td-012-ruff-quality-gate`

需求来源：
- Spec: `docs/90-compat-legacy/superpowers/specs/2026-06-04-ruff-quality-gate-design.md`
- Plan: `docs/90-compat-legacy/superpowers/plans/2026-06-04-ruff-quality-gate.md`
- 技术债：`docs/03-engineering-governance/technical-debt.md#td-012-治理后端全量-ruff-质量门禁`
- 架构约束：`docs/03-engineering-governance/01-rules/quality-gates.md`，`docs/03-engineering-governance/01-rules/git-workflow.md`

当前进展：
- 已完成：spec 落盘并通过 self-review 与用户复核；按 plan 推进 Task 1-5；ruff 退出码 0；pytest 通过/归因；状态同步。
- 正在处理：
- 未完成：

下一步：
1. 由 Codex 复核流程执行情况。

验证状态：
- 已运行：`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0；`cd packages/server-python && .venv/bin/python -m pytest -q`（按实际结果记录）。
- 未运行：
- 当前失败：无。

交接备注：
- PR #XX，merge commit `<hash>`，完成日期 2026-06-04。
```

并从"下一批候选任务"区移除 `TD-012`。

### Step 6.3: 回读验证

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git diff docs/03-engineering-governance/technical-debt.md docs/03-engineering-governance/current-work.md
```

复核：状态、验证结果、PR 链接、merge commit 是否与实际一致。

---

## Task 7: Git 交付（branch + commit + push + PR + merge）

**Files:** 当前任务分支上所有未提交变更。

### Step 7.1: 提交前最终回查

按 `docs/03-engineering-governance/01-rules/git-workflow.md` 提交前检查执行：

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git status --short
```

期望:
- 仅包含本任务文件：`packages/server-python/`、`docs/90-compat-legacy/superpowers/specs/2026-06-04-ruff-quality-gate-design.md`、`docs/90-compat-legacy/superpowers/plans/2026-06-04-ruff-quality-gate.md`、`docs/03-engineering-governance/technical-debt.md`、`docs/03-engineering-governance/current-work.md`
- 不包含 `outputs/`、`.venv/`、未跟踪生成物、其它人/任务的改动

```bash
cd packages/server-python
.venv/bin/python -m ruff check app/ tests/
.venv/bin/python -m pytest -q 2>&1 | tail -5
```

期望: ruff 退出码 0；pytest 与 Task 5.2 一致。

回读 `docs/03-engineering-governance/current-work.md` 与 `docs/03-engineering-governance/technical-debt.md`，确认状态、验证结果与上述命令输出一致。

### Step 7.2: 暂存与提交

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/ \
        docs/90-compat-legacy/superpowers/specs/2026-06-04-ruff-quality-gate-design.md \
        docs/90-compat-legacy/superpowers/plans/2026-06-04-ruff-quality-gate.md \
        docs/03-engineering-governance/technical-debt.md \
        docs/03-engineering-governance/current-work.md
git status --short
```

期望: 暂存列表与 Step 7.1 期望一致。

```bash
git commit -m "refactor(server): clear backend ruff quality gate (TD-012)

- auto-fix 14 ruff --fix items (F401, I001)
- manually fix 107 E501 (line-too-long) across app/ and tests/
- migrate 17 B008 FastAPI Depends/File defaults to Annotated[...]
- fix 1 SIM105, 1 SIM117, 1 B007, 1 B905, 1 E741, 1 N806, 1 UP046
- bundle design spec (docs/90-compat-legacy/superpowers/specs/) and plan

Spec: docs/90-compat-legacy/superpowers/specs/2026-06-04-ruff-quality-gate-design.md
Plan: docs/90-compat-legacy/superpowers/plans/2026-06-04-ruff-quality-gate.md
Zero business-logic change; ruff rule set unchanged; mypy out of scope."
```

期望: 1 个 commit，`git log -1` 标题与正文符合 Conventional Commits。

### Step 7.3: 推送与创建 PR

```bash
git push -u origin refactor/td-012-ruff-quality-gate
gh pr create \
  --title "refactor(server): clear backend ruff quality gate (TD-012)" \
  --body "## Summary
- 让 \`ruff check app/ tests/\` 退出码为 0
- 修复 148 个 ruff 错误：自动修复 14 + E501 折行 107 + B008 改写 17 + 其它规则 8
- 零业务逻辑变更；不改 ruff 规则集；不动 mypy

## Validation
- \`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/\` 退出码 0
- \`cd packages/server-python && .venv/bin/python -m pytest -q\` <按实际结果>

## Risks
- E501 折行已在 PR 内逐行核对原表达式语义
- B008 改写为 Annotated[...] 是 FastAPI 官方推荐写法，向后兼容
- PR 体积大（148 处），建议 review 时聚焦：(1) celery_app.py docstring 改写、(2) Annotated 迁移、(3) E501 折行的表达式连续性

## Docs
- docs/90-compat-legacy/superpowers/specs/2026-06-04-ruff-quality-gate-design.md（设计）
- docs/90-compat-legacy/superpowers/plans/2026-06-04-ruff-quality-gate.md（实施计划）
- docs/03-engineering-governance/technical-debt.md TD-012 状态更新
- docs/03-engineering-governance/current-work.md 任务卡片登记"
```

记录 PR 链接到 `docs/03-engineering-governance/current-work.md` 与 `docs/03-engineering-governance/technical-debt.md` 的任务卡片。

### Step 7.4: 等待检查与合并

```bash
gh pr checks
gh pr view --json state,mergeable,reviewDecision
```

期望: reviewDecision 通过，mergeable=true。

```bash
gh pr merge --squash --delete-branch
```

### Step 7.5: 合并后确认

```bash
git fetch origin
git checkout main
git pull --ff-only
gh pr view --json state,mergeCommit
```

期望: PR 状态 MERGED；本地 main 包含 merge commit。

记录 merge commit hash 到 `docs/03-engineering-governance/technical-debt.md` 与 `docs/03-engineering-governance/current-work.md`。

### Step 7.6: 最终回复

按 `docs/03-engineering-governance/01-rules/git-workflow.md` 第 5 节，最终回复必须明确说明：
- 当前停在"已合并到 main"
- 验证命令与结果（ruff 退出码 0、pytest 结果）
- PR 链接与 merge commit
- 任何剩余风险（mypy 状态、pytest 在无 DB 环境失败归因 TD-004）

---

## 自查清单（Self-Review）

- [x] **Spec 覆盖:** spec 步骤 1-6 分别对应 Task 1 / Task 2 / Task 3 / Task 4 / Task 5（步骤 6 验证在 Task 5 完成）；spec "交付" 段对应 Task 6 + Task 7；spec "风险" 段各项已在对应 Task 的 Step 中给出规避路径。
- [x] **占位符扫描:** 无 TBD / TODO / "类似 Task N"；每个 Step 含具体命令、文件路径、期望输出。
- [x] **类型一致性:** 全文一致使用 `Annotated[..., Depends(...)]`；`class Repository[T]:` PEP 695 语法；`contextlib.suppress`；`zip(..., strict=True)`；未引入未声明的类型、函数、模块。
- [x] **commit 频率:** 用户已确认 1 个 commit；Task 内部按 layer 推进，错误可按 layer 回退。
- [x] **TDD 适配:** 本任务为纯静态检查治理，无新增业务逻辑；TDD 模板不直接适用，以 ruff 退出码 0 + pytest 回归作为等价"测试通过"信号。

## 范围外（明确不做）

- mypy 治理（spec 明确）
- ruff 规则集调整（spec 明确）
- 业务函数体重构、注释刷新、死代码清理
- 自动修复在 diff 中误改业务代码时的人工重构（仅回退该文件，按 spec 改写）
