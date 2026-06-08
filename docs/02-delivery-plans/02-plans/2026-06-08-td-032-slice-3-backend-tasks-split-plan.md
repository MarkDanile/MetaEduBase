# TD-032 切片 3 拆分 `document/tasks.py`（929 行）+ `structured_data/tasks.py`（671 行）— Plan

## 任务入口

- Spec: `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-3-backend-tasks-split.md`
- 技术债: `docs/03-engineering-governance/technical-debt.md#td-032-治理超大源码文件并建立文件规模拆分原则`
- 任务卡片: `docs/03-engineering-governance/current-work.md` 的 TD-032 卡片
- 当前执行模式: `plan-do`（纯重构、行为零变化、跨 ~14 个新文件已 spec 覆盖）
- 分支: `refactor/td-032-slice-3-backend-tasks`（已从最新 `main` 切出）
- 完成后 Git 阶段: 提交 → push → PR → 合并 `main`（按 `docs/03-engineering-governance/01-rules/git-workflow.md#快速交付通道`）

## 实施顺序

### 1. 探针：单文件 → 包转换的 import 兼容性

- [ ] 临时建 `app/contexts/document/application/tasks/` 空目录 + 空 `__init__.py`。
- [ ] 临时建 `app/contexts/structured_data/application/tasks/` 空目录 + 空 `__init__.py`。
- [ ] 临时把原 `tasks.py` 移到 `tasks.py.bak`（不删，先备份）。
- [ ] 跑：

  ```bash
  .venv/bin/python -c "from app.contexts.document.application.tasks import parse_document; print('OK')"
  .venv/bin/python -c "from app.contexts.structured_data.application.tasks import ds_parse; print('OK')"
  ```

- [ ] 两行都 OK → 探针通过，方案可行；`tasks.py.bak` 仍可作为拆分对照；进入 §2。
- [ ] 若失败 → 排查 Python path 是否有 `__init__.py` 冲突；恢复 `tasks.py` 后再尝试。

**验证点**：`from app.contexts.X.application.tasks import Y` 解析到原 `tasks.py.bak` 的同名符号，OK。

### 2. 风险 2 提前验证：局部 import 必须保持位置

- [ ] 全文 grep 任务文件中的**函数内** `import`（不在模块顶部）：

  ```bash
  rg -n "^\s+import |^\s+from " packages/server-python/app/contexts/document/application/tasks.py
  rg -n "^\s+import |^\s+from " packages/server-python/app/contexts/structured_data/application/tasks.py
  ```

- [ ] 把每条局部 `import` 标到对应 task 子文件（plan §3 实施步骤里逐条核对）。
- [ ] 规则：**所有函数内 `import` 保持原位**（不提升到模块顶部），避免循环 import。

**验证点**：grep 命中行号在 plan §3 每个 task 子文件里**仍能命中**相同函数内位置。

### 3. 按 spec §1 + §2 拆出 14 个新文件

按"document 先、structured_data 后"顺序拆。**每拆一个文件，立刻跑该文件相关的聚焦测试**，避免批量提交失败时难定位。

#### 3.1 document 任务包

- [ ] **3.1.1** 建 `tasks/` 空包：

  ```bash
  mkdir -p app/contexts/document/application/tasks
  touch app/contexts/document/application/tasks/__init__.py
  ```

- [ ] **3.1.2** 写 `tasks/pipeline_guard.py`：迁 `_pipeline_version_key` + `_check_pipeline_stale`（行 37-71）。
- [ ] **3.1.3** 写 `tasks/extract_template_prompts.py`：迁 `_build_parsed_structured_data`（74-76）+ `_merge_template_structured_data`（79-96）+ `build_fields_desc`（649-668 嵌套函数）+ `try_parse`（700-717 嵌套函数）。
- [ ] **3.1.4** 写 `tasks/parse.py`：`parse_document` 整体迁入（行 99-208）。`from .pipeline_guard import _check_pipeline_stale`、`from .extract_template_prompts import _build_parsed_structured_data`。
- [ ] **3.1.5** 写 `tasks/chunk.py`：`chunk_document`（行 214-346）。所有 `import re` / `from app.shared.parsing.xxx` 保持原位（行 263、255、256）。
- [ ] **3.1.6** 写 `tasks/embed.py`：`embed_chunks`（行 352-468）。`import httpx`（385）保持原位。
- [ ] **3.1.7** 写 `tasks/index.py`：`index_tsvector`（行 474-542）。
- [ ] **3.1.8** 写 `tasks/extract_template.py`：`extract_template`（行 548-772）。`from app.contexts.document.application.template_selector import select_template`（586）保持原位（局部 import）。`from .extract_template_prompts import build_fields_desc, try_parse, _merge_template_structured_data`。
- [ ] **3.1.9** 写 `tasks/extract_knowledge_graph.py`：`extract_knowledge_graph`（行 778-929）。`find_node_id`（875-887 嵌套函数）保持在 `extract_knowledge_graph` 函数内（不抽到模块级）。
- [ ] **3.1.10** 写 `tasks/__init__.py`：re-export 6 个 task 名字（spec §1 草案）。
- [ ] **3.1.11** 删除原 `app/contexts/document/application/tasks.py`。

#### 3.2 structured_data 任务包

- [ ] **3.2.1** 建 `tasks/` 空包：

  ```bash
  mkdir -p app/contexts/structured_data/application/tasks
  touch app/contexts/structured_data/application/tasks/__init__.py
  ```

- [ ] **3.2.2** 写 `tasks/ds_parse.py`：`ds_parse` 整体迁入（行 34-124）。`from app.shared.parsing.xlsx_parser import extract_xlsx_rows`（62）保持原位。
- [ ] **3.2.3** 写 `tasks/ds_embed.py`：`ds_embed`（行 130-253）。`import httpx`（164）保持原位。
- [ ] **3.2.4** 写 `tasks/ds_extract_kg.py`：`ds_extract_kg`（行 259-514）。`parse_kg_json`（336-351 嵌套函数）保持在 `ds_extract_kg` 函数内（不抽到模块级）。`from app.contexts.knowledge.application.embedding_service import get_embedding`（413）保持原位（局部 import）。`import httpx`（312）保持原位。
- [ ] **3.2.5** 写 `tasks/ds_cross_dataset_edges.py`：`ds_build_cross_dataset_edges`（行 539-671）。`_extract_entity_name`（520-522） + `_extract_fk_reference`（525-536）保持模块级 helper。
- [ ] **3.2.6** 写 `tasks/__init__.py`：re-export 4 个 task 名字。
- [ ] **3.2.7** 删除原 `app/contexts/structured_data/application/tasks.py`。

### 4. 验证

- [ ] **4.1** 文档门禁：`scripts/check-engineering-docs` 退出码 0。
- [ ] **4.2** Import 探针：

  ```bash
  .venv/bin/python -c "
  from app.contexts.document.application.tasks import (
      parse_document, chunk_document, embed_chunks,
      index_tsvector, extract_template, extract_knowledge_graph,
  )
  from app.contexts.structured_data.application.tasks import (
      ds_parse, ds_embed, ds_extract_kg, ds_build_cross_dataset_edges,
  )
  print('all 10 tasks import OK')
  "
  ```

- [ ] **4.3** 外部 import 兼容性探针（必须仍可解析）：

  ```bash
  .venv/bin/python -c "from app.contexts.document.application.tasks import parse_document, chunk_document, embed_chunks, extract_knowledge_graph, extract_template, index_tsvector; print('router-1 OK')"
  .venv/bin/python -c "from app.contexts.structured_data.application.tasks import ds_parse; print('router-2 OK')"
  .venv/bin/python -c "from app.contexts.structured_data.application.tasks import ds_extract_kg; print('task_router OK')"
  .venv/bin/python -c "from app.contexts.document.application.tasks import (parse_document, chunk_document, embed_chunks, extract_knowledge_graph, extract_template, index_tsvector); print('autodiscover proxy OK')"
  .venv/bin/python -c "from app.contexts.structured_data.application.tasks import (ds_parse, ds_embed, ds_extract_kg, ds_build_cross_dataset_edges); print('autodiscover proxy OK')"
  ```

- [ ] **4.4** 聚焦测试：

  ```bash
  cd packages/server-python
  .venv/bin/python -m pytest tests/shared/test_task_lifecycle.py -v
  .venv/bin/python -m pytest tests/contexts/document/ -v
  .venv/bin/python -m pytest tests/contexts/structured_data/ -v
  ```

- [ ] **4.5** 全量测试（依赖 `metaedu_test`）：

  ```bash
  .venv/bin/python -m pytest -q
  ```

  - 沙箱可达 → 通过；
  - 沙箱不可达 → 标 `未运行` 并记录原因（`quality-gates.md#验证表述规范`）。

- [ ] **4.6** ruff：

  ```bash
  .venv/bin/python -m ruff check app/ tests/
  ```

- [ ] **4.7** 行数核对：

  ```bash
  wc -l \
    app/contexts/document/application/tasks/*.py \
    app/contexts/structured_data/application/tasks/*.py
  ```

  - 期望：document `__init__.py` ≤30 行；每个 task 子文件 70-160 行。
  - 期望：structured_data `__init__.py` ≤30 行；每个 task 子文件 95-210 行。

- [ ] **4.8** `git diff --name-status` 仅包含 spec / plan / current-work + 新 tasks/ 包 + 删除旧 tasks.py。无业务代码改动（router / lifecycle / llm / tests 全部不动）。

### 5. Git 闭环

- [ ] 同步 `docs/03-engineering-governance/current-work.md` 任务卡（TD-032 切片 3 收口）。
- [ ] 暂存相关文件（`git add app/contexts/{document,structured_data}/application/tasks/`，**注意删除旧 `tasks.py`**：`git add -A app/contexts/.../application/tasks.py` 标记删除）。
- [ ] 提交：`refactor(server): split document/structured_data tasks into focused modules`。
- [ ] push：`git push -u origin refactor/td-032-slice-3-backend-tasks`。
- [ ] PR：`gh pr create --title "refactor(server): TD-032 slice 3 — split document + structured_data tasks" --body "..."`，body 含 Summary / Scope / Validation / Risks / Docs。
- [ ] `gh pr view --json state,mergeable,reviewDecision` 确认 `MERGEABLE`；`gh pr checks` 查 CI（本仓库 gate 走本地 `scripts/check-engineering-docs` + pytest，与切片 1-2 一致；PR 未配置 CI）。
- [ ] squash merge：`gh pr merge --squash --delete-branch`。
- [ ] 合并后回写：
  - `docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md`：`document/tasks.py` 与 `structured_data/tasks.py` 状态 `⚪ 待切片` → `🟢 已拆分` + 新行数（实测）+ 拆出去向。
  - `docs/03-engineering-governance/technical-debt.md#td-032`：备注追加「切片 3 已合并」+ PR 链接。
  - `docs/03-engineering-governance/work-log.md`：新增 1 行索引。
  - `docs/03-engineering-governance/current-work.md`：TD-032 任务卡「下一步」改为「切片 4 单独 spec / plan」。
  - 上述 docs-only 回写合并到 1 个原子 backfill commit。

## 任务拆分（按 plan-do 步骤）

1. 风险 1 + 2 探针（§1 + §2，10 分钟）
2. document tasks 包（§3.1，10 个文件，主拆工作量）
3. structured_data tasks 包（§3.2，5 个文件）
4. 验证（§4，import + 聚焦测试 + ruff + 行数）
5. 走完整 Git 流程
6. 合并后回写 4 处 docs

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 单文件 → 包转换时 `__init__.py` 缺漏或循环 import | §1 探针先建空包验证 import 兼容性 |
| 函数内 `import` 被错提升到模块顶部，引入循环 | §2 grep 标位置 + §3 实施时逐条核对；不主动 refactor import 位置 |
| `extract_template` / `extract_knowledge_graph` 内联 helper 抽离时改变可观察行为 | helpers 抽到独立文件但实现 byte-equivalent；嵌套函数变模块级函数对调用者无影响 |
| `app/contexts/document/tasks.py` 与 `app/contexts/structured_data/tasks.py`（Celery autodiscover 代理）被误改 | spec §3 已明确"不动"；plan §3 不包含这两个文件的步骤 |
| 沙箱无 `metaedu_test`，全量 pytest 失败 | §4.5 标 `未运行` + 记录原因；聚焦测试 + ruff 已覆盖核心行为 |
| `extract_template_prompts.py` 拆出后成为新超大文件候选 | 预期 ~110 行，远低于 ≤500 原则；不预防性再拆 |

## 提交前最终回查（按 `docs/03-engineering-governance/task-modes.md#通用收尾回查`）

- [ ] `current-work.md` 任务卡与代码实际状态一致。
- [ ] `technical-debt.md` 任务卡状态与代码实际状态一致。
- [ ] `scripts/check-engineering-docs` 退出码 0。
- [ ] 6 个聚焦 pytest 文件全部通过；全量 pytest 沙箱不可达时标 `未运行`。
- [ ] `ruff check app/ tests/` 退出码 0。
- [ ] 业务行为不变声明写到 PR 描述 + 本文件。
- [ ] `git diff --name-status` 只包含本任务文件（tasks 包 + spec/plan + current-work）；无业务代码、无生成物。
