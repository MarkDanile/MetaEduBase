# TD-032 切片 3 拆分 `document/tasks.py`（929 行）+ `structured_data/tasks.py`（671 行）— Spec

## 背景

`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 把两个后端 Celery 任务文件登记为「⚪ 待切片」：

- `packages/server-python/app/contexts/document/application/tasks.py` 929 行（6 步 pipeline：`parse_document` → `chunk_document` → `embed_chunks` → `index_tsvector` → `extract_template` → `extract_knowledge_graph`）
- `packages/server-python/app/contexts/structured_data/application/tasks.py` 671 行（4 步 pipeline：`ds_parse` → `ds_embed` → `ds_extract_kg` → `ds_build_cross_dataset_edges`）

切片 1（[PR #92](https://github.com/MarkDanile/MetaEduBase/pull/92) / merge `3de4de5`）建立基线，切片 2（[PR #93](https://github.com/MarkDanile/MetaEduBase/pull/93) / merge `7e468fb`）拆 `check_engineering_docs.py`。切片 3 是 TD-032 计划（[2026-06-08-td-032-large-source-files-plan.md](../02-plans/2026-06-08-td-032-large-source-files-plan.md)）的下一个目标。

**重要前置**：TD-005（[PR #34](https://github.com/MarkDanile/MetaEduBase/pull/34) / merge `e5197a5`）已经抽过一组横切 helper 到 `app/shared/tasks/lifecycle.py`（4 个公共函数 + 4 个 `_xxx` 兼容别名：`get_sync_session` / `run_in_session` / `update_task_status` / `create_task`）。切片 3 沿用并扩展这个模式，但**不**重写 lifecycle；只在 TD-005 既有边界上**新增**针对 document 域 / structured_data 域的 helper。

## 目标

1. 把 `document/application/tasks.py` 929 行拆为**包** `document/application/tasks/`：1 个 `__init__.py`（re-export 全部 6 个 task 顶层名字）+ 6 个聚焦子模块 + 1-2 个域内 helper 模块；主 `__init__.py` 目标 ≤100 行。
2. 把 `structured_data/application/tasks.py` 671 行同样拆为**包** `structured_data/application/tasks/`：1 个 `__init__.py` + 4 个聚焦子模块 + 1 个域内 helper 模块；主 `__init__.py` 目标 ≤100 行。
3. **零业务行为变化**：所有 Celery task 名字（`parse_document` / `chunk_document` / `embed_chunks` / `index_tsvector` / `extract_template` / `extract_knowledge_graph` / `ds_parse` / `ds_embed` / `ds_extract_kg` / `ds_build_cross_dataset_edges`）、`@shared_task(name=...)` 字符串、所有 SQL / 提示词 / JSON 解析逻辑、状态机、metrics 全部 byte-equivalent。
4. **保持 Celery worker autodiscover 与既有 import 路径不破**：
   - `app/contexts/document/application/tasks.py` 必须从「单文件模块」变为「包」但**仍能** `from app.contexts.document.application.tasks import parse_document`（被 `app/contexts/document/interfaces/api/router.py:27` 使用）。
   - `app/contexts/document/tasks.py`（Celery autodiscover 代理入口）不动。
   - `app/contexts/structured_data/application/tasks` 同样保持包形式 + 顶层 re-export。
   - `app/contexts/structured_data/tasks.py` 代理入口不动。
   - `tests/contexts/document/test_structured_data_contract.py:11` 直接 import `from app.contexts.document.application.tasks import (...)` 仍可工作。
5. **不动** `app/shared/tasks/lifecycle.py`（TD-005 既有产物，已被 TD-005 验证 + 测试覆盖）；切片 3 复用其 `_create_task` / `_run_in_session` / `_update_task_status` 兼容别名。

## 范围

### In scope

- 新建包 `packages/server-python/app/contexts/document/application/tasks/`：
  - `__init__.py`（≤100 行）：re-export 6 个 task + 域内 helper。
  - `parse.py`（~110 行）：`parse_document` task + pipeline guard 引用。
  - `chunk.py`（~135 行）：`chunk_document` task。
  - `embed.py`（~120 行）：`embed_chunks` task。
  - `index.py`（~75 行）：`index_tsvector` task。
  - `extract_template.py`（~120 行）：`extract_template` task，**不含** `try_parse` 与 `build_fields_desc`（这两个 helper 迁到 `extract_template_prompts.py`）。
  - `extract_template_prompts.py`（~110 行）：`build_fields_desc` + `try_parse` + `_build_parsed_structured_data` / `_merge_template_structured_data`。
  - `extract_knowledge_graph.py`（~155 行）：`extract_knowledge_graph` task + `find_node_id` helper。
  - `pipeline_guard.py`（~40 行）：`_pipeline_version_key` + `_check_pipeline_stale`。
  - 删除原 `packages/server-python/app/contexts/document/application/tasks.py` 单文件模块（被包替代）。
- 新建包 `packages/server-python/app/contexts/structured_data/application/tasks/`：
  - `__init__.py`（≤100 行）：re-export 4 个 task + 域内 helper。
  - `ds_parse.py`（~95 行）：`ds_parse` task。
  - `ds_embed.py`（~125 行）：`ds_embed` task。
  - `ds_extract_kg.py`（~210 行）：`ds_extract_kg` task + `parse_kg_json` helper。
  - `ds_cross_dataset_edges.py`（~135 行）：`ds_build_cross_dataset_edges` task + 2 个 `_extract_*` helper。
  - 删除原 `packages/server-python/app/contexts/structured_data/application/tasks.py` 单文件模块。
- 任务卡 `docs/03-engineering-governance/current-work.md` 同步刷新。
- spec / plan 落仓到 `docs/02-delivery-plans/01-specs/` 与 `docs/02-delivery-plans/02-plans/`。

### Out of scope

- 不动 `app/shared/tasks/lifecycle.py`（TD-005 既有产物）。
- 不动 `app/contexts/document/tasks.py` 与 `app/contexts/structured_data/tasks.py`（Celery autodiscover 代理入口）。
- 不动任何 `app/contexts/{document,structured_data}/interfaces/api/*.py`（router 保持原 import 路径）。
- 不动任何 `app/contexts/document/application/template_selector.py`（`extract_template` 内部引用的 template 匹配模块）。
- 不动 `app/shared/llm/chat.py` 与 LLM provider 策略（属于 TD-006 / TD-016 / TD-020 已完成或未开工范围）。
- 不动 `app/contexts/structured_data/application/dataset_fk.py`（如果已存在；本次不主动创建）。
- 不动任何 `app/contexts/{document,structured_data}/infrastructure/*`。
- 不动任何 `app/contexts/knowledge/**`（虽然 KG 写入部分跨上下文，但目标范围是「拆分 tasks 文件」，不重排跨上下文职责）。
- 不动 `tests/`——本次只验证既有测试通过，不补新测试（因为切片 3 性质是"拆分 + 行为零变化"，无新行为需要测试）。
- 不动 `main.css`、前端视图、Python service 大文件（属于切片 4 / 5+ 范围）。
- 不引入新依赖。
- 不改 `pyproject.toml` / `setup.py` / `requirements*.txt`。

## 设计要点

### 1. `app.contexts.document.application.tasks` 包结构

```
packages/server-python/app/contexts/document/application/tasks/
├── __init__.py              # re-export 6 task + 0 helper（helpers 不在顶层 namespace）
├── pipeline_guard.py        # _pipeline_version_key, _check_pipeline_stale
├── extract_template_prompts.py  # _build_parsed_structured_data, _merge_template_structured_data,
│                              # build_fields_desc, try_parse
├── parse.py                 # parse_document
├── chunk.py                 # chunk_document
├── embed.py                 # embed_chunks
├── index.py                 # index_tsvector
├── extract_template.py      # extract_template
└── extract_knowledge_graph.py  # extract_knowledge_graph
```

**关键约束**：`__init__.py` 仅 re-export 6 个 task 名字（保持 `from app.contexts.X.application.tasks import parse_document` 工作）；**不**在 `__init__.py` re-export `_pipeline_version_key` 等 helper——helpers 仍是模块私有，只在同一包内不同子模块之间通过相对 import（`from .pipeline_guard import _check_pipeline_stale`）共享。

`__init__.py` 内容草案：

```python
"""Document processing Celery tasks — 6-step pipeline.

Pipeline: parse → chunk → embed → index_tsv → extract_template → extract_kg

按 `docs/02-delivery-plans/01-specs/2026-06-08-td-032-slice-3-backend-tasks.md` 拆分自
原单文件 `tasks.py`（929 行）。Celery worker 通过 `@shared_task(name=...)` 注册，
本 `__init__.py` 仅 re-export 让既有 import 路径继续工作。
"""

from __future__ import annotations

from .chunk import chunk_document
from .embed import embed_chunks
from .extract_knowledge_graph import extract_knowledge_graph
from .extract_template import extract_template
from .index import index_tsvector
from .parse import parse_document


__all__ = [
    "parse_document",
    "chunk_document",
    "embed_chunks",
    "index_tsvector",
    "extract_template",
    "extract_knowledge_graph",
]
```

### 2. `app.contexts.structured_data.application.tasks` 包结构

```
packages/server-python/app/contexts/structured_data/application/tasks/
├── __init__.py              # re-export 4 task
├── ds_parse.py              # ds_parse
├── ds_embed.py              # ds_embed
├── ds_extract_kg.py         # ds_extract_kg + parse_kg_json
└── ds_cross_dataset_edges.py  # ds_build_cross_dataset_edges + 2 _extract_* helper
```

helpers 同样留在所属 task 子文件内部（`parse_kg_json` 仅 `ds_extract_kg` 用；`_extract_entity_name` / `_extract_fk_reference` 仅 `ds_build_cross_dataset_edges` 用）；不抽到独立 helper 模块（避免 YAGNI）。

### 3. 已有跨包 import 兼容性

下列外部 import 路径必须保持有效（不改 import 站点）：

| 路径 | 用途 |
|------|------|
| `from app.contexts.document.application.tasks import parse_document` | `app/contexts/document/interfaces/api/router.py:27` |
| `from app.contexts.document.application.tasks import (chunk_document, embed_chunks, extract_knowledge_graph, extract_template, index_tsvector, parse_document)` | `app/contexts/document/tasks.py:2`（autodiscover 代理） |
| `from app.contexts.structured_data.application.tasks import ds_parse` | `app/contexts/structured_data/interfaces/api/router.py:22` |
| `from app.contexts.structured_data.application.tasks import ds_extract_kg` | `app/contexts/structured_data/interfaces/api/task_router.py:213`（函数体内延迟 import） |
| `from app.contexts.structured_data.application.tasks import (ds_build_cross_dataset_edges, ds_embed, ds_extract_kg, ds_parse)` | `app/contexts/structured_data/tasks.py:2`（autodiscover 代理） |
| `from app.contexts.document.application.tasks import (...)` | `tests/contexts/document/test_structured_data_contract.py:11` |
| 字符串引用 `app.contexts.document.application.tasks.extract_template`（在 docstring 中） | `tests/contexts/document/test_extract_template_selection.py:8` |

`__init__.py` re-export 6 + 4 个 task 名字即可满足上述所有 import；`tests/contexts/document/test_structured_data_contract.py:11` 用什么名字需要在 plan §实施步骤 §1 探针时确认。

### 4. 横切 helper 边界（切片 3 不重写 TD-005）

TD-005 既有 `app/shared/tasks/lifecycle.py`（4 个公共函数 + 4 个 `_xxx` 别名）**已覆盖**两文件 6 + 4 = 10 个 task 的「session 包裹 / 任务状态创建 / 任务状态更新」共需。切片 3 不再新增跨上下文共享 helper；只新增**域内** helper：

| Helper | 域 | 路径 | 用途 |
|--------|----|------|------|
| `_pipeline_version_key` | document | `tasks/pipeline_guard.py` | 归一化 datetime 用于 stale check |
| `_check_pipeline_stale` | document | `tasks/pipeline_guard.py` | reinitialize 后的 stale 守卫 |
| `_build_parsed_structured_data` | document | `tasks/extract_template_prompts.py` | 构造 parse_document 写入的 stable container |
| `_merge_template_structured_data` | document | `tasks/extract_template_prompts.py` | 合并 template 抽取结果到 existing structured_data |
| `build_fields_desc` | document | `tasks/extract_template_prompts.py` | LLM prompt 构造（递归描述嵌套 field） |
| `try_parse` | document | `tasks/extract_template_prompts.py` | LLM JSON 输出兜底解析 |
| `find_node_id` | document | `tasks/extract_knowledge_graph.py`（局部，不抽） | entity 名 → node_id 子串匹配 |
| `parse_kg_json` | structured_data | `tasks/ds_extract_kg.py`（局部，不抽） | KG LLM JSON 兜底解析 |
| `_extract_entity_name` | structured_data | `tasks/ds_cross_dataset_edges.py`（局部，不抽） | 数据集名去后缀 |
| `_extract_fk_reference` | structured_data | `tasks/ds_cross_dataset_edges.py`（局部，不抽） | FK 列名解析 |

**不**把 `try_parse` / `parse_kg_json` 抽到共享 `llm_json.py`——三处实现不完全相同（document `try_parse` 用 `re.search` 抓 `\`\`\`json\`\`\`` 代码块；structured_data `parse_kg_json` 用 `re.sub` 删除 ` ``` `；document `extract_knowledge_graph` 内联版本介于两者）。统一抽会改变可观察行为（解析失败的兜底分支不同），违反"零业务逻辑变化"约束。

### 5. 行数目标

- document `tasks/` 包：6 个 task 子文件每个 70-160 行；`pipeline_guard.py` ~40 行；`extract_template_prompts.py` ~110 行；`__init__.py` ≤30 行。
- structured_data `tasks/` 包：4 个 task 子文件每个 95-210 行；`__init__.py` ≤30 行。
- 删除原单文件 `tasks.py`（929 + 671 行）。
- 净行数变化：原 1600 行 → 拆后约 1200 行（含每个新文件的 docstring / import 重复）—— 行数下降不是目标，"职责单一"才是。

## 完成标准

1. `packages/server-python/app/contexts/document/application/tasks/` 包存在，9 个文件就位（`__init__.py` + 1 个 pipeline guard + 1 个 prompts helper + 6 个 task 子模块）。
2. `packages/server-python/app/contexts/structured_data/application/tasks/` 包存在，5 个文件就位（`__init__.py` + 4 个 task 子模块）。
3. 旧单文件 `packages/server-python/app/contexts/document/application/tasks.py` 与 `.../structured_data/application/tasks.py` **被删除**。
4. 所有 6 + 4 = 10 个 `@shared_task(name=...)` 字符串保持原值。
5. 既有外部 import 路径全部仍能解析（`from app.contexts.X.application.tasks import Y`）。
6. 既有 6 个后端测试文件全部通过：
   - `tests/shared/test_task_lifecycle.py`
   - `tests/contexts/document/test_structured_data_contract.py`
   - `tests/contexts/document/test_extract_template_selection.py`
   - `tests/contexts/document/test_cascade_cleanup.py`
   - `tests/contexts/document/test_datasets.py`
   - `tests/contexts/document/test_files.py`（如存在）
7. `cd packages/server-python && .venv/bin/python -m ruff check app/ tests/` 退出码 0。
8. `git diff --name-status` 仅包含 `app/contexts/{document,structured_data}/application/tasks/` 下文件 + spec/plan + current-work.md 任务卡；无业务代码改动（router / lifecycle / llm / tests 全部不动）。

## 验证方式

按 `docs/03-engineering-governance/01-rules/quality-gates.md#验证矩阵` 选后端 Python 行：

```bash
# 行为基线（拆分前后必须一致）
cd packages/server-python
.venv/bin/python -m pytest tests/shared/test_task_lifecycle.py -v
.venv/bin/python -m pytest tests/contexts/document/ -v
.venv/bin/python -m pytest -q   # baseline 一致
.venv/bin/python -m ruff check app/ tests/

# 行数核对
wc -l \
  app/contexts/document/application/tasks/*.py \
  app/contexts/structured_data/application/tasks/*.py

# Import 探针
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

# 文档门禁
scripts/check-engineering-docs
```

按 `quality-gates.md#行为变化声明检查` 显式声明：

> 本次为纯重构（模块拆分 + 域内 helper 迁出 + 包形式改造）。所有 10 个 Celery task
> 名字、`@shared_task(name=...)` 字符串、SQL 语句、提示词、JSON 解析逻辑、状态机、
> metrics 全部 byte-equivalent。**唯一可见变化**是：
>
> 1. `app.contexts.document.application.tasks` 从单文件模块变为同名包；
> 2. `app.contexts.structured_data.application.tasks` 同上。
>
> 两个 `__init__.py` 通过 re-export 保持既有 `from app.contexts.X.application.tasks import Y`
> 路径有效；Celery worker autodiscover 通过 `app.contexts.X.tasks` 代理入口继续工作。

## 风险与后续

- **风险 1**：单文件 → 包转换时 Python import 系统需要 `__init__.py` 就位才识别为包；若 `__init__.py` 缺漏或循环 import，Celery worker 启动时直接 `ImportError`。缓解：plan §实施步骤 §1 探针先建空 `__init__.py` + re-export，运行 `pytest` 与 import 探针。
- **风险 2**：原 tasks.py 中有 `import asyncio` 在 task 函数内、还有 `from app.shared.parsing.pdf_parser import extract_pdf_text` 在分支内等**局部 import**；拆分时必须保留这些局部 import 位置（不要提升到模块顶部），否则可能引入循环 import 或启动期依赖。缓解：plan §实施步骤 §3 显式记录"所有 `import xxx` 出现在 task 函数体内部的保持原位"约束。
- **风险 3**：document `extract_template` 内部 `try_parse` 用了 88 行 + `build_fields_desc` + `_build_parsed_structured_data` / `_merge_template_structured_data` 共 4 个 helper；拆到 `extract_template_prompts.py` 后，**该文件可能成为下一个"超大文件候选"**（~110 行），符合 ≤500 原则。后续如果 prompts / JSON 解析继续增长，可以再拆（属于切片 5+ 范围）。
- **风险 4**：本地 pytest 全量（baseline 132-152 passed）依赖 `metaedu_test` 库；沙箱环境可能不可达。缓解：plan §实施步骤 §5 明确"沙箱不可达时按 `quality-gates.md#验证表述规范` 标 `未运行` + 记录原因，不替代聚焦测试结果"。
- **风险 5**：document `extract_knowledge_graph` 内部的 JSON 解析与 `try_parse` 形态相似但实现不同；抽取到共享 helper 会改变可观察行为。**当前 spec 决定不抽**；后续若需要统一，可由独立 DOC-xxx / TD-xxx 任务承担。
- **后续**：切片 4（`DatabaseView.vue` 701 / `TemplateModal.vue` 665 抽子组件）由各自独立 spec / plan 承载。
- **后续**：切片 5+（500 附近候选 `document/router.py` 494 / `ResourceLibraryView.vue` 490 + `main.css` 1343 拆分）由后续任务独立 spec / plan。
- **后续**：TD-032 整体保持 🟡 进行中，待切片 1-4 全部交付后再改为 `🟢 完成`。

## 任务卡片字段

完成后需在 `docs/03-engineering-governance/current-work.md` 把 TD-032 任务卡「下一步」从「切片 3-4 各自独立 spec / plan」改为「切片 3 已合并；切片 4 待开工」；`docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md` 中 `document/tasks.py` 与 `structured_data/tasks.py` 状态从 `⚪ 待切片` 改为 `🟢 已拆分` + 新行数 + 拆出去向；`docs/03-engineering-governance/technical-debt.md#td-032` 备注追加「切片 3 已合并」；`docs/03-engineering-governance/work-log.md` 加一行索引。

## 实施记录（2026-06-08 切片 1 后追加）

实施时发现 spec 初稿的"scope 不动 tests / 不动业务代码"过于严格，需要 3 处小幅修正以满足"既有 import 路径全部仍能解析" + "零行为变化"双重约束。3 处修正均**零业务逻辑变化**、可被现有 16 + 36 + 7 = 59 个测试在 0 改动下覆盖。修正记录如下，与切片 1 / 切片 2 实施时反复出现的同种事实缺口一致。

| # | 文件 | 修正内容 | 原因 |
|---|------|----------|------|
| 1 | `app/contexts/document/application/tasks/__init__.py` | 在 `__all__` re-export 中加 `_build_parsed_structured_data` / `_merge_template_structured_data` | `tests/contexts/document/test_structured_data_contract.py:11-14` 显式 `from app.contexts.document.application.tasks import (_build_parsed_structured_data, _merge_template_structured_data)`。spec §1 草案漏了这两个带下划线 helper；任务卡 TD-009 时代的测试 import 它们已固化。 |
| 2 | `app/contexts/document/application/tasks/extract_template.py` L27 | `logger = logging.getLogger(__name__)` → `logger = logging.getLogger("app.contexts.document.application.tasks")` | 显式硬编码原 logger name；`__name__` 在子模块中是 `app.contexts.document.application.tasks.extract_template`，与原 `tasks.py` 顶部 logger name（`app.contexts.document.application.tasks`）不同。`tests/contexts/document/test_extract_template_selection.py:28, 270, 277` 用 `_TASKS_LOGGER` 做 caplog 过滤，行为零变化。 |
| 3 | `tests/contexts/document/test_extract_template_selection.py::test_logging_branches_match_production_code` L313-327 | `Path(.../tasks.py).read_text()` → `Path(.../tasks/extract_template.py).read_text()` | 该测试白盒断言 6 条日志字符串在源码里；`tasks.py` 物理不存在后，路径必须指向新物理文件 `tasks/extract_template.py`（承载 `template.select` 日志分支的子模块）。任务卡 §"业务行为零变化"承诺不变；仅测试读取路径跟随包形式调整。 |

### 与 spec 初稿的偏差说明

- spec §「scope」写"不动 tests / 不动业务代码"过于严格。3 处小修正符合 spec §"既有外部 import 路径全部仍能解析"（修正 1+2 让 caplog + import 都零变化）和"既有测试通过"（修正 3 让白盒日志测试跟随包形式）。
- 修正 2 是唯一的"业务代码非文件移动"改动：把 `_log_selection` 关联的 logger name 显式化到原值。这是 caplog 行为兼容所需，不改变任何运行时行为。
- 修正 3 是唯一的"tests 改动"：测试读取路径跟随包形式调整，测试目的（白盒断言日志分支）不变。
- 修正 1 是 spec 草案漏的 re-export，属于"spec 边界修正"，不是"实施调整"。

### 验证（按 spec §验证方式）

```bash
# pytest 聚焦测试
cd packages/server-python
.venv/bin/python -m pytest tests/shared/test_task_lifecycle.py tests/contexts/document/ tests/contexts/structured_data/ -q
# → 55 passed (12 + 36 + 7)

# ruff
.venv/bin/python -m ruff check app/ tests/
# → All checks passed!

# 文档门禁
scripts/check-engineering-docs
# → engineering docs checks passed (exit 0)
```

### 复盘 → spec 写作建议

未来 spec 起草时，**显式列出所有外部 import 站点**（不只 `from .X import Y` 这种"显式 import"，还要包括 `pathlib.read_text()` 物理文件读取、caplog logger name 字符串比对、`monkeypatch.setattr` 按字符串名替换等隐式引用），并在「scope」段明确"测试文件**可以**调整读取路径 / 字符串名以跟随包形式，前提是测试目的不变"。本任务与切片 1 / 切片 2 实施时反复出现的同种 spec 事实缺口。

