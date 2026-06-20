"""Scenario execution for REQ-024 P2 real validation.

Split out of the original monolithic script (TD-032 slice 8). Builds the
AIChatService per scenario, runs each question, computes three-metric coverage
via `coverage`, and packs/group_runs/lift helpers consumed by the report.
"""

from __future__ import annotations

import json
from typing import Any

from .coverage import (
    _compute_keypoint_coverage,
    _compute_llm_judge_coverage_async,
    _compute_semantic_coverage,
    _compute_semantic_embedding_coverage,
)
from .models import Question, Scenario, ScenarioRun


def _default_scenarios() -> list[Scenario]:
    return [
        Scenario(
            name="baseline_rule_no_edge",
            use_hybrid_ner=False,
            use_graph_edge=False,
            rrf_weights={"vector": 1.0, "keyword": 1.0, "graph_node": 0.5, "graph_edge": 0.0},
        ),
        Scenario(
            name="query_understanding",
            use_hybrid_ner=True,
            use_graph_edge=False,
            rrf_weights={"vector": 1.0, "keyword": 1.0, "graph_node": 0.5, "graph_edge": 0.0},
        ),
        Scenario(
            name="graph_edge",
            use_hybrid_ner=True,
            use_graph_edge=True,
            rrf_weights={"vector": 1.0, "keyword": 1.0, "graph_node": 0.5, "graph_edge": 0.5},
        ),
        # REQ-034: graph_edge weight sweep (use_graph_edge=True, varying weight).
        # Brackets the default 0.5 to evaluate whether lowering the weight is
        # a meaningful lever. Retrieval-layer metrics only (no LLM needed).
        Scenario(
            name="graph_edge_w03",
            use_hybrid_ner=True,
            use_graph_edge=True,
            rrf_weights={"vector": 1.0, "keyword": 1.0, "graph_node": 0.5, "graph_edge": 0.3},
        ),
        Scenario(
            name="graph_edge_w07",
            use_hybrid_ner=True,
            use_graph_edge=True,
            rrf_weights={"vector": 1.0, "keyword": 1.0, "graph_node": 0.5, "graph_edge": 0.7},
        ),
        Scenario(
            name="weighted_rrf",
            use_hybrid_ner=True,
            use_graph_edge=True,
            rrf_weights={"vector": 1.0, "keyword": 1.0, "graph_node": 0.8, "graph_edge": 1.2},
        ),
    ]


def _fake_query_understanding_response(query: str) -> str:
    mapping = {
        "Python 函数的参数": ["Python", "函数", "参数", "默认参数", "可变参数", "关键字参数"],
        "教学安排": ["教学安排", "教学质量", "教学目标", "教学评价", "课程标准"],
        "模板配置": ["模板", "配置", "字段", "结构化抽取", "schema"],
        "电子信息专业课程": ["电子信息", "专业", "课程"],
        "先导知识": ["先导知识", "前置能力", "知识基础", "课程关系"],
        "返回值": ["Python", "函数", "参数", "返回值", "函数定义"],
    }
    terms: list[str] = []
    for key, value in mapping.items():
        if key in query:
            terms.extend(value)
    if not terms:
        terms = [query]
    return json.dumps(
        {
            "method": "llm",
            "confidence": 0.75,
            "normalized_query": query,
            "core_terms": terms[:3],
            "expanded_terms": terms,
            "entities": [],
            "filters": {},
        },
        ensure_ascii=False,
    )


async def _build_service(session, tenant_id: str, scenario: Scenario, *, allow_llm: bool):
    import uuid

    from app.contexts.document.infrastructure.chunk_repository import ChunkRepository
    from app.contexts.knowledge.application.ai_chat_service import AIChatService
    from app.contexts.knowledge.application.composite_retriever import CompositeChunkRetriever
    from app.contexts.knowledge.application.context_packer import ContextPacker
    from app.contexts.knowledge.application.evidence_fusion import RRFFusion
    from app.contexts.knowledge.application.hybrid_ner_service import HybridQueryUnderstandingService
    from app.contexts.knowledge.application.ner_service import RuleBasedNER
    from app.contexts.knowledge.infrastructure.retrievers.pg_chunk_keyword_retriever import (
        PgChunkKeywordRetriever,
    )
    from app.contexts.knowledge.infrastructure.retrievers.pg_chunk_vector_retriever import (
        PgChunkVectorRetriever,
    )
    from app.contexts.knowledge.infrastructure.retrievers.pg_graph_retriever import (
        PgEdgeRetriever,
        PgGraphRetriever,
    )
    from app.contexts.knowledge.infrastructure.retrievers.pg_metadata_filter import PgMetadataFilter

    if scenario.use_hybrid_ner:
        if allow_llm:
            ner_pipeline = HybridQueryUnderstandingService()
        else:
            ner_pipeline = HybridQueryUnderstandingService(
                llm_provider=lambda _sys, user: _fake_query_understanding_response(user)
            )
    else:
        ner_pipeline = RuleBasedNER()

    service = AIChatService(
        chunk_retriever=CompositeChunkRetriever(
            [PgChunkVectorRetriever(), PgChunkKeywordRetriever()]
        ),
        graph_retriever=PgGraphRetriever(),
        metadata_filter=PgMetadataFilter(),
        evidence_fusion=RRFFusion(channel_weights=scenario.rrf_weights),
        ner_pipeline=ner_pipeline,
        min_evidence_score=0.0,
        context_packer=ContextPacker(ChunkRepository(session), uuid.UUID(str(tenant_id))),
        edge_retriever=PgEdgeRetriever() if scenario.use_graph_edge else None,
    )

    if not allow_llm:
        async def _dry_llm(_system_prompt: str, user_content: str) -> str:
            return (
                "DRY-RUN: external LLM disabled. "
                "This answer is not a real quality signal. "
                f"prompt_chars={len(user_content)}"
            )

        service._call_llm = _dry_llm  # type: ignore[method-assign]
        return service, None, None
    # allow_llm: return service's real _call_llm for LLM-as-judge (REQ-028) and
    # get_embedding for semantic embedding coverage (REQ-030)
    from app.contexts.knowledge.application.embedding_service import get_embedding
    return service, service._call_llm, get_embedding  # type: ignore[method-assign]


def _trace_chunk_ids(items: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for item in items:
        cid = item.get("source_chunk_id") or item.get("chunk_id")
        if cid:
            ids.append(str(cid))
    return ids


async def _run_question(
    session,
    tenant_id: str,
    q: Question,
    scenario: Scenario,
    *,
    allow_llm: bool,
    semantic_emb_threshold: float = 0.5,
) -> ScenarioRun:
    from app.contexts.knowledge.application.ai_chat_service import ChatRequest

    service, llm_callable, embedding_callable = await _build_service(
        session, tenant_id, scenario, allow_llm=allow_llm
    )
    result = await service.chat(
        ChatRequest(message=q.text, context_window=8),
        tenant_id=tenant_id,
        session=session,
    )
    diagnostics = result.diagnostics or {}
    retrieval_topn = diagnostics.get("retrieval_topn", {}) or {}
    fusion_topn = diagnostics.get("fusion_topn", []) or []
    packed_blocks = diagnostics.get("packed_blocks", []) or []
    graph_edge_items = retrieval_topn.get("graph_edge", []) or []
    vector_items = retrieval_topn.get("vector", []) or []
    graph_edge_chunk_ids = _trace_chunk_ids(graph_edge_items)
    fusion_edge_count = sum(
        1 for item in fusion_topn
        if "graph_edge" in (item.get("channels") or []) or item.get("source_type") == "knowledge_edge"
    )
    packed_edge_count = sum(
        1 for block in packed_blocks
        if "graph_edge" in (block.get("channels") or []) or block.get("source_type") == "knowledge_edge"
    )
    final_answer_preview = (result.reply or "")[:800]
    sources_titles: list[str] = []
    for src in (result.document_sources or [])[:10]:
        # `result.document_sources` is a list of `DocumentSource` Pydantic models.
        # Use attribute access (with dict fallback for tests/mocks that pass dicts).
        title = ""
        if hasattr(src, "title"):
            title = getattr(src, "title", "") or ""
        elif isinstance(src, dict):
            title = (
                src.get("title")
                or src.get("source_title")
                or src.get("filename")
                or ""
            )
        if title:
            sources_titles.append(str(title))

    # REQ-028 three-metric coverage
    sub_hit, sub_list, kp_total, sub_pct = _compute_keypoint_coverage(
        final_answer_preview,
        sources_titles,
        q.expected_keypoints,
    )
    sem = _compute_semantic_coverage(
        final_answer_preview,
        sources_titles,
        q.expected_keypoints,
    )
    judge = await _compute_llm_judge_coverage_async(
        final_answer_preview,
        q.expected_keypoints,
        llm_callable,
    )
    judge_pct = judge.get("coverage_pct") if isinstance(judge, dict) else None

    # REQ-030: semantic embedding coverage (硅流 embedding cosine)
    # Only run when --allow-llm (in dry-run, embedding_callable is None,
    # so embedding math would fail / return 0).
    # REQ-032: threshold is configurable via --semantic-emb-threshold (default 0.5).
    semantic_emb = await _compute_semantic_embedding_coverage(
        final_answer_preview,
        sources_titles,
        q.expected_keypoints,
        embedding_callable if allow_llm else None,
        threshold=semantic_emb_threshold,
    )
    semantic_emb_pct = float(semantic_emb.get("coverage_pct", 0.0) or 0.0)
    semantic_emb_weight_pct = float(semantic_emb.get("weight_pct", 0.0) or 0.0)
    semantic_emb_hit_terms = list(semantic_emb.get("hit_terms", []) or [])
    semantic_emb_continuous_pct = float(semantic_emb.get("continuous_pct", 0.0) or 0.0)

    return ScenarioRun(
        question_group=q.group,
        question_id=q.question_id,
        question_text=q.text,
        scenario=scenario.name,
        query_understanding=diagnostics.get("query_understanding"),
        retrieval_counts={k: len(v or []) for k, v in retrieval_topn.items()},
        fusion_topn=fusion_topn[:10],
        packed_blocks=packed_blocks[:10],
        prompt_preview=diagnostics.get("prompt_preview", "")[:1200],
        final_answer_preview=final_answer_preview,
        document_sources_count=len(result.document_sources or []),
        graph_edge_retrieval_count=len(graph_edge_items),
        graph_edge_fusion_count=fusion_edge_count,
        graph_edge_packed_count=packed_edge_count,
        vector_fallback_count=sum(
            1
            for item in vector_items
            if (item.get("metadata") or {}).get("embedding_fallback") is True
        ),
        graph_edge_chunk_ids=graph_edge_chunk_ids,
        fusion_chunk_ids=_trace_chunk_ids(fusion_topn),
        document_sources_titles=sources_titles,
        keypoint_total=kp_total,
        keypoint_hit_count=sub_hit,
        keypoint_coverage_pct=round(sub_pct, 4),
        keypoint_hit_list=sub_list,
        keypoint_coverage_pct_substring=round(sub_pct, 4),
        keypoint_coverage_pct_semantic=sem["coverage_pct"],
        keypoint_weight_pct_semantic=sem["weight_pct"],
        keypoint_llm_judge_pct=judge_pct,
        keypoint_hit_list_substring=sub_list,
        keypoint_hit_list_semantic=sem["hit_terms"],
        keypoint_semantic_embedding_pct=semantic_emb_pct,
        keypoint_semantic_embedding_weight_pct=semantic_emb_weight_pct,
        keypoint_semantic_embedding_hit_terms=semantic_emb_hit_terms,
        keypoint_semantic_embedding_continuous_pct=semantic_emb_continuous_pct,
    )


def _json_preview(value: Any, *, limit: int = 260) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit] + ("..." if len(text) > limit else "")


def _compact_run(run: ScenarioRun) -> dict[str, Any]:
    return {
        "question_group": run.question_group,
        "question_id": run.question_id,
        "scenario": run.scenario,
        "retrieval_counts": run.retrieval_counts,
        "vector_fallback_count": run.vector_fallback_count,
        "graph_edge_retrieval_count": run.graph_edge_retrieval_count,
        "graph_edge_fusion_count": run.graph_edge_fusion_count,
        "graph_edge_packed_count": run.graph_edge_packed_count,
        "document_sources_count": run.document_sources_count,
        "keypoint_total": run.keypoint_total,
        "keypoint_hit_count": run.keypoint_hit_count,
        "keypoint_coverage_pct": run.keypoint_coverage_pct,
        "keypoint_coverage_pct_substring": run.keypoint_coverage_pct_substring,
        "keypoint_coverage_pct_semantic": run.keypoint_coverage_pct_semantic,
        "keypoint_weight_pct_semantic": run.keypoint_weight_pct_semantic,
        "keypoint_llm_judge_pct": run.keypoint_llm_judge_pct,
        # REQ-030: semantic embedding + LLM-as-judge fields
        "keypoint_semantic_embedding_pct": run.keypoint_semantic_embedding_pct,
        "keypoint_semantic_embedding_weight_pct": run.keypoint_semantic_embedding_weight_pct,
        "keypoint_semantic_embedding_hit_terms": run.keypoint_semantic_embedding_hit_terms,
        # REQ-032: continuous weighted coverage (no threshold binarization)
        "keypoint_semantic_embedding_continuous_pct": run.keypoint_semantic_embedding_continuous_pct,
        "final_answer_preview": run.final_answer_preview[:220],
    }


def _group_runs(runs: list[ScenarioRun]) -> dict[tuple[str, str], dict[str, ScenarioRun]]:
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]] = {}
    for run in runs:
        grouped.setdefault((run.question_group, run.question_id), {})[run.scenario] = run
    return grouped


def _graph_edge_supplement_count(group: dict[str, ScenarioRun]) -> int:
    baseline = group.get("baseline_rule_no_edge")
    edge = group.get("graph_edge") or group.get("weighted_rrf")
    if not baseline or not edge:
        return 0
    baseline_ids = set(baseline.fusion_chunk_ids)
    return len([cid for cid in edge.graph_edge_chunk_ids if cid not in baseline_ids])


def _compute_lift_metrics(baseline: float, weighted: float, mode: str = "residual") -> dict[str, Any]:
    """REQ-029 AC-5 threshold redesign.

    Two modes:
    - absolute: delta = weighted - baseline; verdict by +-0.30 thresholds
    - residual: residual_ratio = (weighted - baseline) / (1 - baseline), clamped to [-1, 1];
                verdict by +-0.30 thresholds; handles baseline=1.0 (no room) and baseline=0.0
                (any positive weighted = 1.0)
    """
    delta = float(weighted) - float(baseline)
    if mode == "absolute":
        verdict = "正向" if delta >= 0.30 else ("退化" if delta <= -0.30 else "中性")
        return {
            "delta": round(delta, 4),
            "residual_ratio": None,
            "verdict": verdict,
            "mode": "absolute",
        }
    # residual mode (REQ-029 default)
    baseline_c = max(0.0, min(1.0, float(baseline)))
    weighted_c = max(0.0, min(1.0, float(weighted)))
    if baseline_c >= 1.0:
        residual = 0.0  # baseline full, no room to improve
    elif baseline_c <= 0.0:
        residual = 1.0 if weighted_c > 0.0 else 0.0  # from zero, any positive = full gain
    else:
        residual = (weighted_c - baseline_c) / (1.0 - baseline_c)
    residual = max(-1.0, min(1.0, residual))
    verdict = "正向" if residual >= 0.30 else ("退化" if residual <= -0.30 else "中性")
    return {
        "delta": round(delta, 4),
        "residual_ratio": round(residual, 4),
        "verdict": verdict,
        "mode": "residual",
    }
