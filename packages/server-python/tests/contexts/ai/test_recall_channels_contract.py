import inspect

import pytest

from app.contexts.knowledge.application.recall_service import (
    PgKeywordRecallChannel,
    PgMetadataRecallChannel,
    PgVectorRecallChannel,
)
from app.shared.domain.recall_channel import RecallChannel

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
async def test_channel_recall_signature_matches_protocol(cls):
    """所有具体 recall 形参必须与 RecallChannel Protocol 完全一致（modulo 默认值）。

    不再做下划线前缀兼容：下划线前缀不再是"未使用参数"的私用约定，
    与 Protocol 严格对齐。TD-030 收口契约。
    """
    protocol_params = set(inspect.signature(RecallChannel.recall).parameters)
    cls_params = set(inspect.signature(cls.recall).parameters)
    missing = protocol_params - cls_params
    extra = cls_params - protocol_params
    assert not missing, f"{cls.__name__}.recall 缺少 Protocol 形参: {sorted(missing)}"
    assert not extra, f"{cls.__name__}.recall 出现 Protocol 外形参: {sorted(extra)}"


@pytest.mark.asyncio
@pytest.mark.parametrize("cls", list(EXPECTED_NAMES.keys()))
async def test_channel_recall_signature_accepts_required_args(cls):
    ch = cls()
    sig = inspect.signature(ch.recall)
    params = set(sig.parameters)
    # 至少包含 query, ner_result, tenant_id, session, top_k
    for required in ("query", "ner_result", "tenant_id", "session", "top_k"):
        assert required in params, f"{cls.__name__}.recall missing {required}"
