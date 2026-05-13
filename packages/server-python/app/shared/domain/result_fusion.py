from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.shared.domain.recall_channel import RecallResult


@runtime_checkable
class ResultFusion(Protocol):
    def fuse(
        self,
        channel_results: dict[str, list[RecallResult]],
        top_k: int = 10,
    ) -> list[RecallResult]: ...
