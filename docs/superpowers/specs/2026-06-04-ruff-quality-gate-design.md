# TD-012: 治理后端全量 ruff 质量门禁 — Design

日期：2026-06-04
来源：`docs/engineering/technical-debt.md#td-012-治理后端全量-ruff-质量门禁`
状态：设计已确认，待进入实施计划

## 目标

让 `packages/server-python` 的后端全量 ruff 检查退出码为 0，并以此为稳定的质量门禁。

完成标准（来自技术债定义）：

> 后端全量 ruff 门禁可运行并退出码为 0，或者仓库明确收敛规则范围并文档化暂缓项。

本次明确选择**第一个分支**：使 `ruff check app/ tests/` 退出码为 0。

## 范围

- 改动面：`packages/server-python/app/` 与 `packages/server-python/tests/` 下所有被 ruff 规则命中的文件。
- 不动 `packages/server-python/pyproject.toml` 中 `[tool.ruff]` / `[tool.ruff.lint]` 的规则集与 `line-length`。
- 不动 `Makefile` 中 `lint` 目标里的 `mypy app/` 段（避免与本次治理范围混杂；mypy 不属于本任务）。
- 不顺手清理与 ruff 无关的死代码、注释、格式。
- 不改动任何业务函数体语义：折行必须保持原表达式求值结果一致；自动修复（`--fix`）必须只命中 import 排序、未使用 import、I001 等纯结构性项。

## 现状（2026-06-04 勘测）

`cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 报告 **148 个错误**，按规则分布：

| 规则 | 数量 | 说明 |
|------|------|------|
| E501 `line-too-long` | 107 | 72%，是本次主工作量 |
| B008 `function-call-in-default-argument` | 17 | 多为 FastAPI `Depends` 等常见模式 |
| F401 `unused-import` | 11 | 14 个可自动修复（其中 3 个需 `--unsafe-fixes`） |
| I001 `unsorted-imports` | 3 | 可自动修复 |
| E402 `module-import-not-at-top-of-file` | 2 | 需人工确认（多为 `celery_app.py` 内注释后导入） |
| SIM105 `suppressible-exception` | 2 | contextlib.suppress 替换 |
| B007 `unused-loop-control-variable` | 1 | `_` 命名 |
| B905 `zip-without-explicit-strict` | 1 | 加 `strict=` |
| E741 `ambiguous-variable-name` | 1 | `l` / `O` / `I` 之类 |
| N806 `non-lowercase-variable-in-function` | 1 | 全大写变量 |
| SIM117 `multiple-with-statements` | 1 | 合并 `with` |
| UP046 `non-pep695-generic-class` | 1 | PEP 695 泛型语法 |

注：技术债中记录的 "162 个" 与现状 148 的差额来自 TD-002 / TD-002-FOLLOWUP 已治理的部分行。

## 实施方式

### 步骤 1：自动修复层

执行 `ruff check --fix app/ tests/`，处理 14 个可自动修复项（含 I001、F401）。

### 步骤 2：必要时 unsafe 修复

对剩余 F401 但需 `--unsafe-fixes` 的 3 个项目，先逐项人工阅读 diff，确认仅删除未使用 import 后再执行 `--fix --unsafe-fixes`。任何不确定的项回退到人工处理。

### 步骤 3：手工修复 E501（107 处）

E501 折行原则：

- **表达式折行**：在二元运算符、函数调用、集合字面量、关键字参数后换行，使用括号或反斜杠隐式续行；避免破坏现有字符串字面量。
- **长字符串字面量**：不可拆的 SQL / 文件名 / MIME / 长 fixture data 等长字符串行，优先尝试用 Python 隐式字符串拼接或变量绑定拆行；若仍不可拆，标注 `# noqa: E501` 并在该行上方一行写明原因（"long fixture data"、"MIME constant" 等）。不使用缩短变量名绕过长度限制。
- **类型注解 / Pydantic Field**：跨字段的继承或泛型可用括号续行。
- **测试文件**：长 fixture / 长参数表同样按上述原则处理。

不使用缩短变量名绕过长度限制。`# noqa: E501` 仅在字符串确实不可拆时使用，且必须带理由注释。

### 步骤 4：手工修复 B008（17 处）

B008 默认参数函数调用在 FastAPI 中典型为 `Depends(get_db)`。该用法在 `ruff` 默认配置下被 B008 标记，但属于框架惯用模式。两种处理：

- 若为 FastAPI `Depends(...)`、`Security(...)`、`Header(...)` 等框架惯用：在表达式前加 `from __future__ import annotations` 或显式 `Annotated[..., Depends(...)]` 替代后，B008 自动消失（首选）。
- 若为业务侧真实 bug（如 `datetime.now()` 默认参数）：按 ruff 建议移到函数体内。

不在 `pyproject.toml` 中添加 `flake8-bugbear.extend-immutable-calls`，避免通过放宽规则让数字变好看。

### 步骤 5：E402 / SIM / B / UP 系列（少量）

- E402（2）：`celery_app.py` 中在模块说明性注释后再 `import` 触发的 E402。处理方式为把那段说明性 `# ...` 注释改写为模块顶部 docstring（`"""..."""`）或普通字符串字面量，使 E402 命中点不再出现；不静默使用 `# noqa: E402`。
- SIM105 / SIM117：使用 `contextlib.suppress` 与合并 `with` 改写。
- B007：循环控制变量改为 `_`。
- B905：`zip(...)` 改为 `zip(..., strict=...)`。
- E741 / N806：重命名变量。
- UP046：迁移到 PEP 695 泛型语法（`class Foo[T]:`）。

### 步骤 6：再次全量验证

```bash
cd packages/server-python && .venv/bin/python -m ruff check app/ tests/
```

退出码必须为 0。

## 测试

ruff 修复属于纯静态层调整，理论上不影响行为，但仍需回归：

```bash
cd packages/server-python && .venv/bin/python -m pytest -q
```

预期 87 passed（或在执行步骤 1/2 期间未引入回归时保持一致）。若数据库不可用导致集成测试失败，沿用 TD-001 / TD-002 已记录的失败模式归因到 TD-004，不计入本任务失败项。

## 风险

- **E501 折行误改语义**：在链式调用、生成器表达式、上下文管理器中折行可能改变 `import` 顺序或闭合括号位置。每处折行需肉眼对照原表达式。
- **B008 误改**：误把 `Depends` 移除导致运行时错误。修复前对每个 B008 命中点确认是否为框架惯用。
- **F401 自动修复误删**：被动态 import 的模块（`importlib.import_module`）可能因未直接使用而被误删；步骤 2 必须先阅读 diff。
- **PR 体积大**：148 处改动集中在一个 commit。提交信息需明确范围；commit message 引用 `TD-012` 与本次"纯静态修复，零行为变更"声明，便于 review。

## 交付

- 1 个 commit，1 个 PR 合并到 `main`。
- 同步更新 `docs/engineering/technical-debt.md` 中 `TD-012` 状态为 `🟢 完成`，记录完成日期、commit hash 与 PR 链接。
- 同步更新 `docs/engineering/current-work.md` 任务卡片，写明验证结果。

## 不在范围

- mypy 治理（`Makefile` 中 `lint: ruff + mypy` 仍可能因 mypy 失败；本次只保证 ruff 退出码 0；mypy 状态以本次跑出来的结果如实记录，不强行修复）。
- ruff 规则集调整（不放宽规则、不加 per-file-ignore）。
- 任何与 ruff 无关的代码清理、注释刷新、函数重构。
