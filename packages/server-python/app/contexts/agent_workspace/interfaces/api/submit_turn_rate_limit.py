"""WS-S2 phase-A §10 要求的 submit 提交限流（429 + ``Retry-After``）。

范围与限制（必须如实理解，不得当成分布式限流）：

- 仓库此前**没有**任何限流中间件或依赖（phase-A §10 已注明「实装归 phase-C」）。
- 本实现是**进程内**滑动窗口计数器，按 ``(tenant_id, actor_id)`` 限流。
- 它不是跨副本共享的分布式限流：多副本部署下每个副本各自计数。真实分布式
  限流需要外部共享存储，超出 WS-S2 phase-C 范围，本模块不声称实现它。
- 它只挂在 submit-turn 端点，不改动其它既有端点的行为。

限流器自身故障时的行为（fail-closed，如实记录）：

- ``acquire()`` 不吞异常。端点以裸调用方式使用它，因此若计数器自身抛出
  异常，请求会沿 FastAPI 既有异常路径失败，而**不会**被静默放行。
- 这是刻意的保守取向：限流是保护措施，但把它的实现缺陷当成「放行」会
  让保护措施静默失效；让失败显式暴露更安全。
- 注意：业务正确性并不依赖限流器——durable 事务边界与 capability gate
  仍独立生效；此处 fail-closed 只影响「限流计数」本身。
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass

# 默认配额：单 actor 在窗口内允许的提交次数与窗口长度。
# 取值偏宽，避免在合法短轮询与契约测试场景下误伤；它冻结的是「存在限流与
# Retry-After 语义」，不是最终运营参数。
DEFAULT_SUBMIT_LIMIT = 60
DEFAULT_SUBMIT_WINDOW_SECONDS = 60.0

# 进程内计数表上限，防止长时间运行后无界增长（超出时淘汰最旧条目）。
_MAX_TRACKED_KEYS = 10_000


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class SubmitTurnRateLimiter:
    """按 ``(tenant_id, actor_id)`` 的进程内滑动窗口限流器。"""

    def __init__(
        self,
        *,
        limit: int = DEFAULT_SUBMIT_LIMIT,
        window_seconds: float = DEFAULT_SUBMIT_WINDOW_SECONDS,
    ):
        self._limit = limit
        self._window_seconds = window_seconds
        self._hits: OrderedDict[tuple[uuid.UUID, uuid.UUID], list[float]] = (
            OrderedDict()
        )

    def acquire(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        now: float | None = None,
    ) -> RateLimitDecision:
        """记录一次提交尝试；超限则拒绝并给出 ``Retry-After`` 秒数。"""
        current = time.monotonic() if now is None else now
        key = (tenant_id, actor_id)
        cutoff = current - self._window_seconds
        window = [stamp for stamp in self._hits.get(key, []) if stamp > cutoff]
        if len(window) >= self._limit:
            oldest = min(window)
            retry_after = max(1, int(oldest + self._window_seconds - current) + 1)
            self._hits[key] = window
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
        window.append(current)
        self._hits[key] = window
        self._hits.move_to_end(key)
        while len(self._hits) > _MAX_TRACKED_KEYS:
            self._hits.popitem(last=False)
        return RateLimitDecision(allowed=True, retry_after_seconds=0)

    def reset(self) -> None:
        """清空计数（测试与显式运维复位使用）。"""
        self._hits.clear()


# 端点使用的进程级单例：与 router 同生命周期。
submit_turn_rate_limiter = SubmitTurnRateLimiter()
