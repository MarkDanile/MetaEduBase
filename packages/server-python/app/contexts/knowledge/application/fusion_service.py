from __future__ import annotations

from app.shared.domain.recall_channel import RecallResult


class FrequencyFusion:
    def fuse(
        self,
        channel_results: dict[str, list[RecallResult]],
        top_k: int = 10,
    ) -> list[RecallResult]:
        freq: dict[str, int] = {}
        by_id: dict[str, RecallResult] = {}
        best_score: dict[str, float] = {}
        channels: dict[str, list[str]] = {}

        for ch_name, results in channel_results.items():
            for r in results:
                nid = r.node_id
                freq[nid] = freq.get(nid, 0) + 1
                if nid not in channels:
                    channels[nid] = []
                channels[nid].append(ch_name)

                if nid not in by_id:
                    by_id[nid] = r
                    best_score[nid] = r.score or 0.0
                else:
                    existing = by_id[nid]
                    merged_channels = list(set((existing.channel or "").split(",") + [ch_name]))
                    existing.channel = ",".join(merged_channels)

                    cur_score = r.score or 0.0
                    if cur_score > best_score[nid]:
                        best_score[nid] = cur_score
                        by_id[nid] = r
                        existing_channels = channels[nid]
                        by_id[nid].channel = ",".join(existing_channels)

        sorted_ids = sorted(
            freq,
            key=lambda x: (freq[x], best_score[x]),
            reverse=True,
        )

        fused: list[RecallResult] = []
        for nid in sorted_ids[:top_k]:
            r = by_id[nid].model_copy()
            r.channel = ",".join(channels.get(nid, []))
            fused.append(r)
        return fused
