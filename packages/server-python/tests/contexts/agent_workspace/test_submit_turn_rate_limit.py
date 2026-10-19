"""SubmitTurnRateLimiter 容量 / 淘汰 / 恢复契约测试（TD-109 返修）。

纯单元测试：经 `now` 注入确定性时间，不需要真实 PostgreSQL。
覆盖 #647 复审 P3-a 的三个待区分问题：
- 活跃限流窗口被容量淘汰后，同一 key 能否重新获得额度（计数重置 = 绕过）；
- 拒绝请求是否刷新淘汰顺序（LRU 位置）；
- 容量饱和时的具体行为与内存有界性。

并如实证伪一个过度声明：拒绝路径只写已存在 key（窗口满才会拒绝），
不产生无界增长——有界性在旧实现上也成立，缺陷仅在淘汰顺序与饱和策略。
"""

from __future__ import annotations

import uuid

import pytest

from app.contexts.agent_workspace.interfaces.api import submit_turn_rate_limit as rl_module
from app.contexts.agent_workspace.interfaces.api.submit_turn_rate_limit import (
    SubmitTurnRateLimiter,
)

LIMIT = 2
WINDOW = 60.0
MAX_KEYS = 5


def _key() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4()


def _limiter() -> SubmitTurnRateLimiter:
    return SubmitTurnRateLimiter(limit=LIMIT, window_seconds=WINDOW)


@pytest.fixture(autouse=True)
def _small_capacity(monkeypatch: pytest.MonkeyPatch):
    """把容量缩到 5，避免每次测试真灌 10_000 个 key。"""
    monkeypatch.setattr(rl_module, "_MAX_TRACKED_KEYS", MAX_KEYS)


def _allowed(limiter: SubmitTurnRateLimiter, key: tuple[uuid.UUID, uuid.UUID], t: float) -> bool:
    return limiter.acquire(tenant_id=key[0], actor_id=key[1], now=t).allowed


def test_window_expiry_restores_quota() -> None:
    """窗口到期后同一 key 恢复额度（新旧实现均应成立的基础语义）。"""
    limiter = _limiter()
    key = _key()
    assert _allowed(limiter, key, 0.0)
    assert _allowed(limiter, key, 0.5)
    rejected = limiter.acquire(tenant_id=key[0], actor_id=key[1], now=1.0)
    assert not rejected.allowed
    # Retry-After 指向最旧命中过窗时刻（0.0 + 60 - 1.0 → 60，含 +1 取整）
    assert rejected.retry_after_seconds >= 59
    assert rejected.retry_after_seconds <= 61
    assert _allowed(limiter, key, 61.0)


def test_rejection_refreshes_lru_position() -> None:
    """拒绝路径也必须刷新 LRU 位置，否则活跃窗口滞留淘汰位。"""
    limiter = _limiter()
    key_a = _key()
    assert _allowed(limiter, key_a, 0.0)
    assert _allowed(limiter, key_a, 0.5)
    # 两个后续 key 把 A 挤到最旧位
    _allowed(limiter, _key(), 1.0)
    _allowed(limiter, _key(), 1.5)
    assert list(limiter._hits)[0] == key_a  # 拒绝前 A 确为最旧
    rejected = limiter.acquire(tenant_id=key_a[0], actor_id=key_a[1], now=2.0)
    assert not rejected.allowed
    assert list(limiter._hits)[-1] == key_a  # 拒绝后 A 被刷新为最新


def test_capacity_flood_cannot_reset_live_window() -> None:
    """核心回归：高基数新 key 洪峰不得淘汰未过期窗口（计数不得重置）。

    饱和策略：容量满且无全过期条目时，新 key 一律 fail-closed 429，
    已有活跃窗口的剩余额度完全不受影响；内存始终有界。
    """
    limiter = _limiter()
    victim = _key()
    assert _allowed(limiter, victim, 0.0)
    assert _allowed(limiter, victim, 0.5)
    blocked = limiter.acquire(tenant_id=victim[0], actor_id=victim[1], now=1.0)
    assert not blocked.allowed  # victim 已被限流

    # 洪峰：20 个新 key 各来一次，容量只有 5
    flood_results = []
    for i in range(20):
        flood_results.append(_allowed(limiter, _key(), 2.0 + i * 0.01))
    # 容量内的新 key 正常放行（victim + 4 个新 key = 5），其余饱和 429
    assert flood_results.count(True) == MAX_KEYS - 1
    assert flood_results.count(False) == 20 - (MAX_KEYS - 1)
    assert len(limiter._hits) <= MAX_KEYS  # 内存有界

    # 洪峰之后 victim 的限流状态必须完好：窗口未过期，仍然 429
    still_blocked = limiter.acquire(tenant_id=victim[0], actor_id=victim[1], now=3.0)
    assert not still_blocked.allowed
    assert still_blocked.retry_after_seconds >= 55  # 额度未被重置


def test_rejection_path_does_not_grow_table_unbounded() -> None:
    """如实证伪「拒绝流量导致无界增长」：拒绝分支只写已存在 key。

    窗口满才会拒绝，而已满窗口意味着 key 已在表内；新 key 的写入只发生在
    允许路径且受容量约束。新旧实现均应满足有界性。
    """
    limiter = _limiter()
    repeat_key = _key()
    for i in range(50):
        # 同一 key 反复打到超限并一直被拒
        limiter.acquire(tenant_id=repeat_key[0], actor_id=repeat_key[1], now=10.0 + i * 0.001)
        # 夹杂新 key（受容量约束）
        _allowed(limiter, _key(), 10.0 + i * 0.001)
        assert len(limiter._hits) <= MAX_KEYS


def test_expired_entries_are_swept_before_saturation_rejection() -> None:
    """容量饱和时先清全过期条目：有过期垃圾时新 key 不应被误 429。"""
    limiter = _limiter()
    stale_keys = [_key() for _ in range(MAX_KEYS)]  # 填满容量
    for i, key in enumerate(stale_keys):
        assert _allowed(limiter, key, float(i))
    # 时间推进到全部过期之后
    fresh = _key()
    t = WINDOW + 100.0
    assert _allowed(limiter, fresh, t)
    # 过期条目已被清扫，而不是占着容量
    remaining = set(limiter._hits)
    assert fresh in remaining
    assert all(stale not in remaining for stale in stale_keys)
    assert len(limiter._hits) == 1


def test_saturation_retry_after_is_positive() -> None:
    """饱和 429 同样携带正的 Retry-After（phase-A §10 形状不变）。"""
    limiter = _limiter()
    live = [_key() for _ in range(MAX_KEYS)]
    for i, key in enumerate(live):
        assert _allowed(limiter, key, float(i))
    newcomer = _key()
    decision = limiter.acquire(tenant_id=newcomer[0], actor_id=newcomer[1], now=10.0)
    assert not decision.allowed
    assert decision.retry_after_seconds >= 1
    # 既有 key 的额度未被 newcomer 影响
    for key in live:
        assert _allowed(limiter, key, 11.0)
