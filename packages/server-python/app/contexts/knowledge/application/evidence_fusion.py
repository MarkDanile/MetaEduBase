"""`EvidenceFusion` — REQ-010 多源证据融合。

- `EvidenceFusion` Protocol: P1 SimpleFrequencyFusion 实现 + RRFFusion 占位。
- `SimpleFrequencyFusion` 沿用现有 `FrequencyFusion` 行为（按命中通道数 +
  best score 排序），但输入/输出升级到 `EvidenceItem`。
- `RRFFusion` 通用实现：按通道排名累计 `1/(k+rank)`；P2 调优 k 值与通道权重。
- `channels` 字段聚合去重 + 排序（便于 assertion / UI 渲染稳定）。

P2 / P3 替换 Neo4j / Milvus / Qdrant / Elasticsearch 时，本模块不变 — fusion
只关心 `EvidenceItem` 列表，不关心底层召回是 SQL / pgvector / tsvector 还是
图数据库。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.contexts.knowledge.domain.evidence import EvidenceItem


@runtime_checkable
class EvidenceFusion(Protocol):
    """REQ-010 证据融合契约。

    实现者必须严格按本 Protocol 形参命名（不依赖下划线前缀做兼容），
    下游契约测试 `test_chunk_retriever_contract.py` 等用
    `set(sig.parameters)` 与本 Protocol 严格对齐。
    """

    def fuse(
        self,
        channel_results: dict[str, list[EvidenceItem]],
        top_k: int = 10,
    ) -> list[EvidenceItem]: ...


class SimpleFrequencyFusion:
    """P1 简单频率融合：按命中通道数 + best score 排序。

    沿用 `FrequencyFusion` (knowledge context) 行为，输出从 `RecallResult`
    升级为 `EvidenceItem`。`channels` 字段合并后按字典序排序，UI 渲染稳定。
    """

    def fuse(
        self,
        channel_results: dict[str, list[EvidenceItem]],
        top_k: int = 10,
    ) -> list[EvidenceItem]:
        freq: dict[str, int] = {}
        by_id: dict[str, EvidenceItem] = {}
        best_score: dict[str, float] = {}
        channels: dict[str, set[str]] = {}

        for ch_name, results in channel_results.items():
            for r in results:
                eid = r.evidence_id
                freq[eid] = freq.get(eid, 0) + 1
                channels.setdefault(eid, set()).add(ch_name)

                if eid not in by_id:
                    by_id[eid] = r.model_copy()
                    best_score[eid] = r.score or 0.0
                else:
                    cur = r.score or 0.0
                    if cur > best_score[eid]:
                        best_score[eid] = cur
                        by_id[eid] = r.model_copy()

        sorted_ids = sorted(
            freq,
            key=lambda x: (freq[x], best_score[x]),
            reverse=True,
        )

        fused: list[EvidenceItem] = []
        for eid in sorted_ids[:top_k]:
            item = by_id[eid]
            item.channels = sorted(channels.get(eid, set()))
            item.score = best_score[eid]
            fused.append(item)
        return fused


class RRFFusion:
    """Reciprocal Rank Fusion — P2 调优占位实现。

    公式：`score(e) = sum_over_channels(1 / (k + rank_in_channel))`。
    k=60 是 RRF 原始论文默认；P1 阶段先暴露为可用实现，等 P2 真实样例
    验证再调 k 值与通道权重。
    """

    def __init__(self, k: int = 60) -> None:
        self.k = k

    def fuse(
        self,
        channel_results: dict[str, list[EvidenceItem]],
        top_k: int = 10,
    ) -> list[EvidenceItem]:
        agg_score: dict[str, float] = {}
        by_id: dict[str, EvidenceItem] = {}
        channels: dict[str, set[str]] = {}

        for ch_name, results in channel_results.items():
            for rank, r in enumerate(results, start=1):
                eid = r.evidence_id
                agg_score[eid] = agg_score.get(eid, 0.0) + 1.0 / (self.k + rank)
                channels.setdefault(eid, set()).add(ch_name)
                if eid not in by_id:
                    by_id[eid] = r.model_copy()

        sorted_ids = sorted(agg_score, key=lambda x: agg_score[x], reverse=True)

        fused: list[EvidenceItem] = []
        for eid in sorted_ids[:top_k]:
            item = by_id[eid]
            item.channels = sorted(channels.get(eid, set()))
            item.score = round(agg_score[eid], 6)
            fused.append(item)
        return fused
