"""受控 suppression reason code 契约（composition/shared coordination）。

Spec §5.2/§5.3/§9.3：suppression tombstone 与 execution decision 的 reason 只能
来自受控枚举，自由文本（可能含正文、提示词、案件细节或 secret）永不落库。
workspace 的 ``redacted_reason`` 与 execution 的 ``decision_reason`` 共用同一
归一入口，保证同一 suppress 操作两侧落的 code 一致。
"""

from __future__ import annotations

# 受控 suppression reason code 白名单：只存受控 code，自由文本不落库。不在
# 白名单的输入归一到通用 code，不反射原始内容。
SUPPRESSION_REASON_CODES: frozenset[str] = frozenset(
    {
        "external_object_deleted",
        "output_purge_suppressed",
        "late_body_write_rejected",
        "operator_suppressed",
        "retention_expired",
    }
)
SUPPRESSION_REASON_FALLBACK = "operator_suppressed"


def suppression_reason_code(reason: str) -> str:
    """把调用方 reason 归一到受控 code；自由文本不落 tombstone/decision。

    归一仅做大小写与空白/连字符折叠，不保留原始内容的任何片段；非白名单
    输入一律落到 ``SUPPRESSION_REASON_FALLBACK``。
    """
    normalized = reason.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in SUPPRESSION_REASON_CODES:
        return normalized
    return SUPPRESSION_REASON_FALLBACK
