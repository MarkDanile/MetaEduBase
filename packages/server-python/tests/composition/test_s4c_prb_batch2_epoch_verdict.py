r"""R1-S4-C PR-B 批次2b：consume epoch 分类（deterministic verdict）。

契约：Plan §R1-S4-C C3/R4（round-4/5/6/7/8 修订）。
- unknown：producer epoch NULL -> Tx1 inbox rejected + tombstone + ledger
  epoch_unresolvable（scope 已知 conversation_scope / 未知 tenant_scope）。
- stale：producer epoch < 当前**且** fence erasing/erased -> Tx1 tombstone +
  Tx2 终态化，不登记 ledger。
- normal：producer epoch == 当前，或 < 当前但 fence active（soft-delete/
  restore，R4 carve-out——正文从未 erase、fence 允许写，不得仅因 token 推进
  被 tombstone）。
- data_anomaly：producer epoch > 当前（fence 对齐窗口）-> fail closed。
"""

from __future__ import annotations

from app.composition.agent_control_plane import classify_consume_epoch
from app.contexts.agent_workspace.domain.erasure import ErasureFenceState


def test_epoch_unknown_when_producer_null():
    v = classify_consume_epoch(
        producer_purge_revision=None,
        current_purge_revision=3,
        fence_state=ErasureFenceState.ACTIVE,
    )
    assert v.kind == "unknown"
    assert v.current_purge_revision == 3


def test_epoch_stale_when_producer_below_and_fence_not_active():
    for st in (ErasureFenceState.ERASING, ErasureFenceState.ERASED):
        v = classify_consume_epoch(
            producer_purge_revision=1,
            current_purge_revision=5,
            fence_state=st,
        )
        assert v.kind == "stale", st


def test_epoch_normal_when_equal():
    v = classify_consume_epoch(
        producer_purge_revision=5,
        current_purge_revision=5,
        fence_state=ErasureFenceState.ACTIVE,
    )
    assert v.kind == "normal"


def test_epoch_normal_when_below_but_fence_active_is_restore_carveout():
    """R4 carve-out：soft-delete/restore 推进 token 但 fence active 时，pre-existing
    事件不得仅因 token 推进被 tombstone。"""
    v = classify_consume_epoch(
        producer_purge_revision=3,
        current_purge_revision=5,
        fence_state=ErasureFenceState.ACTIVE,
    )
    assert v.kind == "normal"


def test_epoch_normal_when_below_but_fence_blocked():
    """fence blocked（非 erasing/erased）也不 stale——未实际清除。"""
    v = classify_consume_epoch(
        producer_purge_revision=3,
        current_purge_revision=5,
        fence_state=ErasureFenceState.BLOCKED,
    )
    assert v.kind == "normal"


def test_epoch_data_anomaly_when_producer_above_current():
    v = classify_consume_epoch(
        producer_purge_revision=7,
        current_purge_revision=5,
        fence_state=ErasureFenceState.ACTIVE,
    )
    assert v.kind == "data_anomaly"
