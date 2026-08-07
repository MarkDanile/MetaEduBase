r"""R1-S4-C C8 项 11：具名 reason code 参数化回归测试（PR-B 批次2）。

契约：Plan §R1-S4-C round-8/round-9 修订。``SUPPRESSION_REASON_CODES`` 增
``epoch_unknown_rejected``（unknown epoch）/``epoch_stale_rejected``（stale
epoch）——**不**被 `suppression_reason_code` 归一成 `operator_suppressed`
（否则精确幂等判定失去可区分身份）。变异验证：从 allowlist 剔除任一新 code
对应测试变红（击杀回退变异）；既有 5 code 归一行为不变对照。
"""

from __future__ import annotations

import pytest

from app.composition.agent_suppression_reasons import (
    SUPPRESSION_REASON_CODES,
    SUPPRESSION_REASON_FALLBACK,
    suppression_reason_code,
)


@pytest.mark.parametrize(
    ("input_reason", "expected"),
    [
        # 具名 code：不被归一成 fallback（C8 项 11 核心断言）。
        ("epoch_unknown_rejected", "epoch_unknown_rejected"),
        ("epoch_stale_rejected", "epoch_stale_rejected"),
        # 既有 5 code 归一行为不变对照。
        ("external_object_deleted", "external_object_deleted"),
        ("output_purge_suppressed", "output_purge_suppressed"),
        ("late_body_write_rejected", "late_body_write_rejected"),
        ("retention_expired", "retention_expired"),
        # 自由文本 -> fallback（不反射原始内容）。
        ("用户说了一些敏感内容", SUPPRESSION_REASON_FALLBACK),
        ("some-free-form-reason", SUPPRESSION_REASON_FALLBACK),
    ],
)
def test_suppression_reason_code_normalization(input_reason, expected):
    assert suppression_reason_code(input_reason) == expected


def test_named_codes_are_registered_in_allowlist():
    """两个具名 code 必须已入 allowlist（变异验证前置：剔除即测试失败）。"""
    assert "epoch_unknown_rejected" in SUPPRESSION_REASON_CODES
    assert "epoch_stale_rejected" in SUPPRESSION_REASON_CODES


def test_named_codes_are_distinct_from_existing_and_fallback():
    """具名 code 不得与既有 code / fallback 冲突，保持可区分身份。"""
    assert SUPPRESSION_REASON_FALLBACK not in {
        "epoch_unknown_rejected",
        "epoch_stale_rejected",
    }
    assert not {"epoch_unknown_rejected", "epoch_stale_rejected"} & {
        "external_object_deleted",
        "output_purge_suppressed",
        "late_body_write_rejected",
        "retention_expired",
    }
