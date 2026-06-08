
from app.contexts.knowledge.application.fusion_service import FrequencyFusion
from app.shared.domain.recall_channel import RecallResult


def _r(node_id: str, score: float, channel: str) -> RecallResult:
    return RecallResult(
        node_id=node_id, title=f"title-{node_id}", description=None,
        domain="smart_manufacturing", level="course",
        score=score, channel=channel, path=None,
    )


def test_fuse_merges_duplicate_node_id_across_channels():
    fusion = FrequencyFusion()
    channel_results = {
        "vector":   [_r("n1", 0.9, "vector"),   _r("n2", 0.5, "vector")],
        "keyword":  [_r("n1", 0.7, "keyword"),  _r("n3", 0.6, "keyword")],
        "metadata": [_r("n2", 0.8, "metadata")],
    }
    fused = fusion.fuse(channel_results, top_k=10)
    ids = [r.node_id for r in fused]
    # n1 出现 2 次，n2 出现 2 次，n3 出现 1 次；频次降序
    assert ids.index("n1") < ids.index("n3")
    assert ids.index("n2") < ids.index("n3")


def test_fuse_orders_by_frequency_then_best_score():
    fusion = FrequencyFusion()
    channel_results = {
        "vector":   [_r("low", 0.99, "vector")],
        "keyword":  [_r("low", 0.50, "keyword")],
        "metadata": [_r("hi",  0.30, "metadata"), _r("hi", 0.29, "metadata")],
    }
    fused = fusion.fuse(channel_results, top_k=10)
    # low 出现 2 次，hi 出现 2 次，频次并列时按最佳分数降序，low=0.99 > hi=0.30
    assert [r.node_id for r in fused] == ["low", "hi"]


def test_fuse_top_k_truncates_results():
    fusion = FrequencyFusion()
    channel_results = {
        "vector": [_r(f"n{i}", 0.5, "vector") for i in range(5)],
    }
    fused = fusion.fuse(channel_results, top_k=2)
    assert len(fused) == 2
    assert {r.node_id for r in fused} == {"n0", "n1"}


def test_fuse_empty_input_returns_empty_list():
    fusion = FrequencyFusion()
    assert fusion.fuse({}, top_k=10) == []
    assert fusion.fuse({"vector": []}, top_k=10) == []


def test_fuse_channel_field_lists_all_source_channels():
    fusion = FrequencyFusion()
    channel_results = {
        "vector":   [_r("n1", 0.9, "vector")],
        "keyword":  [_r("n1", 0.7, "keyword")],
        "metadata": [_r("n1", 0.6, "metadata")],
    }
    fused = fusion.fuse(channel_results, top_k=5)
    assert len(fused) == 1
    assert fused[0].node_id == "n1"
    channels = set(fused[0].channel.split(","))
    # 三个来源都应被记录（顺序由实现决定，集合相等即可）
    assert channels == {"vector", "keyword", "metadata"}
