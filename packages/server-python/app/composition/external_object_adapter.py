"""S4-E-B1 external object adapter 契约（external.payload.v1）。

契约事实源：Plan §R1-S4-E E-2b/E-3a/E-6（PR #546 已合并 `c243c36d`）。B2
（ExternalPayloadErasureParticipant）消费本契约；B1 定义并证明它。

- **adapter contract 硬前置（E-2b）**：adapter 必须支持**幂等重放**（同
  idempotency key 重复调用无重复副作用）或 **receipt lookup**（同 key 取回已发删除
  evidence）至少一个，否则 B1/B2 不得开工——``adapter_satisfies_prerequisite`` 返回
  False / ``require_adapter_prerequisite`` raise。
- **失败分类注入（E-3a「可证明未发送」判据）**：adapter 须能注入两类失败——发送前
  连接错误（``ExternalEraseNotSentError``，**可证明未发送** -> ``blocked/erase_timeout``，
  可重试）与发送后超时（``ExternalEraseTimeoutError``，**可能已生效** ->
  ``unknown/outcome_unknown``，不自动重试）；``classify_adapter_outcome`` 承载 E-3a
  矩阵（纯映射，B2 消费）。
- **idempotency key / receipt digest（E-2b）**：idempotency key 由 ``ref_scheme`` +
  ``ref_value`` + ``adapter_key``/``adapter_version`` 派生，**不含 lease_epoch/attempt**
  （跨 takeover 稳定——新 lease 用同 key 去重）；``receipt_digest`` 必须由 adapter
  返回的可验证 ``adapter_receipt_evidence`` 按冻结 envelope 重算（**禁仅凭本地 outcome
  自造 receipt**，E-6 伪造本地 outcome 反例）。``ref_digest`` 由
  ``external_ref_identity_digest`` 对完整稳定 ledger 身份派生。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.contexts.agent_execution.domain.snapshots import snapshot_digest

# ---------------------------------------------------------------------------
# 失败分类（E-3a「可证明未发送」判据）
# ---------------------------------------------------------------------------


class ExternalEraseError(Exception):
    """external object adapter 调用失败基类。"""


class ExternalEraseFailedError(ExternalEraseError):
    """明确失败（非幂等错误，**可证明未产生副作用**）-> ``blocked/adapter_unavailable``。

    可重试（重试 ``registered``，须满足 B1 capability 判定，E-3a）。
    """


class ExternalEraseNotSentError(ExternalEraseError):
    """建立连接/发出请求前失败（**可证明未发送**）-> ``blocked/erase_timeout``。

    与 ``ExternalEraseTimeoutError`` 的判别边界（E-3a）：连接前失败可证明未发送；
    无法区分是否已发出的一律视为**可能已生效** -> ``unknown``。
    """


class ExternalEraseTimeoutError(ExternalEraseError):
    """超时且无法证明是否已发出（**可能已生效**）-> ``unknown/outcome_unknown``。

    不自动重试；仅 adapter 支持幂等重放/``receipt lookup`` 时允许（E-2b key 去重）。
    """


# ---------------------------------------------------------------------------
# adapter 结果类型
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExternalEraseSuccess:
    """删除成功 + adapter 返回的可验证 evidence。

    ``receipt_digest`` 必须由 ``adapter_receipt_evidence`` 重算（E-2b）——缺 evidence
    或 evidence 被篡改时重算不匹配（E-6 伪造本地 outcome 反例）。
    """

    adapter_receipt_evidence: str


@dataclass(frozen=True, slots=True)
class ExternalEraseUnknown:
    """adapter 返回 unknown outcome（请求可能已生效）-> ``unknown/outcome_unknown``。"""


class ExternalObjectAdapter(Protocol):
    """external object 删除 adapter 契约形状（B1 判定/B2 消费共用）。

    - ``adapter_key``/``adapter_version``：稳定协议身份（idempotency/receipt 派生输入）。
    - ``supports_idempotent_replay``/``supports_receipt_lookup``：E-2b 硬前置——至少
      一个为 True 才能被 B1 判定为 capability 已验证。
    - ``delete_object``：幂等删除（同 key 重复调用无重复副作用）；成功返回
      ``ExternalEraseSuccess(evidence)``，outcome 未知返回 ``ExternalEraseUnknown``；
      失败按分类 raise ``ExternalEraseNotSentError``/``ExternalEraseTimeoutError``/
      ``ExternalEraseFailedError``。
    - ``receipt_lookup``：同 stable idempotency key 取回已发删除的 evidence（重放比对，
      E-2b）；未实现时 raise（由 ``supports_receipt_lookup`` 声明，调用方须先检查）。
    """

    adapter_key: str
    adapter_version: int
    supports_idempotent_replay: bool
    supports_receipt_lookup: bool

    async def delete_object(
        self,
        *,
        ref_scheme: str,
        ref_value: str,
        idempotency_key: str,
    ) -> ExternalEraseSuccess | ExternalEraseUnknown:
        """幂等删除 object。"""

    async def receipt_lookup(self, *, idempotency_key: str) -> str | None:
        """同 key 取回已发删除的 adapter evidence；无 receipt 返回 None。"""


def adapter_satisfies_prerequisite(adapter: ExternalObjectAdapter) -> bool:
    """E-2b 硬前置：幂等重放或 receipt lookup 至少一个。"""
    return adapter.supports_idempotent_replay or adapter.supports_receipt_lookup


def require_adapter_prerequisite(adapter: ExternalObjectAdapter) -> None:
    """显式校验硬前置（不满足 raise——B1/B2 不得开工，E-2b）。"""
    if not adapter_satisfies_prerequisite(adapter):
        raise ValueError(
            f"adapter {adapter.adapter_key!r} v{adapter.adapter_version} supports "
            "neither idempotent replay nor receipt lookup; S4-E erasure cannot start"
        )


# ---------------------------------------------------------------------------
# E-3a 矩阵分类
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EraseOutcomeClassification:
    """E-3a 矩阵一行：(erase_state, blocked_reason)。"""

    erase_state: str
    blocked_reason: str | None


def classify_adapter_outcome(
    outcome: ExternalEraseSuccess | ExternalEraseUnknown | ExternalEraseError,
) -> EraseOutcomeClassification:
    """E-3a 矩阵：adapter 结果/异常 -> (erase_state, blocked_reason) 分类。

    纯映射（B2 消费；本 Slice 不写 ledger 状态——写 `erased`/`blocked`/`unknown` 的
    双事务协议归 S4-E-B2）。``digest_mismatch``（blocked）由 B2 在 receipt 重算比对处
    产生，不在此分类。
    """
    if isinstance(outcome, ExternalEraseSuccess):
        return EraseOutcomeClassification("erased", None)
    if isinstance(outcome, ExternalEraseUnknown):
        return EraseOutcomeClassification("unknown", "outcome_unknown")
    if isinstance(outcome, ExternalEraseNotSentError):
        return EraseOutcomeClassification("blocked", "erase_timeout")
    if isinstance(outcome, ExternalEraseTimeoutError):
        return EraseOutcomeClassification("unknown", "outcome_unknown")
    if isinstance(outcome, ExternalEraseFailedError):
        return EraseOutcomeClassification("blocked", "adapter_unavailable")
    raise ValueError(f"unclassified external adapter outcome: {outcome!r}")


# ---------------------------------------------------------------------------
# E-2b idempotency key / receipt digest（跨 takeover 稳定）
# ---------------------------------------------------------------------------


def external_erase_idempotency_key(
    *,
    ref_scheme: str,
    ref_value: str,
    adapter_key: str,
    adapter_version: int,
) -> str:
    """E-2b：跨 takeover 稳定 idempotency key（**不含 lease_epoch/attempt**）。

    takeover 后 key 不变——新 lease 用同 key 去重，不重复删（E-6 lease takeover 反例）。
    """
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "external_erase_idempotency",
            "ref_scheme": ref_scheme,
            "ref_value": ref_value,
            "adapter_key": adapter_key,
            "adapter_version": adapter_version,
        }
    )


def external_ref_identity_digest(
    *,
    ref_scheme: str,
    ref_value: str,
    source_table: str,
    source_row_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
) -> str:
    """ledger 行身份的 canonical digest（receipt envelope 的 ``ref_digest`` 字段）。

    覆盖完整稳定 ledger identity（``ref_scheme``/``ref_value``/``source_table``/
    ``source_row_id``/``conversation_id``），与 E-2c ``external_delete_intent.v1`` 的
    身份集合一致（B2 的 intent digest 复用同一身份投影）。
    """
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "external_ref_identity",
            "ref_scheme": ref_scheme,
            "ref_value": ref_value,
            "source_table": source_table,
            "source_row_id": str(source_row_id),
            "conversation_id": (
                str(conversation_id) if conversation_id is not None else None
            ),
        }
    )


def external_erase_receipt_digest(
    *,
    adapter_key: str,
    adapter_version: int,
    idempotency_key: str,
    adapter_receipt_evidence: str,
    ref_digest: str,
    erase_outcome: str,
) -> str:
    """E-2b 冻结 envelope：``receipt_digest`` 必须由 adapter evidence 重算。

    ``adapter_receipt_evidence`` 缺失/被篡改时重算不匹配（E-6 伪造本地 outcome
    反例：仅凭本地「已调用」写 receipt -> 重算不匹配 fail closed）。64-hex 满足
    ``ck_*_receipt_digest``；不新增 adapter_receipt_digest 列（receipt_digest 直接
    承载 canonical evidence）。
    """
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "external_erase_receipt",
            "adapter_key": adapter_key,
            "adapter_version": adapter_version,
            "idempotency_key": idempotency_key,
            "adapter_receipt_evidence": adapter_receipt_evidence,
            "ref_digest": ref_digest,
            "erase_outcome": erase_outcome,
        }
    )
