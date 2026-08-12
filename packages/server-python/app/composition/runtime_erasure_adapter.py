"""R1-S4-E-C runtime.private.v1 session-destroy adapter 契约（conformance）。

契约事实源：Plan §R1-S4-E E-5 第 4 项（S4-E-C Runtime conformance fake）+
spec §10.3（conformance suite：session destroy + 旧 epoch event + 迟到 seq +
unknown outcome + ACK 重放）。镜像 ``external_object_adapter.py``（S4-E-B1/B2
external adapter contract）的失败分类/idempotency/receipt 结构——REQ-043 的每个
Runtime Adapter 在启用前必须通过本 conformance suite（spec §10.3）。

- **adapter contract 硬前置（E-2b 镜像）**：adapter 必须支持**幂等重放**（同
  idempotency key 重复调用无重复副作用）或 **receipt lookup**（同 key 取回已发
  destroy evidence）至少一个，否则 conformance 不得开工——
  ``adapter_satisfies_prerequisite`` 返回 False / ``require_adapter_prerequisite``
  raise。
- **失败分类注入（E-3a「可证明未发送」判据镜像）**：adapter 须能注入两类失败——
  调用前连接错误（``RuntimeDestroyNotSentError``，**可证明未发送** ->
  ``blocked/erase_timeout``，可重试）与调用后超时（``RuntimeDestroyTimeoutError``，
  **可能已生效** -> ``unknown/outcome_unknown``，不自动重试）；
  ``classify_destroy_outcome`` 承载矩阵（纯映射，participant 消费）。
- **idempotency key / receipt digest（E-2b 镜像）**：idempotency key 由
  ``runtime_session_ref`` + ``adapter_key``/``adapter_version`` 派生，**不含
  lease_epoch/attempt**（跨 takeover 稳定）；``receipt_digest`` 必须由 adapter
  返回的可验证 ``adapter_receipt_evidence`` 按冻结 envelope 重算（**禁仅凭本地
  outcome 自造 receipt**，E-6 伪造本地 outcome 反例镜像）。``session_digest`` 由
  ``runtime_session_identity_digest`` 对完整稳定 binding 身份派生。

**边界**：本模块是 conformance fake 的 adapter 契约形状，**不构成激活依据**
（spec §10.2「fake 只证明契约，不得宣称生产对象已删除」）——``runtime.private.v1``
registry 保持 ``erase_available=False``，真实 Pi/ACP/LangGraph spool 删除归
REQ-043；``runtime_spool`` capability 当前**无实现、无清除路径**（spool 不在 R1
源码范围），conformance 只覆盖 ``runtime_session_ref``。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.contexts.agent_execution.domain.snapshots import snapshot_digest

# ---------------------------------------------------------------------------
# 失败分类（E-3a「可证明未发送」判据镜像）
# ---------------------------------------------------------------------------


class RuntimeDestroyError(Exception):
    """runtime session destroy adapter 调用失败基类。"""


class RuntimeDestroyFailedError(RuntimeDestroyError):
    """明确失败（非幂等错误，**可证明未产生副作用**）-> ``blocked/adapter_unavailable``。

    可重试（retry 重新 destroy 同一 session ref）。
    """


class RuntimeDestroyNotSentError(RuntimeDestroyError):
    """调用前失败（**可证明未发送**）-> ``blocked/erase_timeout``。

    与 ``RuntimeDestroyTimeoutError`` 的判别边界（E-3a 镜像）：调用前失败可证明
    未发送；无法区分是否已发出的一律视为**可能已生效** -> ``unknown``。
    """


class RuntimeDestroyTimeoutError(RuntimeDestroyError):
    """超时且无法证明是否已发出（**可能已生效**）-> ``unknown/outcome_unknown``。

    不自动重试；仅 adapter 支持幂等重放/``receipt lookup`` 时允许（E-2b key 去重）。
    """


# ---------------------------------------------------------------------------
# adapter 结果类型
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuntimeDestroySuccess:
    """destroy 成功 + adapter 返回的可验证 evidence。

    ``receipt_digest`` 必须由 ``adapter_receipt_evidence`` 重算（E-2b 镜像）——
    缺 evidence 或 evidence 被篡改时重算不匹配（伪造本地 outcome 反例）。
    """

    adapter_receipt_evidence: str


@dataclass(frozen=True, slots=True)
class RuntimeDestroyUnknown:
    """adapter 返回 unknown outcome（请求可能已生效）-> ``unknown/outcome_unknown``。"""


class RuntimeSessionDestroyAdapter(Protocol):
    """runtime session destroy adapter 契约形状（conformance participant 消费）。

    - ``adapter_key``/``adapter_version``：稳定协议身份（idempotency/receipt 派生输入）。
    - ``supports_idempotent_replay``/``supports_receipt_lookup``：E-2b 硬前置——至少
      一个为 True 才能被判定为 capability 已验证。
    - ``destroy_session``：幂等 destroy（同 key 重复调用无重复副作用）；成功返回
      ``RuntimeDestroySuccess(evidence)``，outcome 未知返回 ``RuntimeDestroyUnknown``；
      失败按分类 raise ``RuntimeDestroyNotSentError``/``RuntimeDestroyTimeoutError``/
      ``RuntimeDestroyFailedError``。
    - ``receipt_lookup``：同 stable idempotency key 取回已发 destroy 的 evidence
      （重放比对，E-2b）；未实现时 raise（由 ``supports_receipt_lookup`` 声明，
      调用方须先检查）。
    """

    adapter_key: str
    adapter_version: int
    supports_idempotent_replay: bool
    supports_receipt_lookup: bool

    async def destroy_session(
        self,
        *,
        runtime_session_ref: str,
        idempotency_key: str,
    ) -> RuntimeDestroySuccess | RuntimeDestroyUnknown:
        """幂等 destroy runtime session。"""

    async def receipt_lookup(self, *, idempotency_key: str) -> str | None:
        """同 key 取回已发 destroy 的 adapter evidence；无 receipt 返回 None。"""


def adapter_satisfies_prerequisite(adapter: RuntimeSessionDestroyAdapter) -> bool:
    """E-2b 硬前置镜像：幂等重放或 receipt lookup 至少一个。"""
    return adapter.supports_idempotent_replay or adapter.supports_receipt_lookup


def require_adapter_prerequisite(adapter: RuntimeSessionDestroyAdapter) -> None:
    """显式校验硬前置（不满足 raise——conformance 不得开工，E-2b）。"""
    if not adapter_satisfies_prerequisite(adapter):
        raise ValueError(
            f"adapter {adapter.adapter_key!r} v{adapter.adapter_version} supports "
            "neither idempotent replay nor receipt lookup; S4-E-C runtime "
            "conformance cannot start"
        )


# ---------------------------------------------------------------------------
# E-3a 矩阵分类镜像
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DestroyOutcomeClassification:
    """E-3a 矩阵一行：(erase_state, blocked_reason)。"""

    erase_state: str
    blocked_reason: str | None


def classify_destroy_outcome(
    outcome: RuntimeDestroySuccess | RuntimeDestroyUnknown | RuntimeDestroyError,
) -> DestroyOutcomeClassification:
    """E-3a 矩阵：adapter 结果/异常 -> (erase_state, blocked_reason) 分类。

    纯映射（conformance participant 消费）。``digest_mismatch``（blocked）由
    participant 在 receipt 重算比对处产生，不在此分类。
    """
    if isinstance(outcome, RuntimeDestroySuccess):
        return DestroyOutcomeClassification("erased", None)
    if isinstance(outcome, RuntimeDestroyUnknown):
        return DestroyOutcomeClassification("unknown", "outcome_unknown")
    if isinstance(outcome, RuntimeDestroyNotSentError):
        return DestroyOutcomeClassification("blocked", "erase_timeout")
    if isinstance(outcome, RuntimeDestroyTimeoutError):
        return DestroyOutcomeClassification("unknown", "outcome_unknown")
    if isinstance(outcome, RuntimeDestroyFailedError):
        return DestroyOutcomeClassification("blocked", "adapter_unavailable")
    raise ValueError(f"unclassified runtime destroy outcome: {outcome!r}")


# ---------------------------------------------------------------------------
# E-2b idempotency key / receipt digest（跨 takeover 稳定）镜像
# ---------------------------------------------------------------------------


def runtime_destroy_idempotency_key(
    *,
    runtime_session_ref: str,
    adapter_key: str,
    adapter_version: int,
) -> str:
    """E-2b：跨 takeover 稳定 idempotency key（**不含 lease_epoch/attempt**）。

    takeover 后 key 不变——新 lease 用同 key 去重，不重复 destroy（E-6 lease
    takeover 反例镜像）。
    """
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "runtime_destroy_idempotency",
            "runtime_session_ref": runtime_session_ref,
            "adapter_key": adapter_key,
            "adapter_version": adapter_version,
        }
    )


def runtime_session_identity_digest(
    *,
    binding_id: uuid.UUID,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    runtime_profile_id: uuid.UUID,
    runtime_session_ref: str,
) -> str:
    """binding 身份的 canonical digest（receipt envelope 的 ``session_digest`` 字段）。

    覆盖完整稳定 binding identity，与 intent digest 的身份集合一致（participant
    复用同一身份投影）。
    """
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "runtime_session_identity",
            "binding_id": str(binding_id),
            "tenant_id": str(tenant_id),
            "conversation_id": str(conversation_id),
            "runtime_profile_id": str(runtime_profile_id),
            "runtime_session_ref": runtime_session_ref,
        }
    )


def runtime_destroy_receipt_digest(
    *,
    adapter_key: str,
    adapter_version: int,
    idempotency_key: str,
    adapter_receipt_evidence: str,
    session_digest: str,
    destroy_outcome: str,
) -> str:
    """E-2b 冻结 envelope：``receipt_digest`` 必须由 adapter evidence 重算。

    ``adapter_receipt_evidence`` 缺失/被篡改时重算不匹配（伪造本地 outcome
    反例镜像：仅凭本地「已调用」写 receipt -> 重算不匹配 fail closed）。
    """
    return snapshot_digest(
        {
            "schema_version": 1,
            "kind": "runtime_destroy_receipt",
            "adapter_key": adapter_key,
            "adapter_version": adapter_version,
            "idempotency_key": idempotency_key,
            "adapter_receipt_evidence": adapter_receipt_evidence,
            "session_digest": session_digest,
            "destroy_outcome": destroy_outcome,
        }
    )
