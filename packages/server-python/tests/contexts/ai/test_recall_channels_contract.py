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
    # 去掉前导下划线以兼容"未使用参数"惯例（_query, _ner_result）
    params = {p.lstrip("_") for p in sig.parameters}
    # 至少包含 query, ner_result, tenant_id, session, top_k
    for required in ("query", "ner_result", "tenant_id", "session", "top_k"):
        assert required in params, f"{cls.__name__}.recall missing {required}"
