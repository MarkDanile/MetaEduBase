# REQ-007 收口 REQ-003 RAG 质量链路验收缺口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收口 REQ-003 复盘发现的 4 类缺口：补 3 通道 fake rows 行为级测试、清理 `test_ai_chat_rag_e2e.py` 死代码、修正 P1 轨道 B 过度验证声明、修正 P1 / 迭代 / Backlog / current-work 状态矛盾。

**Architecture:** TDD 新增 fake rows 行为级测试（不动业务代码）→ 清理 e2e 死代码 → 修正 P1 / 迭代 验证结论（要么补测试要么改描述）→ 修正 Backlog REQ-003 / REQ-007 状态 + current-work 同步。最终全量验证 + 闭环。

**Tech Stack:** pytest 8.3+、pytest-asyncio、unittest.mock、SQLAlchemy AsyncSession（mock）、FastAPI ASGITransport。

**Requirement (事实源):** `docs/01-product-planning/05-requirements/REQ-007-req-003-rag-quality-gate-follow-up.md`（5 个 AC）

**Parent Spec:** `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md`

**Working dir:** `packages/server-python`

---

## File Structure

| 文件 | 职责 | AC |
|------|------|----|
| `tests/contexts/ai/test_recall_channels_behavior.py` (新建) | 3 通道 fake rows 行为级测试：row mapping、SQL 参数、空输入早退 | AC-1 |
| `tests/contexts/ai/test_ai_chat_rag_e2e.py` (修改) | 移除未使用 imports、helpers、无效变量 | AC-4 |
| `docs/01-product-planning/02-milestones/01-validation-phase.md` (修改) | 修正轨道 B 过度验证声明；REQ-003 / REQ-007 状态同步 | AC-2, AC-3 |
| `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md` (修改) | REQ-003 / REQ-007 状态同步 | AC-2 |
| `docs/01-product-planning/04-backlog.md` (修改) | REQ-003 / REQ-007 状态、摘要、下一步 | AC-2 |
| `docs/03-engineering-governance/current-work.md` (修改) | REQ-007 推进到"进行中"或"完成" | AC-2 |

业务代码 0 改动（除 AC-4 范围内 e2e 死代码清理）。

---

## Task 1: 3 通道 fake rows 行为级测试（AC-1）

**Files:**
- Create: `packages/server-python/tests/contexts/ai/test_recall_channels_behavior.py`

> **关键：3 通道都依赖真实业务代码路径**——必须真的调用 `channel.recall(query, ner_result, tenant_id, session, top_k)`，然后用 `AsyncMock` 拦截 `session.execute`，断言 SQL 文本 / 绑定参数 / 返回的 `RecallResult` 字段。不允许只断言 `name` / 签名（那是 Task 3 已覆盖的契约）。

### Step 1: 写失败测试 — PgVectorRecallChannel

新建 `tests/contexts/ai/test_recall_channels_behavior.py`：

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.contexts.knowledge.application.embedding_service import (
    get_embedding as get_embedding_vec,
)
from app.shared.domain.ner_pipeline import NERResult


# --- helpers ---------------------------------------------------------------

class _FakeRow(dict):
    """Behaves like SQLAlchemy Row + supports attribute access via __getitem__."""


def _row(node_id: str, **overrides) -> _FakeRow:
    base = {
        "id": node_id,
        "title": f"title-{node_id}",
        "description": f"desc-{node_id}",
        "domain": "smart_manufacturing",
        "level": "course",
        "path": None,
    }
    base.update(overrides)
    return _FakeRow(base)


def _fake_session_with_rows(rows: list[_FakeRow]) -> MagicMock:
    """返回一个 MagicMock session，session.execute 异步返回包含 rows 的结果。"""
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    execute = AsyncMock(return_value=result)
    session = MagicMock()
    session.execute = execute
    return session, execute


def _ner_with(domains: list[str] | None = None, levels: list[str] | None = None) -> NERResult:
    return NERResult(
        domains=domains or [],
        levels=levels or [],
        raw_entities=[],
    )


# --- PgVectorRecallChannel -----------------------------------------------

@pytest.mark.asyncio
async def test_pg_vector_recall_returns_recall_results_with_score_and_channel():
    ch = PgVectorRecallChannel()
    session, execute = _fake_session_with_rows([
        _row("n1", score=0.92),
        _row("n2", score=0.81),
    ])

    with patch.object(get_embedding_vec, "__call__", AsyncMock(return_value=[0.1] * 8)):
        results = await ch.recall(
            "智能制造",
            _ner_with(domains=["smart_manufacturing"]),
            tenant_id="t-1",
            session=session,
            top_k=5,
        )

    assert len(results) == 2
    assert all(r.channel == "vector" for r in results)
    assert [r.node_id for r in results] == ["n1", "n2"]
    assert results[0].score == pytest.approx(0.92, abs=1e-4)
    assert results[1].score == pytest.approx(0.81, abs=1e-4)
    # description / domain / level 都被正确映射
    assert results[0].domain == "smart_manufacturing"
    assert results[0].level == "course"


@pytest.mark.asyncio
async def test_pg_vector_recall_passes_tenant_topk_and_vector_to_sql():
    ch = PgVectorRecallChannel()
    session, execute = _fake_session_with_rows([])

    with patch.object(get_embedding_vec, "__call__", AsyncMock(return_value=[0.1, 0.2, 0.3])):
        await ch.recall(
            "anything",
            _ner_with(),
            tenant_id="tenant-xyz",
            session=session,
            top_k=7,
        )

    assert execute.await_count == 1
    stmt, params = execute.await_args.args
    # stmt 是 sqlalchemy TextClause
    assert "knowledge_nodes" in str(stmt)
    assert ":tid" in str(stmt)
    assert params["tid"] == "tenant-xyz"
    assert params["lim"] == 7
    # vec 是 8 元素数组，PG vector 字面量形如 "[0.1,0.2,0.3]"
    assert params["vec"].startswith("[")
    assert params["vec"].endswith("]")


@pytest.mark.asyncio
async def test_pg_vector_recall_returns_empty_when_embedding_unavailable():
    ch = PgVectorRecallChannel()
    session, execute = _fake_session_with_rows([])

    with patch.object(get_embedding_vec, "__call__", AsyncMock(return_value=None)):
        results = await ch.recall(
            "anything",
            _ner_with(),
            tenant_id="t",
            session=session,
            top_k=5,
        )

    assert results == []
    assert execute.await_count == 0  # 没有真去查 DB


# --- PgKeywordRecallChannel -----------------------------------------------

@pytest.mark.asyncio
async def test_pg_keyword_recall_maps_rows_and_uses_decrementing_score():
    ch = PgKeywordRecallChannel()
    session, _ = _fake_session_with_rows([
        _row("n1"),
        _row("n2"),
        _row("n3"),
    ])

    results = await ch.recall(
        "电子信息专业的课程",
        _ner_with(),
        tenant_id="t-2",
        session=session,
        top_k=5,
    )

    assert [r.node_id for r in results] == ["n1", "n2", "n3"]
    assert all(r.channel == "keyword" for r in results)
    # score 按 1.0 - idx*0.05 递减
    assert results[0].score == pytest.approx(1.0, abs=1e-4)
    assert results[1].score == pytest.approx(0.95, abs=1e-4)
    assert results[2].score == pytest.approx(0.90, abs=1e-4)


@pytest.mark.asyncio
async def test_pg_keyword_recall_passes_tenant_topk_and_keywords():
    ch = PgKeywordRecallChannel()
    session, execute = _fake_session_with_rows([])

    await ch.recall(
        "电子信息专业的课程有哪些？",
        _ner_with(),
        tenant_id="tenant-abc",
        session=session,
        top_k=4,
    )

    assert execute.await_count == 1
    stmt, params = execute.await_args.args
    assert "knowledge_nodes" in str(stmt)
    assert "ILIKE" in str(stmt)
    assert params["tid"] == "tenant-abc"
    assert params["lim"] == 4
    # 至少有一个 q{i} keyword 参数被传进去
    assert any(k.startswith("q") and v.startswith("%") and v.endswith("%")
               for k, v in params.items())


@pytest.mark.asyncio
async def test_pg_keyword_recall_returns_empty_when_no_keywords_extracted():
    ch = PgKeywordRecallChannel()
    session, execute = _fake_session_with_rows([])

    # 单字符 query 切不出长度 >=2 的关键词
    results = await ch.recall(
        "你",
        _ner_with(),
        tenant_id="t",
        session=session,
        top_k=5,
    )

    assert results == []
    assert execute.await_count == 0


# --- PgMetadataRecallChannel ----------------------------------------------

@pytest.mark.asyncio
async def test_pg_metadata_recall_filters_by_domain_and_level():
    ch = PgMetadataRecallChannel()
    session, execute = _fake_session_with_rows([
        _row("n1"),
        _row("n2"),
    ])

    results = await ch.recall(
        "anything",  # query 在 metadata 通道被忽略
        _ner_with(domains=["smart_manufacturing"], levels=["course"]),
        tenant_id="t-3",
        session=session,
        top_k=5,
    )

    assert [r.node_id for r in results] == ["n1", "n2"]
    assert all(r.channel == "metadata" for r in results)
    assert all(r.domain == "smart_manufacturing" for r in results)
    assert all(r.level == "course" for r in results)
    # score 按 0.8 - idx*0.04 递减
    assert results[0].score == pytest.approx(0.8, abs=1e-4)
    assert results[1].score == pytest.approx(0.76, abs=1e-4)


@pytest.mark.asyncio
async def test_pg_metadata_recall_passes_domain_level_tenant_topk_to_sql():
    ch = PgMetadataRecallChannel()
    session, execute = _fake_session_with_rows([])

    await ch.recall(
        "x",
        _ner_with(domains=["smart_manufacturing"], levels=["course", "chapter"]),
        tenant_id="tenant-meta",
        session=session,
        top_k=3,
    )

    assert execute.await_count == 1
    stmt, params = execute.await_args.args
    assert "knowledge_nodes" in str(stmt)
    assert "domain IN" in str(stmt)
    assert "level IN" in str(stmt)
    assert params["tid"] == "tenant-meta"
    assert params["lim"] == 3
    assert params["d0"] == "smart_manufacturing"
    assert params["l0"] == "course"
    assert params["l1"] == "chapter"


@pytest.mark.asyncio
async def test_pg_metadata_recall_returns_empty_when_no_ner_signal():
    ch = PgMetadataRecallChannel()
    session, execute = _fake_session_with_rows([])

    results = await ch.recall(
        "anything",
        _ner_with(domains=[], levels=[]),
        tenant_id="t",
        session=session,
        top_k=5,
    )

    assert results == []
    assert execute.await_count == 0  # 早退，没有 SQL
```

### Step 2: 跑测试，预期 9 项全部通过

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_recall_channels_behavior.py -v`
Expected: `9 passed`

如果有任何 import 错误（特别是 `get_embedding_vec` 是从 `embedding_service` 模块直接 import 的，可能 patch 路径需要调整）：

- 实际签名看 `app/contexts/knowledge/application/embedding_service.py:def get_embedding(...)`。如果你直接 patch 这个函数（`patch("app.contexts.knowledge.application.recall_service.get_embedding_vec", ...)`），更稳。改为：

```python
with patch(
    "app.contexts.knowledge.application.recall_service.get_embedding_vec",
    AsyncMock(return_value=[0.1] * 8),
):
```

并把 import 改成 `from unittest.mock import patch` 已经在；调整后回到 Step 2 重跑。

### Step 3: 不动业务代码

如果发现某条用例揭示了真实 bug（不是测试本身写错）—— STOP，回报 BLOCKED，不要在 Task 1 改业务代码。

### Step 4: 跑测试，预期 9 项全部通过

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_recall_channels_behavior.py -v`
Expected: `9 passed`

### Step 5: 提交

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/ai/test_recall_channels_behavior.py
git commit -m "test(ai): add 3-channel fake-rows behavior tests (REQ-007 AC-1)"
```

---

## Task 2: 清理 `test_ai_chat_rag_e2e.py` 死代码（AC-4）

**Files:**
- Modify: `packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py`

### Step 1: 扫描死 import / 死 helper

读取 `tests/contexts/ai/test_ai_chat_rag_e2e.py`，列出：

- 所有 `import` 行。
- 在测试体内**没有任何引用**的 import → 待删除。
- 定义了但没有任何测试调用的 helper / 局部变量 → 待删除。

按 REQ-007 复盘信号，下列是明确嫌疑（Task 4 的 code quality reviewer 早就标出）：

- `from app.contexts.knowledge.application.fusion_service import FrequencyFusion`（未用）
- `from app.contexts.knowledge.application.recall_service import (PgKeywordRecallChannel, PgMetadataRecallChannel, PgVectorRecallChannel)`（未用）
- `from app.shared.domain.ner_pipeline import NERResult`（未用）
- `_FakeRow` / `_row` / `_session_with_rows`（仅 AC-7 调一次，且 `session` 变量绑了没用）
- AC-7 测试里的 `session = _session_with_rows(...)` 局部变量（被 patched 的 recall 不用）

具体删除清单：见实现时根据实际未使用项确定；用 `rg "FrequencyFusion" tests/contexts/ai/test_ai_chat_rag_e2e.py`、`rg "PgKeywordRecallChannel" ...` 等检查。

### Step 2: 删除未使用 import + 未使用 helper

**只删除确认未被任何测试函数体内引用的项**。如果某个 helper 看着没用但被你"觉得将来要用"——保留（YAGNI 反面：不要为了清理而清理）。

### Step 3: 把 AC-7 的 `session = ...` 死局部变量删除（如果适用）

```python
# 删除前
async def test_ai_chat_degrades_when_one_channel_raises():
    session = _session_with_rows([_row("n1", 0.9)])  # 死变量

    async def vector_ok(*_a, **_k):
        ...
```

```python
# 删除后
async def test_ai_chat_degrades_when_one_channel_raises():
    async def vector_ok(*_a, **_k):
        ...
```

### Step 4: 跑测试，预期 3 项仍通过

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_ai_chat_rag_e2e.py -v`
Expected: `3 passed`

如果 `ruff check` 警告未使用 import：

Run: `cd packages/server-python && .venv/bin/python -m ruff check tests/contexts/ai/test_ai_chat_rag_e2e.py`
Expected: 退出码 0；不允许有未使用 import 警告。

### Step 5: 提交

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py
git commit -m "test(ai): remove dead imports/helpers in ai_chat_rag_e2e (REQ-007 AC-4)"
```

---

## Task 3: 修正 P1 / 迭代 / Backlog / current-work 状态矛盾（AC-2）

**Files:**
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`
- Modify: `docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md`
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/03-engineering-governance/current-work.md`

### Step 1: 阅读 P1 里程碑和迭代当前状态

- `01-validation-phase.md`：在轨道 B / Open Items 区，找到 REQ-003 引用 + REQ-007 引用（如已登记）。
- `2026-W23-p1-final-gap-closure.md`：Scope 表的 REQ-003 状态 + Review 段。
- `04-backlog.md`：REQ-003 行 + REQ-007 行。
- `current-work.md`：把 REQ-007 从"下一批候选"移出、登记到"当前进行中"。

### Step 2: 修正 P1 里程碑（`01-validation-phase.md`）

- 在 Open Items 段，找到 `REQ-003` 行：状态写为 `Done`（不是 `Candidate`）。
- 在 Open Items 段，新增 `REQ-007` 行：状态 `Doing`（本任务正在收口）。
- 轨道 B 表格的 4 行（Task 5 已写过）保持不变（修正过度声明留给 Task 4）。

### Step 3: 修正迭代卡（`2026-W23-p1-final-gap-closure.md`）

- Scope 表 REQ-003 状态 `Candidate` → `Done`。
- Scope 表新增 REQ-007 行：状态 `Doing`，验收 5 个 AC（指向 requirement）。
- Review 段第一行（"轨道 B 多项已有代码但缺直接测试"）保持——它描述的是 REQ-003 起点；可在 Review 后追加"REQ-003 已通过 PR #74 关闭，验收缺口由 REQ-007 承接"。

### Step 4: 修正 Backlog（`04-backlog.md`）

- REQ-003 行：状态 `Done` 保持（不变）。
- REQ-007 行：状态 `Candidate`（已建）保持；摘要"下一步"列保持已写好的"补 3 通道 fake rows 行为级测试，修正 P1 / 迭代状态矛盾和过度验证声明，清理 e2e 测试漂移"。

### Step 5: 修正 current-work（`current-work.md`）

- "当前进行中" 登记 REQ-007（保留我刚 push 的版本）。
- "下一批候选" 不再列 REQ-007。
- "最近完成" REQ-003 行已正确（包含 PR #74 链接）。

### Step 6: 跑文档门禁

Run: `cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && scripts/check-engineering-docs`
Expected: 退出码 0

### Step 7: 提交

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add docs/01-product-planning/02-milestones/01-validation-phase.md \
        docs/01-product-planning/03-iterations/2026-W23-p1-final-gap-closure.md \
        docs/01-product-planning/04-backlog.md \
        docs/03-engineering-governance/current-work.md
git commit -m "docs(REQ-007): sync REQ-003/REQ-007 status across P1/iteration/Backlog/workbench (AC-2)"
```

---

## Task 4: 修正过度验证声明 + 全量验证（AC-3, AC-5）

**Files:**
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`
- Run-only（不修改代码）: `tests/contexts/ai/{test_rule_based_ner,test_frequency_fusion,test_recall_channels_contract,test_recall_channels_behavior,test_ai_chat_rag_e2e}.py`

### Step 1: 复核 P1 轨道 B 4 行的"验证结论"列

读 `01-validation-phase.md` 轨道 B 4 行（Task 5 已写过）。对照**实际**测试覆盖范围：

- **NER**："已通过 `test_rule_based_ner.py` 7 用例（AC-1/AC-2）" — 实际覆盖：域别名 / 关键词 / 全角 / 大小写 / 未知 query / dataclass / 协议。是否含"空字符串"？**查 `test_rule_based_ner.py::test_extract_unknown_query_returns_empty_lists`** —— query 是中文句子，不是空字符串。**修正**：把"覆盖别名 / 全角 / 大小写 / 未知 query / 关键词 / 协议"或保留原句但**追加"未覆盖空字符串 query"**（不撒谎）。
- **3 通道召回**："已通过 `test_recall_channels_contract.py` 9 用例（AC-6）" — Task 1 之后应改写为"已通过 `test_recall_channels_contract.py` 9 用例（AC-6）+ `test_recall_channels_behavior.py` 9 用例（AC-1 行为级）"。
- **结果融合**："已通过 `test_frequency_fusion.py` 5 用例（AC-3/4/5）" — 实际覆盖：去重 / 频次 / top_k / 空输入 / channel 集合。**保持原句**。
- **溯源上下文组装**："已通过 `test_ai_chat_rag_e2e.py` 3 用例（AC-7/8/9）" — 实际覆盖：单通道失败降级 / sources 字段集 / 跨通道去重。**未覆盖**：空召回回退（`_run_channel` 全部返回 `[]` 时 `fused = []`，`reply` 怎么走）、LLM 失败兜底文案（`_call_llm` 异常时返回 `f"❌ AI 回答生成失败: ..."`）。**修正**：描述改为"3 用例（AC-7 单通道失败降级 / AC-8 sources 字段集 / AC-9 跨通道去重）；未覆盖空召回回退与 LLM 失败兜底文案"。

### Step 2: 改写过度声明

在 `01-validation-phase.md` 轨道 B 4 行的"说明"列（或在"验证结论"列后追加）按 Step 1 的修正改写。**禁止**写"覆盖空召回 / LLM 失败"而没有对应测试。

如果决定补这两个用例（空召回 / LLM 失败），**必须**先回到 Task 1 风格的额外测试用例；这超出 REQ-007 范围（见 Out of Scope：不修改 RAG 业务代码，且未在 requirement 5 AC 里）。**推荐改写描述**而非补测试。

### Step 3: 全量验证（AC-5）

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_rule_based_ner.py tests/contexts/ai/test_frequency_fusion.py tests/contexts/ai/test_recall_channels_contract.py tests/contexts/ai/test_ai_chat_rag_e2e.py -q`
Expected: 退出码 0，所有用例通过

**重要**：如果本机 `metaedu_test` 不可达（之前 REQ-003 复盘已记录），本命令**不**依赖 `metaedu_test`（所有新测试都走 mock）。如果出现 DB 错误——STOP，回报 BLOCKED。

### Step 4: ruff + docs gate

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
.venv/bin/python -m ruff check packages/server-python/tests/contexts/ai/ 2>&1 | tail -10 || true
scripts/check-engineering-docs
git diff --check
```

Expected: 全部退出码 0 或 0 命中。

### Step 5: 提交

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add docs/01-product-planning/02-milestones/01-validation-phase.md
git commit -m "docs(REQ-007): correct P1 Track-B over-claim to match actual test coverage (AC-3/AC-5)"
```

---

## Self-Review

**Spec coverage check:**

| AC | 任务 |
|----|------|
| AC-1 | Task 1（3 通道 fake rows 行为级测试 9 用例） |
| AC-2 | Task 3（P1 / iteration / Backlog / current-work 状态同步） |
| AC-3 | Task 4 Step 1-2（修正过度声明） |
| AC-4 | Task 2（清理 e2e 死 import / 死 helper） |
| AC-5 | Task 4 Step 3-4（命令可复现 + 不假报通过） |

**Placeholder scan:** Task 1 测试代码完整、Task 4 Step 1 给的修正建议具体可贴。

**Type consistency:**
- `RecallResult` 字段顺序与 Task 1 助手 `_row()` 一致。
- `NERResult` 构造 `_ner_with()` 沿用。
- `_FakeRow` 子类 + `dict` 行为在 Task 1 助手和现有 e2e 文件中保持兼容。
