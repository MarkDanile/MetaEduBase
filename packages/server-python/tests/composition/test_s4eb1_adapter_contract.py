"""R1-S4-E-B1：external object adapter contract 测试。

契约事实源：Plan §R1-S4-E E-2b（adapter 幂等重放/`receipt lookup` 硬前置 +
idempotency key 跨 takeover 稳定 + receipt digest 由 adapter evidence 重算）+
E-3a（「可证明未发送」判据 -> blocked/unknown 矩阵）。纯单元测试（无 DB）。

判别点（E-6）：
- 缺幂等重放且缺 receipt lookup 的 adapter -> `adapter_satisfies_prerequisite` False、
  `require_adapter_prerequisite` raise（变异：删任一 supports_* 判定 -> 红）。
- idempotency key 由 ref_scheme+ref_value+adapter_key/adapter_version 派生，**不含
  lease_epoch/attempt**（E-6 lease takeover 反例：固定输入下 key 相等；改 adapter 输入
  -> key 变化）。
- receipt digest 由 adapter evidence 重算（E-6 伪造本地 outcome 反例：同 envelope 改
  evidence -> digest 变化；64-hex）。
- E-3a 矩阵：ExternalEraseSuccess -> erased；NotSent -> blocked/erase_timeout；
  Timeout/Unknown -> unknown/outcome_unknown；Failed -> blocked/adapter_unavailable。
"""
from __future__ import annotations

import uuid

import pytest

from app.composition.external_object_adapter import (
    ExternalEraseFailedError,
    ExternalEraseNotSentError,
    ExternalEraseSuccess,
    ExternalEraseTimeoutError,
    ExternalEraseUnknown,
    adapter_satisfies_prerequisite,
    classify_adapter_outcome,
    external_erase_idempotency_key,
    external_erase_receipt_digest,
    external_ref_identity_digest,
    require_adapter_prerequisite,
)

# ---------------------------------------------------------------------------
# fake adapter（支持注入失败分类 + 计数）
# ---------------------------------------------------------------------------


class FakeAdapter:
    def __init__(
        self,
        *,
        adapter_key: str = "fake-db-local",
        adapter_version: int = 1,
        supports_idempotent_replay: bool = True,
        supports_receipt_lookup: bool = False,
    ):
        self.adapter_key = adapter_key
        self.adapter_version = adapter_version
        self.supports_idempotent_replay = supports_idempotent_replay
        self.supports_receipt_lookup = supports_receipt_lookup
        self.calls: list[str] = []

    async def delete_object(self, **kwargs):
        self.calls.append("delete")
        return ExternalEraseUnknown()

    async def receipt_lookup(self, **kwargs):
        return None


# ---------------------------------------------------------------------------
# E-2b 硬前置：幂等重放 / receipt lookup 至少一个
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("idempotent", "lookup", "expected"),
    [
        (True, True, True),
        (True, False, True),
        (False, True, True),
        (False, False, False),
    ],
)
def test_adapter_prerequisite_matrix(idempotent, lookup, expected):
    """E-2b：至少支持幂等重放或 receipt lookup 一个才满足硬前置。"""
    adapter = FakeAdapter(
        supports_idempotent_replay=idempotent, supports_receipt_lookup=lookup
    )
    assert adapter_satisfies_prerequisite(adapter) is expected


def test_require_adapter_prerequisite_raises_when_neither_supported():
    """缺两者 -> require raise（B1/B2 不得开工，E-2b 硬前置）。"""
    adapter = FakeAdapter(
        supports_idempotent_replay=False, supports_receipt_lookup=False
    )
    with pytest.raises(ValueError, match="neither idempotent replay nor receipt lookup"):
        require_adapter_prerequisite(adapter)


def test_require_adapter_prerequisite_passes_with_one():
    """至少一个支持 -> 不抛。"""
    require_adapter_prerequisite(
        FakeAdapter(supports_idempotent_replay=True, supports_receipt_lookup=False)
    )
    require_adapter_prerequisite(
        FakeAdapter(supports_idempotent_replay=False, supports_receipt_lookup=True)
    )


# ---------------------------------------------------------------------------
# E-2b idempotency key：跨 takeover 稳定（不含 lease_epoch/attempt）
# ---------------------------------------------------------------------------


def test_idempotency_key_stable_across_same_input():
    """固定 ref_scheme+ref_value+adapter_key/adapter_version -> key 值相等。

    E-6 lease takeover 反例：purge 被接管（新 lease_epoch/attempt）后 adapter 重调
    用——key 不含 lease_epoch/attempt，跨 takeover 稳定，新 lease 用同 key 去重。
    """
    kwargs = dict(
        ref_scheme="db_local",
        ref_value="obj://staging/object/1",
        adapter_key="fake-db-local",
        adapter_version=1,
    )
    assert external_erase_idempotency_key(**kwargs) == external_erase_idempotency_key(
        **kwargs
    )


def test_idempotency_key_changes_on_adapter_identity():
    """adapter_key/version 参与派生：换 adapter -> key 变化（防跨 adapter 误去重）。"""
    base = dict(
        ref_scheme="db_local",
        ref_value="obj://staging/object/1",
        adapter_key="fake-db-local",
        adapter_version=1,
    )
    assert external_erase_idempotency_key(**base) != external_erase_idempotency_key(
        **{**base, "adapter_key": "other-adapter"}
    )
    assert external_erase_idempotency_key(**base) != external_erase_idempotency_key(
        **{**base, "adapter_version": 2}
    )


def test_idempotency_key_changes_on_ref_identity():
    """ref_scheme/ref_value 参与派生：不同 object -> 不同 key。"""
    base = dict(
        ref_scheme="db_local",
        ref_value="obj://staging/object/1",
        adapter_key="fake-db-local",
        adapter_version=1,
    )
    assert external_erase_idempotency_key(**base) != external_erase_idempotency_key(
        **{**base, "ref_value": "obj://staging/object/2"}
    )


# ---------------------------------------------------------------------------
# E-2b receipt digest：必须由 adapter evidence 重算（禁自造）
# ---------------------------------------------------------------------------


def test_receipt_digest_is_64hex_and_deterministic():
    """receipt digest 64-hex + 同输入确定性。"""
    kwargs = dict(
        adapter_key="fake-db-local",
        adapter_version=1,
        idempotency_key="a" * 64,
        adapter_receipt_evidence="adapter-provided-receipt-abc",
        ref_digest="b" * 64,
        erase_outcome="erased",
    )
    digest = external_erase_receipt_digest(**kwargs)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert digest == external_erase_receipt_digest(**kwargs)


def test_receipt_digest_changes_on_tampered_evidence():
    """E-6 伪造本地 outcome 反例：evidence 被篡改/伪造 -> digest 变化（不匹配 fail closed）。"""
    base = dict(
        adapter_key="fake-db-local",
        adapter_version=1,
        idempotency_key="a" * 64,
        adapter_receipt_evidence="adapter-provided-receipt-abc",
        ref_digest="b" * 64,
        erase_outcome="erased",
    )
    assert external_erase_receipt_digest(**base) != external_erase_receipt_digest(
        **{**base, "adapter_receipt_evidence": "forged-local-outcome-no-evidence"}
    )
    # 仅凭本地「已调用」写 receipt（缺 evidence）同样不匹配——缺 evidence 不能重算
    # 出与持久化 digest 相同值。
    assert external_erase_receipt_digest(
        **{**base, "adapter_receipt_evidence": ""}
    ) != external_erase_receipt_digest(**base)


# ---------------------------------------------------------------------------
# E-2c 身份 digest（receipt envelope 的 ref_digest 字段）
# ---------------------------------------------------------------------------


def test_ref_identity_digest_covers_stable_ledger_identity():
    """ref 身份 digest 覆盖完整稳定 ledger identity + 确定性。"""
    kwargs = dict(
        ref_scheme="db_local",
        ref_value="obj://staging/object/1",
        source_table="agent_workspace_outbox",
        source_row_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        conversation_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    )
    digest = external_ref_identity_digest(**kwargs)
    assert len(digest) == 64
    assert digest == external_ref_identity_digest(**kwargs)
    assert digest != external_ref_identity_digest(**{**kwargs, "ref_value": "obj://x"})


# ---------------------------------------------------------------------------
# E-3a 矩阵：adapter 结果/异常 -> (erase_state, blocked_reason)
# ---------------------------------------------------------------------------


def test_classify_erased():
    c = classify_adapter_outcome(ExternalEraseSuccess(adapter_receipt_evidence="ev"))
    assert c.erase_state == "erased"
    assert c.blocked_reason is None


def test_classify_not_sent_is_blocked_erase_timeout():
    """可证明未发送（连接前失败）-> blocked/erase_timeout（可重试，E-3a 上行）。"""
    c = classify_adapter_outcome(
        ExternalEraseNotSentError("connection refused before send")
    )
    assert c.erase_state == "blocked"
    assert c.blocked_reason == "erase_timeout"


def test_classify_timeout_is_unknown_outcome_unknown():
    """发送后 TimeoutError（无法证明未发送）-> unknown/outcome_unknown（不自动重试）。

    E-6「可能已生效 timeout -> unknown」反例：fake adapter 注入发送后 TimeoutError
    -> 断言 unknown + outcome_unknown；变异：一律 blocked 自动重试 -> 红。
    """
    c = classify_adapter_outcome(
        ExternalEraseTimeoutError("request may have been sent")
    )
    assert c.erase_state == "unknown"
    assert c.blocked_reason == "outcome_unknown"


def test_classify_unknown_outcome_is_unknown():
    """adapter 返回 unknown -> unknown/outcome_unknown（不自动重试）。"""
    c = classify_adapter_outcome(ExternalEraseUnknown())
    assert c.erase_state == "unknown"
    assert c.blocked_reason == "outcome_unknown"


def test_classify_failed_is_blocked_adapter_unavailable():
    """明确失败（可证明未产生副作用）-> blocked/adapter_unavailable（可重试）。"""
    c = classify_adapter_outcome(
        ExternalEraseFailedError("adapter returned explicit error")
    )
    assert c.erase_state == "blocked"
    assert c.blocked_reason == "adapter_unavailable"
