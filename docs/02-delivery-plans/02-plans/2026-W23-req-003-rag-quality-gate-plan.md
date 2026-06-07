# REQ-003 P1 RAG 质量链路验收与回归测试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 P1 RAG 链路（NER / 3 通道召回 / 频次融合 / sources 结构）补齐可复现的回归测试，让轨道 B 四项"待验证"翻为验证结论。

**Architecture:** 纯函数 / 协议级测试 + 接口级 mock 测试，不连 PostgreSQL。沿用 `tests/conftest.py` 与现有 `httpx.AsyncClient` mock 模式打 LLM。完成 4 个独立测试文件后做 1 个文档回填任务收口。

**Tech Stack:** pytest 8.3+、pytest-asyncio、unittest.mock、SQLAlchemy AsyncSession、FastAPI ASGITransport。

**Spec:** `docs/02-delivery-plans/01-specs/2026-W23-req-003-rag-quality-gate.md`

**Working dir:** `packages/server-python`

---

## File Structure

| 文件 | 职责 | 验收点 |
|------|------|--------|
| `tests/contexts/ai/test_rule_based_ner.py` (新建) | `RuleBasedNER` 域 / 层级 / 归一化 / 协议 | AC-1, AC-2 |
| `tests/contexts/ai/test_frequency_fusion.py` (新建) | `FrequencyFusion.fuse` 去重、频次、`top_k`、channel 拼接 | AC-3, AC-4, AC-5 |
| `tests/contexts/ai/test_recall_channels_contract.py` (新建) | 3 通道协议形态与 `name` 契约（不接 DB） | AC-6 |
| `tests/contexts/ai/test_ai_chat_rag_e2e.py` (新建) | 端到端 mock-LLM 验证 sources 结构、降级、融合行为 | AC-7, AC-8, AC-9 |
| `docs/01-product-planning/02-milestones/01-validation-phase.md` (修改) | 轨道 B 四项"待验证"翻结论 | AC-11 |
| `docs/01-product-planning/04-backlog.md` (修改) | REQ-003 状态推进 | AC-11 |

业务代码 0 改动。

---

## Task 1: NER 域与层级识别回归测试

**Files:**
- Create: `packages/server-python/tests/contexts/ai/test_rule_based_ner.py`
- Test: 同上

- [ ] **Step 1: 写失败测试**

在 `tests/contexts/ai/test_rule_based_ner.py`：

```python
import pytest

from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.shared.domain.ner_pipeline import NERPipeline, NERResult


@pytest.mark.asyncio
async def test_extract_known_domain_and_level():
    ner = RuleBasedNER()
    result = await ner.extract("电子信息专业的课程有哪些？")
    assert "electronics_info" in result.domains
    assert "professional" in result.levels
    assert "course" in result.levels


@pytest.mark.asyncio
async def test_extract_aliases_normalize_to_same_domain():
    ner = RuleBasedNER()
    a = await ner.extract("财经商贸类知识")
    b = await ner.extract("财经商贸类知识")
    c = await ner.extract("财经商贸类知识")
    assert a.domains == b.domains == c.domains == ["finance_commerce"]


@pytest.mark.asyncio
async def test_extract_full_width_punctuation_does_not_break():
    ner = RuleBasedNER()
    result = await ner.extract("智能制造（高端）是什么？")
    assert "smart_manufacturing" in result.domains


@pytest.mark.asyncio
async def test_extract_case_insensitive_for_english_segments():
    ner = RuleBasedNER()
    result = await ner.extract("What is 智能制造?")
    assert "smart_manufacturing" in result.domains


@pytest.mark.asyncio
async def test_extract_unknown_query_returns_empty_lists():
    ner = RuleBasedNER()
    result = await ner.extract("你好，请问今天天气如何")
    assert result == NERResult(domains=[], levels=[], raw_entities=[])


@pytest.mark.asyncio
async def test_extract_returns_ner_result_dataclass():
    ner = RuleBasedNER()
    result = await ner.extract("土木建筑专业的知识点")
    assert isinstance(result, NERResult)
    assert "civil_engineering" in result.domains
    assert "knowledge_point" in result.levels


def test_rule_based_ner_satisfies_protocol():
    ner = RuleBasedNER()
    assert isinstance(ner, NERPipeline)
```

- [ ] **Step 2: 跑测试，预期至少 1 条失败**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_rule_based_ner.py -v`
Expected: 7 项中至少 1 项失败（文件刚创建），或全部通过说明 NER 实现已对齐。**记录实际结果。**

- [ ] **Step 3: 不写实现 — 只确认测试本身写对**

如果步骤 2 出现"无法导入"类错误，调整 import 路径后回到 Step 2。
**任务 1 不修改任何业务代码。**

- [ ] **Step 4: 跑测试，预期全部通过**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_rule_based_ner.py -v`
Expected: `7 passed`

- [ ] **Step 5: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/ai/test_rule_based_ner.py
git commit -m "test(ai): add RuleBasedNER regression coverage (REQ-003 AC-1/AC-2)"
```

---

## Task 2: 频次融合回归测试

**Files:**
- Create: `packages/server-python/tests/contexts/ai/test_frequency_fusion.py`
- Test: 同上

- [ ] **Step 1: 写失败测试**

在 `tests/contexts/ai/test_frequency_fusion.py`：

```python
import pytest

from app.contexts.knowledge.application.fusion_service import FrequencyFusion
from app.shared.domain.recall_channel import RecallResult


def _r(node_id: str, score: float, channel: str) -> RecallResult:
    return RecallResult(
        node_id=node_id, title=f"title-{node_id}", description=None,
        domain="smart_manufacturing", level="course",
        score=score, channel=channel, path=None,
    )


def test_fuse_merges_duplicate_node_id_across_channels():
    fusion = FrequencyFusion()
    channel_results = {
        "vector":   [_r("n1", 0.9, "vector"),   _r("n2", 0.5, "vector")],
        "keyword":  [_r("n1", 0.7, "keyword"),  _r("n3", 0.6, "keyword")],
        "metadata": [_r("n2", 0.8, "metadata")],
    }
    fused = fusion.fuse(channel_results, top_k=10)
    ids = [r.node_id for r in fused]
    # n1 出现 2 次，n2 出现 2 次，n3 出现 1 次；频次降序
    assert ids.index("n1") < ids.index("n3")
    assert ids.index("n2") < ids.index("n3")


def test_fuse_orders_by_frequency_then_best_score():
    fusion = FrequencyFusion()
    channel_results = {
        "vector":   [_r("low", 0.99, "vector")],
        "keyword":  [_r("low", 0.50, "keyword")],
        "metadata": [_r("hi",  0.30, "metadata"), _r("hi", 0.29, "metadata")],
    }
    fused = fusion.fuse(channel_results, top_k=10)
    # low 出现 2 次，hi 出现 2 次，频次并列时按最佳分数降序，low=0.99 > hi=0.30
    assert [r.node_id for r in fused] == ["low", "hi"]


def test_fuse_top_k_truncates_results():
    fusion = FrequencyFusion()
    channel_results = {
        "vector": [_r(f"n{i}", 0.5, "vector") for i in range(5)],
    }
    fused = fusion.fuse(channel_results, top_k=2)
    assert len(fused) == 2
    assert {r.node_id for r in fused} == {"n0", "n1"}


def test_fuse_empty_input_returns_empty_list():
    fusion = FrequencyFusion()
    assert fusion.fuse({}, top_k=10) == []
    assert fusion.fuse({"vector": []}, top_k=10) == []


def test_fuse_channel_field_lists_all_source_channels():
    fusion = FrequencyFusion()
    channel_results = {
        "vector":   [_r("n1", 0.9, "vector")],
        "keyword":  [_r("n1", 0.7, "keyword")],
        "metadata": [_r("n1", 0.6, "metadata")],
    }
    fused = fusion.fuse(channel_results, top_k=5)
    assert len(fused) == 1
    assert fused[0].node_id == "n1"
    channels = set(fused[0].channel.split(","))
    # 三个来源都应被记录（顺序由实现决定，集合相等即可）
    assert channels == {"vector", "keyword", "metadata"}
```

- [ ] **Step 2: 跑测试，预期至少 1 条失败**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_frequency_fusion.py -v`
Expected: `5 passed` 或失败项被记录。**特别注意 `test_fuse_channel_field_lists_all_source_channels`——若现有实现未做 set 去重，按 spec 风险段放宽断言到"含全部来源（允许重复）"并入账 TD，不改业务代码。**

- [ ] **Step 3: 若 Step 2 触发了 spec 风险段**

不动 `fusion_service.py`。在 `docs/03-engineering-governance/technical-debt.md` 新增条目 `TD-031 FrequencyFusion.channel 拼接去重` 描述证据（测试名 + 实际输出），然后放宽对应断言为：

```python
    parts = fused[0].channel.split(",")
    assert set(parts) == {"vector", "keyword", "metadata"}
    # 允许重复，spec 风险段已记录
```

重新跑测试通过后，继续 Step 4。

- [ ] **Step 4: 跑测试，预期全部通过**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_frequency_fusion.py -v`
Expected: `5 passed`

- [ ] **Step 5: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/ai/test_frequency_fusion.py
git commit -m "test(ai): add FrequencyFusion regression coverage (REQ-003 AC-3/4/5)"
```

---

## Task 3: 3 通道协议契约测试

**Files:**
- Create: `packages/server-python/tests/contexts/ai/test_recall_channels_contract.py`
- Test: 同上

- [ ] **Step 1: 写失败测试**

在 `tests/contexts/ai/test_recall_channels_contract.py`：

```python
import inspect

import pytest

from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)


EXPECTED_NAMES = {
    PgVectorRecallChannel: "vector",
    PgKeywordRecallChannel: "keyword",
    PgMetadataRecallChannel: "metadata",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("cls,expected_name", list(EXPECTED_NAMES.items()))
async def test_channel_name_matches_contract(cls, expected_name):
    ch = cls()
    assert ch.name == expected_name


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", list(EXPECTED_NAMES.keys()))
async def test_channel_exposes_recall_coroutine(cls):
    ch = cls()
    assert callable(getattr(ch, "recall", None))
    assert inspect.iscoroutinefunction(ch.recall)


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", list(EXPECTED_NAMES.keys()))
async def test_channel_recall_signature_accepts_required_args(cls):
    ch = cls()
    sig = inspect.signature(ch.recall)
    params = list(sig.parameters)
    # 至少包含 query, ner_result, tenant_id, session, top_k
    for required in ("query", "ner_result", "tenant_id", "session", "top_k"):
        assert required in params, f"{cls.__name__}.recall missing {required}"
```

- [ ] **Step 2: 跑测试，预期至少 1 条失败**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_recall_channels_contract.py -v`
Expected: 9 项中至少 1 项失败（文件刚创建），记录实际结果。

- [ ] **Step 3: 不改业务代码**

- [ ] **Step 4: 跑测试，预期全部通过**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_recall_channels_contract.py -v`
Expected: `9 passed`

- [ ] **Step 5: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/ai/test_recall_channels_contract.py
git commit -m "test(ai): add 3-channel RecallChannel contract tests (REQ-003 AC-6)"
```

---

## Task 4: ai_chat 端到端 RAG 链路测试

**Files:**
- Create: `packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py`
- Test: 同上

> **本任务不依赖 PostgreSQL 可达**：通过直接 patch `_ner` / 三个 `_channel` 模块级单例与 `httpx.AsyncClient` 来构造端到端场景。

- [ ] **Step 1: 写失败测试**

在 `tests/contexts/ai/test_ai_chat_rag_e2e.py`：

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.contexts.knowledge.application.fusion_service import FrequencyFusion
from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.contexts.knowledge.interfaces.api import ai_router
from app.shared.domain.ner_pipeline import NERResult
from app.shared.domain.recall_channel import RecallResult


# --- helpers ---------------------------------------------------------------

class _FakeRow(dict):
    pass


def _row(node_id: str, score: float | None = None):
    r = _FakeRow()
    r["id"] = node_id
    r["title"] = f"title-{node_id}"
    r["description"] = f"desc-{node_id}"
    r["domain"] = "smart_manufacturing"
    r["level"] = "course"
    r["path"] = None
    if score is not None:
        r["score"] = score
    return r


def _session_with_rows(rows):
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    execute = AsyncMock(return_value=result)
    session = MagicMock()
    session.execute = execute
    return session


def _build_app():
    app = FastAPI()
    app.include_router(ai_router.router, prefix="/api/v1/ai")

    async def _override_user():
        return {"id": "u", "tenant_id": "t", "role": "student"}

    async def _override_session():
        yield MagicMock()

    from app.contexts.knowledge.interfaces.api.ai_router import get_session  # noqa
    app.dependency_overrides[get_session] = _override_session
    from app.contexts.identity.interfaces.api.dependencies import get_current_user  # noqa
    app.dependency_overrides[get_current_user] = _override_user
    return app


def _mock_llm_response(content: str = "这是AI的回答"):
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": content}}]}
    mock_response.raise_for_status = MagicMock()

    client = AsyncMock()
    client.post = AsyncMock(return_value=mock_response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# --- AC-7: single channel failure does not break chat --------------------

@pytest.mark.asyncio
async def test_ai_chat_degrades_when_one_channel_raises():
    session = _session_with_rows([_row("n1", 0.9)])

    async def vector_ok(*_a, **_k):
        return [RecallResult(
            node_id="n1", title="t", description=None,
            domain="smart_manufacturing", level="course",
            score=0.9, channel="vector", path=None,
        )]

    async def keyword_raise(*_a, **_k):
        raise RuntimeError("db down")

    async def metadata_ok(*_a, **_k):
        return [RecallResult(
            node_id="n2", title="t2", description=None,
            domain="smart_manufacturing", level="course",
            score=0.7, channel="metadata", path=None,
        )]

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(ai_router, "_vector_channel", SimpleNamespace(
            name="vector", recall=vector_ok,
        )), patch.object(ai_router, "_keyword_channel", SimpleNamespace(
            name="keyword", recall=keyword_raise,
        )), patch.object(ai_router, "_metadata_channel", SimpleNamespace(
            name="metadata", recall=metadata_ok,
        )), patch.object(ai_router, "_ner", RuleBasedNER()), \
             patch("app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
                   return_value=_mock_llm_response()):
            resp = await ac.post("/api/v1/ai/chat", json={"message": "智能制造专业的课程"})

    assert resp.status_code == 200
    data = resp.json()
    assert "sources" in data
    ids = [s["id"] for s in data["sources"]]
    # 失败的 keyword 通道不能拖垮整体
    assert "n1" in ids
    assert "n2" in ids


# --- AC-8: sources schema --------------------------------------------------

@pytest.mark.asyncio
async def test_ai_chat_sources_have_required_fields():
    async def vector_ok(query, ner_result, tenant_id, session, top_k=5):
        return [RecallResult(
            node_id="n1", title="title-n1", description="d",
            domain="smart_manufacturing", level="course",
            score=0.9, channel="vector", path=None,
        )]

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(ai_router, "_vector_channel", SimpleNamespace(
            name="vector", recall=vector_ok,
        )), patch.object(ai_router, "_keyword_channel", SimpleNamespace(
            name="keyword", recall=AsyncMock(return_value=[]),
        )), patch.object(ai_router, "_metadata_channel", SimpleNamespace(
            name="metadata", recall=AsyncMock(return_value=[]),
        )), patch.object(ai_router, "_ner", RuleBasedNER()), \
             patch("app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
                   return_value=_mock_llm_response()):
            resp = await ac.post("/api/v1/ai/chat", json={"message": "智能制造"})

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["sources"], list)
    assert len(data["sources"]) == 1
    src = data["sources"][0]
    for field in ("id", "title", "domain", "level", "score", "channel"):
        assert field in src, f"sources[0] missing {field}"
    assert set(src.keys()) == {"id", "title", "description", "domain", "level", "score", "channel"}


# --- AC-9: e2e fusion dedup ------------------------------------------------

@pytest.mark.asyncio
async def test_ai_chat_fuses_duplicate_node_id_across_channels():
    shared = RecallResult(
        node_id="shared", title="shared-title", description=None,
        domain="smart_manufacturing", level="course",
        score=0.9, channel="vector", path=None,
    )
    only_keyword = RecallResult(
        node_id="kw-only", title="kw", description=None,
        domain="smart_manufacturing", level="course",
        score=0.6, channel="keyword", path=None,
    )

    async def vector_ok(*_a, **_k):  return [shared]
    async def keyword_ok(*_a, **_k): return [shared, only_keyword]
    async def metadata_ok(*_a, **_k): return []

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(ai_router, "_vector_channel", SimpleNamespace(
            name="vector", recall=vector_ok,
        )), patch.object(ai_router, "_keyword_channel", SimpleNamespace(
            name="keyword", recall=keyword_ok,
        )), patch.object(ai_router, "_metadata_channel", SimpleNamespace(
            name="metadata", recall=metadata_ok,
        )), patch.object(ai_router, "_ner", RuleBasedNER()), \
             patch("app.contexts.knowledge.interfaces.api.ai_router.httpx.AsyncClient",
                   return_value=_mock_llm_response()):
            resp = await ac.post("/api/v1/ai/chat", json={"message": "智能制造专业的知识点"})

    assert resp.status_code == 200
    data = resp.json()
    ids = [s["id"] for s in data["sources"]]
    assert ids.count("shared") == 1, f"expected dedup, got {ids}"
    assert "kw-only" in ids
    shared_src = next(s for s in data["sources"] if s["id"] == "shared")
    assert set(shared_src["channel"].split(",")) == {"vector", "keyword"}
```

- [ ] **Step 2: 跑测试，预期至少 1 条失败**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_ai_chat_rag_e2e.py -v`
Expected: 3 项中至少 1 项失败（文件刚创建），记录实际结果。

- [ ] **Step 3: 不改业务代码**

如遇 `RuleBasedNER` 在 dependency override 下未生效或 import 路径错，按提示调整 import 与 `patch.object` 路径，回 Step 2。

- [ ] **Step 4: 跑测试，预期全部通过**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai/test_ai_chat_rag_e2e.py -v`
Expected: `3 passed`

- [ ] **Step 5: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add packages/server-python/tests/contexts/ai/test_ai_chat_rag_e2e.py
git commit -m "test(ai): add ai_chat e2e RAG coverage incl. sources structure (REQ-003 AC-7/8/9)"
```

---

## Task 5: 验证总跑 + 文档回填

**Files:**
- Modify: `docs/01-product-planning/02-milestones/01-validation-phase.md`
- Modify: `docs/01-product-planning/04-backlog.md`

- [ ] **Step 1: 全量验证（AC-10）**

Run: `cd packages/server-python && .venv/bin/python -m pytest tests/contexts/ai tests/contexts/knowledge -q`
Expected: 全部通过（包含 Task 1-4 全部用例 + 既有 knowledge 测试）。**实际退出码 0 才算通过。**

如果失败：先回到对应任务修测试 / 调实现 / 入账 TD；不要直接关闭。

- [ ] **Step 2: 编辑 `01-validation-phase.md` 轨道 B**

把"实现事实 / 验证证据"分栏里以下 4 行的"验证结论"由"待验证"改为具体结论，并新增"测试文件"列：

- NER 实体识别（枚举规则）→ "已通过 `tests/contexts/ai/test_rule_based_ner.py` 7 项用例（AC-1/AC-2）"
- 多源并行召回（3 通道） → "已通过 `tests/contexts/ai/test_recall_channels_contract.py` 9 项契约用例（AC-6）；端到端集成待 metaedu_test 可达后由 REQ-006 补"
- 结果融合（频次排序） → "已通过 `tests/contexts/ai/test_frequency_fusion.py` 5 项用例（AC-3/4/5）"
- 溯源上下文组装增强 → "已通过 `tests/contexts/ai/test_ai_chat_rag_e2e.py` 3 项端到端用例（AC-7/8/9）"

如果 Task 2 Step 3 触发了 `TD-031`，在对应行的"说明"栏追加"channel 拼接去重行为入账 TD-031"。

- [ ] **Step 3: 编辑 `04-backlog.md` REQ-003 行**

- 状态：`Candidate` → `Done`（如果 AC-1~10 全通过，且未触发任何 TD 阻断）
- 状态：`Candidate` → `Blocked`（如触发阻断级 TD），并在"下一步"列写明阻塞 ID
- "下一步"列改为："已建 spec/plan；2026-W23 迭代内完成回归测试并回填验证"

- [ ] **Step 4: 工程文档门禁**

Run: `cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase && scripts/check-engineering-docs`
Expected: 退出码 0。若失败按脚本提示修（典型：状态/链接/编号漂移）。

- [ ] **Step 5: 提交**

```bash
cd /Users/strony/Desktop/StronyCodePlace/Edu_ProjectSpace/MetaEduBase
git add docs/01-product-planning/02-milestones/01-validation-phase.md \
        docs/01-product-planning/04-backlog.md
git commit -m "docs(REQ-003): close P1 RAG quality gate; backfill validation evidence"
```

---

## Self-Review

**Spec coverage check:**

| AC | 任务 |
|----|------|
| AC-1 / AC-2 | Task 1 |
| AC-3 / AC-4 / AC-5 | Task 2（含 TD 风险路径） |
| AC-6 | Task 3 |
| AC-7 / AC-8 / AC-9 | Task 4 |
| AC-10 | Task 5 Step 1 |
| AC-11 | Task 5 Step 2-3 |

无缺口。

**Placeholder scan:** 全任务均含完整代码与命令，无 TBD。

**Type consistency:**

- `RecallResult` 字段顺序、类型在 Task 2 助手 `_r()` 和 Task 4 显式构造中保持一致。
- `RuleBasedNER()` / `FrequencyFusion()` 在 Task 1/2/4 保持无参构造。
- `ai_router` 模块级单例 `_ner / _vector_channel / _keyword_channel / _metadata_channel` 在 Task 4 全部 `patch.object`，名字一致。
