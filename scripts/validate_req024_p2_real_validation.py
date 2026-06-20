#!/usr/bin/env python3
"""REQ-024 P2 real validation for Query Understanding and graph_edge recall.

This script is intentionally outside CI. It runs the real AIChatService against
the dev PostgreSQL database and writes a Markdown report. By default it does
not call an external LLM provider; pass --allow-llm for true LLM validation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PYTHON = REPO_ROOT / "packages" / "server-python"
if str(SERVER_PYTHON) not in sys.path:
    sys.path.insert(0, str(SERVER_PYTHON))

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_REQ016_SAMPLES = (
    REPO_ROOT / "tests" / "fixtures" / "rag_validation_samples" / "validate_real_pg_rag_req016.example.json"
)
DEFAULT_REQ018_SAMPLES = (
    REPO_ROOT / "tests" / "fixtures" / "rag_validation_samples" / "validate_real_pg_rag_req018.example.json"
)
DEFAULT_REQ026_SAMPLES = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "rag_validation_samples"
    / "validate_real_pg_rag_req026_weak_recall.example.json"
)
DEFAULT_REQ028_SAMPLES = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "rag_validation_samples"
    / "validate_real_pg_rag_req028_weak_recall_v3.example.json"
)
DEFAULT_OUT = (
    REPO_ROOT
    / "docs"
    / "02-delivery-plans"
    / "01-specs"
    / "2026-06-18-req-024-p2-real-validation-report.md"
)
DEFAULT_REQ026_OUT = (
    REPO_ROOT
    / "docs"
    / "02-delivery-plans"
    / "01-specs"
    / "2026-06-18-req-026-rag-effect-comparison-validation-report.md"
)


@dataclass
class Question:
    group: str
    question_id: str
    text: str
    expected: dict[str, Any]
    expected_keypoints: list["Keypoint"]


@dataclass
class Keypoint:
    term: str
    synonyms: list[str] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class Scenario:
    name: str
    use_hybrid_ner: bool
    use_graph_edge: bool
    rrf_weights: dict[str, float]


@dataclass
class ScenarioRun:
    question_group: str
    question_id: str
    question_text: str
    scenario: str
    query_understanding: dict[str, Any] | None
    retrieval_counts: dict[str, int]
    fusion_topn: list[dict[str, Any]]
    packed_blocks: list[dict[str, Any]]
    prompt_preview: str
    final_answer_preview: str
    document_sources_count: int
    graph_edge_retrieval_count: int
    graph_edge_fusion_count: int
    graph_edge_packed_count: int
    vector_fallback_count: int
    graph_edge_chunk_ids: list[str]
    fusion_chunk_ids: list[str]
    document_sources_titles: list[str]
    keypoint_total: int
    keypoint_hit_count: int
    keypoint_coverage_pct: float
    keypoint_hit_list: list[str]
    # REQ-028: three-metric coverage fields
    keypoint_coverage_pct_substring: float = 0.0
    keypoint_coverage_pct_semantic: float = 0.0
    keypoint_weight_pct_semantic: float = 0.0
    keypoint_llm_judge_pct: float | None = None
    # REQ-030: semantic embedding coverage
    keypoint_semantic_embedding_pct: float = 0.0
    keypoint_semantic_embedding_weight_pct: float = 0.0
    keypoint_semantic_embedding_hit_terms: list[str] = field(default_factory=list)
    keypoint_hit_list_substring: list[str] = field(default_factory=list)
    keypoint_hit_list_semantic: list[str] = field(default_factory=list)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _mask_db_url(url: str) -> str:
    return "***@" + url.split("@", 1)[1] if "@" in url else url


def _parse_keypoint(kp: Any) -> Keypoint:
    """Parse a keypoint entry from JSON.

    Accepts:
    - string: ``"闭包"`` -> Keypoint(term="闭包")
    - dict: ``{"term": "闭包", "synonyms": [...], "weight": 1.0}``
    """
    if isinstance(kp, str):
        return Keypoint(term=kp)
    if isinstance(kp, dict):
        term = kp.get("term")
        if not term:
            raise ValueError(f"keypoint dict missing 'term': {kp!r}")
        synonyms = list(kp.get("synonyms", []) or [])
        weight = float(kp.get("weight", 1.0))
        return Keypoint(term=str(term), synonyms=[str(s) for s in synonyms if s], weight=weight)
    raise ValueError(f"unsupported keypoint type: {type(kp).__name__}")


def _load_questions(req016: Path, req018: Path, req026: Path, req028: Path) -> list[Question]:
    questions: list[Question] = []
    for group, path in [
        ("REQ-016", req016),
        ("REQ-018", req018),
        ("REQ-026", req026),
        ("REQ-028", req028),
    ]:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("questions", []):
            expected = {
                k: v
                for k, v in item.items()
                if k not in {"id", "text", "expected_category", "expected_keypoints"}
            }
            raw_keypoints = item.get("expected_keypoints", []) or []
            keypoints: list[Keypoint] = []
            for kp in raw_keypoints:
                try:
                    keypoints.append(_parse_keypoint(kp))
                except ValueError as exc:
                    print(f"warn: skip keypoint in {group}/{item.get('id')}: {exc}", file=sys.stderr)
            questions.append(
                Question(
                    group=group,
                    question_id=item["id"],
                    text=item["text"],
                    expected=expected,
                    expected_keypoints=keypoints,
                )
            )
    return questions


def _compute_keypoint_coverage(
    answer_preview: str,
    sources_titles: list[str],
    keypoints: list[Keypoint],
) -> tuple[int, list[str], int, float]:
    """Backward-compatible substring coverage (REQ-026/027 baseline)."""
    if not keypoints:
        return 0, [], 0, 0.0
    haystack = (answer_preview or "") + "\n" + "\n".join(sources_titles or [])
    haystack_lower = haystack.lower()
    hit_list: list[str] = []
    for kp in keypoints:
        if not kp.term:
            continue
        if kp.term.lower() in haystack_lower:
            hit_list.append(kp.term)
    total = len([k for k in keypoints if k.term])
    pct = (len(hit_list) / total) if total else 0.0
    return len(hit_list), hit_list, total, pct


def _compute_semantic_coverage(
    answer_preview: str,
    sources_titles: list[str],
    keypoints: list[Keypoint],
) -> dict[str, Any]:
    """REQ-028 semantic coverage: matches term + synonyms, supports per-keypoint weight.

    Returns dict with: hit_count, total, coverage_pct, weight_pct, hit_terms.
    """
    if not keypoints:
        return {
            "hit_count": 0,
            "total": 0,
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
        }
    haystack = ((answer_preview or "") + "\n" + "\n".join(sources_titles or [])).lower()
    hit_terms: list[str] = []
    total_weight = 0.0
    hit_weight = 0.0
    for kp in keypoints:
        if not kp.term:
            continue
        candidates = [kp.term] + list(kp.synonyms or [])
        if any((c or "").lower() in haystack for c in candidates if c):
            hit_terms.append(kp.term)
            hit_weight += kp.weight
        total_weight += kp.weight
    total = len([k for k in keypoints if k.term])
    coverage_pct = (len(hit_terms) / total) if total else 0.0
    weight_pct = (hit_weight / total_weight) if total_weight else 0.0
    return {
        "hit_count": len(hit_terms),
        "total": total,
        "coverage_pct": round(coverage_pct, 4),
        "weight_pct": round(weight_pct, 4),
        "hit_terms": hit_terms,
    }


# REQ-030 / REQ-031: rate limit embedding API calls (硅流 / Qwen 默认 30 req/min，
# 串行排队避免 429 卡死。Semaphore 控制并发数 = 2 即可保证 ≤ 30 req/min 在 batch 内)。
_EMB_SEMAPHORE = asyncio.Semaphore(2)

# REQ-031: 进程内 embedding 缓存。keypoint (term + synonyms) 文本在同一脚本运行内
# 静态，跨 4 scenarios 完全相同，缓存命中避免重复 HTTP 调用。
# 将 10 样例 × 4 scenarios × ~5 keypoints × ~2 candidates ≈ 440 次调用降至 ~140 次。
_EMBEDDING_CACHE: dict[str, list[float]] = {}

# REQ-031: 缓存命中 / miss / 超时降级计数（写报告诊断段）
_EMB_STATS = {"hit": 0, "miss": 0, "timeout": 0, "error": 0}


async def _get_cached_embedding(text: str, embedding_callable) -> list[float] | None:
    """REQ-031: cached embedding with hard timeout + graceful degradation.

    - cache hit: return immediately (no HTTP)
    - cache miss: asyncio.wait_for(embedding_callable(text), timeout=60s)
    - timeout / exception: return None (keypoint marked not hit, no hang)
    - success: write cache + return
    """
    if not text:
        return None
    cached = _EMBEDDING_CACHE.get(text)
    if cached is not None:
        _EMB_STATS["hit"] += 1
        return cached
    _EMB_STATS["miss"] += 1
    try:
        async with _EMB_SEMAPHORE:
            emb = await asyncio.wait_for(embedding_callable(text), timeout=60.0)
    except asyncio.TimeoutError:
        _EMB_STATS["timeout"] += 1
        return None
    except Exception:  # noqa: BLE001
        _EMB_STATS["error"] += 1
        return None
    if emb:
        _EMBEDDING_CACHE[text] = emb
    return emb


async def _compute_semantic_embedding_coverage(
    answer_preview: str,
    sources_titles: list[str],
    keypoints: list[Keypoint],
    embedding_callable,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """REQ-030 semantic embedding coverage: cosine similarity between answer
    embedding and each keypoint's term + synonyms embeddings.

    REQ-031: uses _get_cached_embedding (in-process cache + 60s hard timeout)
    so keypoint embeddings are computed once per script run and reused across
    the 4 scenarios per sample.

    Returns dict with: coverage_pct, weight_pct, hit_terms, per_keypoint.
    """
    if not keypoints or embedding_callable is None:
        return {
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
            "per_keypoint": [],
            "error": "no embedding_callable or empty keypoints",
        }
    answer_text = (answer_preview or "") + "\n" + "\n".join(sources_titles or [])
    if not answer_text.strip():
        return {
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
            "per_keypoint": [],
        }
    answer_emb = await _get_cached_embedding(answer_text, embedding_callable)
    if not answer_emb:
        return {
            "coverage_pct": 0.0,
            "weight_pct": 0.0,
            "hit_terms": [],
            "per_keypoint": [],
            "error": "answer embedding failed (timeout/error/None)",
        }

    import math
    hit_terms: list[str] = []
    per_keypoint: list[dict[str, Any]] = []
    total_weight = 0.0
    hit_weight = 0.0

    for kp in keypoints:
        if not kp.term:
            continue
        candidates = [kp.term] + [s for s in (kp.synonyms or []) if s]
        best_sim = 0.0
        best_text = kp.term
        for cand in candidates:
            cand_emb = await _get_cached_embedding(cand, embedding_callable)
            if not cand_emb or len(cand_emb) != len(answer_emb):
                continue
            # cosine similarity
            dot = sum(a * b for a, b in zip(answer_emb, cand_emb))
            norm_a = math.sqrt(sum(a * a for a in answer_emb))
            norm_c = math.sqrt(sum(b * b for b in cand_emb))
            if norm_a == 0 or norm_c == 0:
                continue
            sim = dot / (norm_a * norm_c)
            if sim > best_sim:
                best_sim = sim
                best_text = cand
        hit = best_sim >= threshold
        per_keypoint.append({
            "term": kp.term,
            "best_match": best_text,
            "similarity": round(best_sim, 4),
            "hit": hit,
            "weight": kp.weight,
        })
        if hit:
            hit_terms.append(kp.term)
            hit_weight += kp.weight
        total_weight += kp.weight

    total = len([k for k in keypoints if k.term])
    coverage_pct = (len(hit_terms) / total) if total else 0.0
    weight_pct = (hit_weight / total_weight) if total_weight else 0.0
    return {
        "coverage_pct": round(coverage_pct, 4),
        "weight_pct": round(weight_pct, 4),
        "hit_terms": hit_terms,
        "per_keypoint": per_keypoint,
    }


def _compute_llm_judge_coverage(
    answer_preview: str,
    keypoints: list[Keypoint],
    llm_callable,
) -> dict[str, Any] | None:
    """Sync placeholder. Real implementation is the async variant below; this
    exists only so legacy callers that import the sync name still resolve.
    Use ``await _compute_llm_judge_coverage_async(...)`` instead.
    """
    return None


async def _compute_llm_judge_coverage_async(
    answer_preview: str,
    keypoints: list[Keypoint],
    llm_callable,
) -> dict[str, Any] | None:
    """Async LLM-as-judge coverage (REQ-028).

    Returns None when llm_callable is None (dry-run mode).
    """
    if llm_callable is None or not keypoints:
        return None
    keypoint_terms = [kp.term for kp in keypoints if kp.term]
    if not keypoint_terms:
        return None
    system_prompt = (
        "你是一名严谨的答案评估员。给定一段 AI 回答和一组关键事实，"
        "判断关键事实在回答中是否被覆盖。忽略同义改写和上下文蕴含，"
        "只判断显式或明确等价表述是否出现。"
        "严格输出 JSON: {\"covered\": [\"事实1\", ...], \"missing\": [\"事实2\", ...], \"score\": 0.0~1.0}。"
        "score = len(covered) / len(全部事实)，范围 [0, 1]。不要输出 JSON 以外内容。"
    )
    user_prompt = (
        f"## 关键事实列表（共 {len(keypoint_terms)} 条）\n"
        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(keypoint_terms))
        + "\n\n## AI 回答\n"
        + (answer_preview or "(空)")
    )
    try:
        raw = await llm_callable(system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "coverage_pct": None}
    if not raw:
        return {"error": "empty llm output", "coverage_pct": None}
    # Parse JSON robustly: find first { ... } block.
    text = str(raw).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"error": "llm output not JSON", "raw": text[:200], "coverage_pct": None}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return {"error": f"json parse: {exc}", "raw": text[:200], "coverage_pct": None}
    score = data.get("score")
    if not isinstance(score, (int, float)):
        score = None
    return {
        "covered": list(data.get("covered", []) or []),
        "missing": list(data.get("missing", []) or []),
        "score": score,
        "coverage_pct": round(float(score), 4) if isinstance(score, (int, float)) else None,
    }
    # Parse JSON robustly: find first { ... } block.
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"error": "llm output not JSON", "raw": text[:200], "coverage_pct": None}
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        return {"error": f"json parse: {exc}", "raw": text[:200], "coverage_pct": None}
    score = data.get("score")
    if not isinstance(score, (int, float)):
        score = None
    return {
        "covered": list(data.get("covered", []) or []),
        "missing": list(data.get("missing", []) or []),
        "score": score,
        "coverage_pct": round(float(score), 4) if isinstance(score, (int, float)) else None,
    }


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


async def _run_question(session, tenant_id: str, q: Question, scenario: Scenario, *, allow_llm: bool) -> ScenarioRun:
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
    semantic_emb = await _compute_semantic_embedding_coverage(
        final_answer_preview,
        sources_titles,
        q.expected_keypoints,
        embedding_callable if allow_llm else None,
        threshold=0.5,
    )
    semantic_emb_pct = float(semantic_emb.get("coverage_pct", 0.0) or 0.0)
    semantic_emb_weight_pct = float(semantic_emb.get("weight_pct", 0.0) or 0.0)
    semantic_emb_hit_terms = list(semantic_emb.get("hit_terms", []) or [])

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


def _render_req026_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
    lift_mode: str = "residual",
) -> tuple[str, dict[str, Any]]:
    """Render REQ-026 weak recall section + collect summary stats."""
    stats = {
        "samples_total": 0,
        "samples_p2_better": 0,
        "samples_p2_worse": 0,
        "samples_p2_neutral": 0,
        "samples_qu_helps": 0,
        "samples_graph_edge_in_packed": 0,
        "samples_graph_edge_positive": 0,
        "data_gaps": [],
        "lift_mode": lift_mode,
    }
    lines: list[str] = []
    lines.append("## REQ-026 弱召回样例关键事实覆盖度对比")
    lines.append("")
    lines.append(f"- **Lift mode**: `{lift_mode}` (REQ-029 redesign: residual = (weighted - baseline) / (1 - baseline))")
    lines.append("")
    lines.append("| Sample | Category | baseline cov | +QU cov | +graph_edge cov | +weighted RRF cov | delta | residual_ratio | 判定 | edge_in_packed |")
    lines.append("|--------|----------|--------------|---------|-----------------|-------------------|-------|----------------|------|----------------|")
    sample_rows = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-026":
            continue
        sample_rows += 1
        stats["samples_total"] += 1
        baseline = scenario_runs.get("baseline_rule_no_edge")
        qu = scenario_runs.get("query_understanding")
        edge = scenario_runs.get("graph_edge")
        weighted = scenario_runs.get("weighted_rrf")
        baseline_cov = baseline.keypoint_coverage_pct if baseline else 0.0
        qu_cov = qu.keypoint_coverage_pct if qu else 0.0
        edge_cov = edge.keypoint_coverage_pct if edge else 0.0
        weighted_cov = weighted.keypoint_coverage_pct if weighted else 0.0
        lift = _compute_lift_metrics(baseline_cov, weighted_cov, mode=lift_mode)
        delta = lift["delta"]
        residual_ratio = lift["residual_ratio"]
        verdict = lift["verdict"]
        if verdict == "正向":
            stats["samples_p2_better"] += 1
        elif verdict == "退化":
            stats["samples_p2_worse"] += 1
        else:
            stats["samples_p2_neutral"] += 1
        if (qu_cov - baseline_cov) >= 0.3:
            stats["samples_qu_helps"] += 1
        edge_packed = weighted.graph_edge_packed_count if weighted else 0
        if edge_packed > 0:
            stats["samples_graph_edge_in_packed"] += 1
            if verdict == "正向":
                stats["samples_graph_edge_positive"] += 1
        residual_str = (
            f"{residual_ratio:+.2f}" if residual_ratio is not None else "-"
        )
        lines.append(
            f"| {qid} | {group} | {baseline_cov:.2f} | {qu_cov:.2f} | "
            f"{edge_cov:.2f} | {weighted_cov:.2f} | {delta:+.2f} | {residual_str} | {verdict} | {edge_packed} |"
        )
    lines.append("")
    if sample_rows == 0:
        lines.append("- 本次未加载任何 REQ-026 弱召回样例，请检查 `--weak-recall-samples` 路径。")
        lines.append("")

    lines.append("### 自动比较结论")
    lines.append("")
    lines.append("- **机制层** (代码能力已接入): REQ-026 样例通过 `validate_req024_p2_real_validation.py` "
                 "脚本与 4 个 scenario (`baseline_rule_no_edge` / `query_understanding` / `graph_edge` / "
                 "`weighted_rrf`) 完成执行。")
    lines.append(
        f"- **prompt 层** (evidence 已进入 prompt): REQ-026 样例中 `graph_edge_in_packed > 0` 的样例数 = "
        f"`{stats['samples_graph_edge_in_packed']}` / `{stats['samples_total']}`。"
    )
    lines.append(
        f"- **质量层** (真实 LLM 回答覆盖度提升): P2 完整链路相对 baseline 覆盖度提升 >= 30% 的样例数 = "
        f"`{stats['samples_p2_better']}` / `{stats['samples_total']}`；退化样例数 = "
        f"`{stats['samples_p2_worse']}`。"
    )
    lines.append(
        f"- **Query Understanding 价值**: `+QU` 覆盖度相对 baseline 提升 >= 30% 的样例数 = "
        f"`{stats['samples_qu_helps']}` / `{stats['samples_total']}`。"
    )
    lines.append(
        f"- **graph_edge 价值**: `graph_edge in packed > 0` 且 delta >= 0.3 的样例数 = "
        f"`{stats['samples_graph_edge_positive']}` / `{stats['samples_total']}`。"
    )
    lines.append("")

    lines.append("### 数据缺口与后续任务")
    lines.append("")
    if stats["samples_p2_better"] < 1:
        lines.append("- 当前 dev DB 数据集未能构造足够的弱召回样例来证明 P2 完整链路相对 baseline 提升 >= 30%。")
        lines.append("- 后续任务候选：")
        lines.append("  - `TD-068`: query embedding 为空导致 vector 通道降级为 keyword fallback（已登记，需修）")
        lines.append("  - 新增 `REQ-027` (待登记): 增加 P2 弱召回知识覆盖 — 课程标准 / Python 高级特性 / 跨课程先导关系")
        stats["data_gaps"].append("P2 弱召回样例不足")
    if stats["samples_graph_edge_in_packed"] < 1:
        lines.append("- 当前所有 REQ-026 弱召回样例中 graph_edge 都未进入 packed context。")
        lines.append("- 后续任务候选：")
        lines.append("  - 复核 ContextPacker 对 `knowledge_edge` source block 的 packed 阈值")
        lines.append("  - 增加 `knowledge_edges` 真实样本数据（dev DB backfill）")
        stats["data_gaps"].append("graph_edge 未进入 packed context")
    if stats["samples_qu_helps"] < 1:
        lines.append("- Query Understanding 对自然问法的增益证据不足。")
        lines.append("- 后续任务候选：")
        lines.append("  - 复核 HybridQueryUnderstandingService 在自然问法场景下的 expanded_terms 命中率")
        lines.append("  - 增强规则优先 + LLM 低置信触发的样本多样性")
        stats["data_gaps"].append("Query Understanding 增益不足")
    if not stats["data_gaps"]:
        lines.append("- 当前未发现数据缺口；后续根据样本扩展决定是否新增独立任务。")
    lines.append("")
    return "\n".join(lines), stats


def _render_report(
    *,
    runs: list[ScenarioRun],
    tenant_id: str,
    db_url: str,
    allow_llm: bool,
    started_at: str,
    errors: list[str],
    report_title: str,
    lift_mode: str = "residual",
) -> str:
    grouped = _group_runs(runs)
    lines: list[str] = []
    lines.append(f"# {report_title}")
    lines.append("")
    lines.append("## 环境")
    lines.append("")
    lines.append(f"- Generated At: `{started_at}`")
    lines.append(f"- DB: `{_mask_db_url(db_url)}`")
    lines.append(f"- Tenant: `{tenant_id}`")
    lines.append(f"- External LLM: `{'enabled' if allow_llm else 'disabled-dry-run'}`")
    lines.append(f"- Validation Status: `{'real-llm-run' if allow_llm else 'partial-dry-run-only'}`")
    lines.append("")

    if errors:
        lines.append("## 运行错误")
        lines.append("")
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    lines.append("## REQ-016 Query Understanding 验收")
    lines.append("")
    lines.append("| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | vector fallback | packed_blocks | answer preview |")
    lines.append("|-------|----------|--------|------------|----------------|----------------|-----------------|---------------|----------------|")
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-016":
            continue
        for scenario_name in [
            "baseline_rule_no_edge",
            "query_understanding",
            "graph_edge",
            "weighted_rrf",
        ]:
            run = scenario_runs.get(scenario_name)
            if not run:
                continue
            qu = run.query_understanding or {}
            lines.append(
                f"| {qid} | {scenario_name} | "
                f"{qu.get('method', '-')} | {qu.get('confidence', '-')} | "
                f"{_json_preview(qu.get('expanded_terms', []), limit=160)} | "
                f"{_json_preview(run.retrieval_counts, limit=160)} | "
                f"{run.vector_fallback_count} | "
                f"{len(run.packed_blocks)} | {run.final_answer_preview[:120]} |"
            )
    lines.append("")

    lines.append("## REQ-018 graph_edge 补足样例分析")
    lines.append("")
    lines.append("| Query | graph_edge topN | edge in fusion | edge in packed | edge chunks not in baseline fusion | retrieval counts |")
    lines.append("|-------|-----------------|----------------|----------------|------------------------------------|------------------|")
    fusion_level_supplement_examples = 0
    prompt_level_supplement_examples = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-018":
            continue
        edge = scenario_runs.get("graph_edge")
        weighted = scenario_runs.get("weighted_rrf")
        selected = weighted or edge
        if not selected:
            continue
        supplement_count = _graph_edge_supplement_count(scenario_runs)
        if supplement_count > 0:
            fusion_level_supplement_examples += 1
        if supplement_count > 0 and selected.graph_edge_packed_count > 0:
            prompt_level_supplement_examples += 1
        lines.append(
            f"| {qid} | {selected.graph_edge_retrieval_count} | "
            f"{selected.graph_edge_fusion_count} | {selected.graph_edge_packed_count} | "
            f"{supplement_count} | {_json_preview(selected.retrieval_counts, limit=180)} |"
        )
    lines.append("")

    lines.append("## 对比结论")
    lines.append("")
    if not allow_llm:
        lines.append("- 本报告以 `External LLM: disabled-dry-run` 生成，不能作为最终真实效果验收通过证据。")
        lines.append("- dry-run 只证明脚本、DB 链路、召回 diagnostics 和报告结构可复跑。")
        lines.append("- dry-run 下的 Query Understanding 使用脚本内 fake provider，不代表真实 LLM 解析质量。")
    else:
        lines.append("- 本报告启用了外部 LLM，可用于 REQ-016 / REQ-018 的真实效果验收判断。")
    vector_fallback_total = sum(run.vector_fallback_count for run in runs)
    lines.append(
        f"- vector fallback trace count: `{vector_fallback_total}` "
        "(大于 0 表示 vector 通道结果来自 keyword fallback，不代表真实语义向量召回)。"
    )
    lines.append(
        f"- graph_edge fusion-level supplement examples: `{fusion_level_supplement_examples}` "
        "(只表示 graph_edge 召回的新 chunk 进入 fusion 阶段)。"
    )
    lines.append(
        f"- graph_edge prompt-level supplement examples: `{prompt_level_supplement_examples}` "
        "(REQ-024 AC-2 的强验收应以进入 packed context / prompt 并改善最终回答为准)。"
    )
    if prompt_level_supplement_examples < 2:
        lines.append(
            "- 结论：graph_edge 已能补足 fusion 候选，但尚未证明进入最终 prompt；"
            "需要登记后续数据 / 权重 / context packer 任务。"
        )
    elif not allow_llm:
        lines.append(
            "- 结论：graph_edge 已在 dry-run 中满足至少 2 个样例进入 packed context；"
            "仍需真实 LLM provider 验收最终回答改善。"
        )
    else:
        lines.append(
            "- 结论：本报告已完成真实 LLM provider run；prompt-level 是否达标可由 "
            "`graph_edge prompt-level supplement examples` 判断，最终回答是否改善仍需结合 "
            "baseline / graph_edge / weighted_rrf 的 answer preview 做人工或自动质量比较。"
        )
    lines.append("")

    lines.append("## 原始 JSON 摘要")
    lines.append("")
    lines.append("```json")
    lines.append(_json_preview([_compact_run(run) for run in runs], limit=4000))
    lines.append("```")
    lines.append("")

    # REQ-026 section (added in REQ-026 extension)
    if any(run.question_group == "REQ-026" for run in runs):
        req026_section, req026_stats = _render_req026_section(runs, grouped, lift_mode=lift_mode)
        lines.append(req026_section)
        lines.append("")

    # REQ-028 section (three-metric comparison)
    if any(run.question_group == "REQ-028" for run in runs):
        req028_section = _render_req028_section(runs, grouped, lift_mode=lift_mode)
        lines.append(req028_section)
        lines.append("")

    # REQ-030 section (semantic embedding + LLM-as-judge)
    if any(run.question_group == "REQ-028" for run in runs) and any(
        run.keypoint_semantic_embedding_pct > 0.0 or run.keypoint_llm_judge_pct is not None
        for run in runs
    ):
        req030_section = _render_req030_section(runs, grouped)
        lines.append(req030_section)
        lines.append("")

    return "\n".join(lines)


def _render_req028_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
    lift_mode: str = "residual",
) -> str:
    """REQ-028: render three-metric coverage (substring / semantic / llm_judge)."""
    lines: list[str] = []
    lines.append("## REQ-028 三口径覆盖度对比")
    lines.append("")
    lines.append(f"- **Lift mode**: `{lift_mode}` (REQ-029 redesign)")
    lines.append("")
    lines.append("| Sample | Scenario | substring cov | semantic cov | weight cov | llm_judge cov | semantic 命中明细 |")
    lines.append("|--------|----------|---------------|--------------|------------|---------------|-------------------|")
    rows = 0
    semantic_above_threshold = 0
    semantic_lift_threshold = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        for scenario_name in [
            "baseline_rule_no_edge",
            "query_understanding",
            "graph_edge",
            "weighted_rrf",
        ]:
            run = scenario_runs.get(scenario_name)
            if not run:
                continue
            rows += 1
            judge_str = (
                f"{run.keypoint_llm_judge_pct:.2f}"
                if isinstance(run.keypoint_llm_judge_pct, (int, float))
                else "-"
            )
            sem_terms = ",".join(run.keypoint_hit_list_semantic[:5]) or "-"
            lines.append(
                f"| {qid} | {scenario_name} | "
                f"{run.keypoint_coverage_pct_substring:.2f} | "
                f"{run.keypoint_coverage_pct_semantic:.2f} | "
                f"{run.keypoint_weight_pct_semantic:.2f} | "
                f"{judge_str} | "
                f"{sem_terms} |"
            )
    lines.append("")
    # Per-sample summary (delta on semantic metric)
    lines.append("### REQ-028 per-sample summary (semantic metric)")
    lines.append("")
    lines.append("| Sample | baseline sem | weighted sem | delta | residual_ratio | 判定 (sem) | edge_in_packed |")
    lines.append("|--------|--------------|--------------|-------|----------------|-------------|----------------|")
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        baseline = scenario_runs.get("baseline_rule_no_edge")
        weighted = scenario_runs.get("weighted_rrf")
        if not baseline or not weighted:
            continue
        baseline_sem = baseline.keypoint_coverage_pct_semantic
        weighted_sem = weighted.keypoint_coverage_pct_semantic
        lift = _compute_lift_metrics(baseline_sem, weighted_sem, mode=lift_mode)
        delta = lift["delta"]
        residual_ratio = lift["residual_ratio"]
        verdict = lift["verdict"]
        if weighted_sem >= 0.5:
            semantic_above_threshold += 1
        if verdict == "正向":
            semantic_lift_threshold += 1
        residual_str = (
            f"{residual_ratio:+.2f}" if residual_ratio is not None else "-"
        )
        lines.append(
            f"| {qid} | {baseline_sem:.2f} | "
            f"{weighted_sem:.2f} | {delta:+.2f} | {residual_str} | {verdict} | "
            f"{weighted.graph_edge_packed_count} |"
        )
    lines.append("")
    lines.append("### REQ-028 三口径决策依据")
    lines.append("")
    lines.append("- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致；保留向后兼容。")
    lines.append("- **semantic 口径 (主验收)**: term + synonyms 集合匹配，命中权重 1.0，修饰词权重 ≤0.5。")
    lines.append("- **weight 口径 (semantic 加权)**: 按 Keypoint.weight 加权后的覆盖率；用于区分核心词与修饰词。")
    lines.append("- **llm_judge 口径 (secondary signal)**: 由 LLM-as-judge 评估，仅在 `--allow-llm` 模式下生效；不作为唯一判定。")
    lines.append("- **lift 口径 (REQ-029 阈值)**: residual_ratio = (weighted - baseline) / (1 - baseline)，解决 baseline 接近上限时绝对 delta 失去判别力的问题。")
    lines.append("- **决策规则**: 当 semantic 与 substring 不一致时（如 semantic ≥ 0.50 但 substring = 0），优先看 semantic；语义匹配覆盖更准确反映真实命中。")
    lines.append("")
    lines.append(f"- **AC-4 (semantic ≥ 0.50)**: `{semantic_above_threshold}` 样例达标（独立看 weighted scenario）")
    lines.append(f"- **AC-5 (semantic lift >= 0.30 in `{lift_mode}` mode)**: `{semantic_lift_threshold}` 样例达标")
    if lift_mode == "residual" and semantic_lift_threshold < 4:
        lines.append("- **未达成**: AC-5 residual 模式仍不达 4/10。已登记 REQ-030 接力。")
    lines.append("")
    return "\n".join(lines)


def _render_req030_section(
    runs: list[ScenarioRun],
    grouped: dict[tuple[str, str], dict[str, ScenarioRun]],
) -> str:
    """REQ-030: render semantic embedding + LLM-as-judge four-metric comparison.

    Per-sample matrix: substring / semantic / semantic embedding / LLM-as-judge
    coverage. Plus Spearman correlation between semantic embedding and LLM-as-judge.
    """
    lines: list[str] = []
    lines.append("## REQ-030 新口径对比（semantic embedding + LLM-as-judge）")
    lines.append("")
    # REQ-031: embedding cache stats (hit / miss / timeout / error)
    total_emb = sum(_EMB_STATS.values())
    if total_emb > 0:
        lines.append(
            f"> REQ-031 embedding cache: hit=`{_EMB_STATS['hit']}` miss=`{_EMB_STATS['miss']}` "
            f"timeout=`{_EMB_STATS['timeout']}` error=`{_EMB_STATS['error']}` (total=`{total_emb}`)"
        )
        lines.append("")
    lines.append("| Sample | Scenario | substring cov | semantic cov | semantic_emb cov | semantic_emb weight | LLM-as-judge cov |")
    lines.append("|--------|----------|----------------|--------------|--------------------|----------------------|-------------------|")
    sem_emb_pairs: list[tuple[float, float]] = []
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        for scenario_name in [
            "baseline_rule_no_edge",
            "query_understanding",
            "graph_edge",
            "weighted_rrf",
        ]:
            run = scenario_runs.get(scenario_name)
            if not run:
                continue
            judge_str = (
                f"{run.keypoint_llm_judge_pct:.2f}"
                if isinstance(run.keypoint_llm_judge_pct, (int, float))
                else "-"
            )
            lines.append(
                f"| {qid} | {scenario_name} | "
                f"{run.keypoint_coverage_pct_substring:.2f} | "
                f"{run.keypoint_coverage_pct_semantic:.2f} | "
                f"{run.keypoint_semantic_embedding_pct:.2f} | "
                f"{run.keypoint_semantic_embedding_weight_pct:.2f} | "
                f"{judge_str} |"
            )
            if isinstance(run.keypoint_llm_judge_pct, (int, float)):
                sem_emb_pairs.append(
                    (run.keypoint_semantic_embedding_pct, run.keypoint_llm_judge_pct)
                )
    lines.append("")

    # Spearman correlation between semantic_emb and llm_judge
    if len(sem_emb_pairs) >= 3:
        try:
            from scipy.stats import spearmanr  # type: ignore
            xs, ys = zip(*sem_emb_pairs)
            rho, _ = spearmanr(xs, ys)
            rho_str = f"{rho:.3f}"
        except ImportError:
            # fallback: simple Pearson
            n = len(sem_emb_pairs)
            mx = sum(p[0] for p in sem_emb_pairs) / n
            my = sum(p[1] for p in sem_emb_pairs) / n
            num = sum((p[0] - mx) * (p[1] - my) for p in sem_emb_pairs)
            den_a = sum((p[0] - mx) ** 2 for p in sem_emb_pairs) ** 0.5
            den_b = sum((p[1] - my) ** 2 for p in sem_emb_pairs) ** 0.5
            rho = num / (den_a * den_b) if den_a * den_b > 0 else 0.0
            rho_str = f"{rho:.3f} (Pearson fallback, scipy unavailable)"
    else:
        rho = 0.0
        rho_str = "n/a"
    lines.append("### REQ-030 双口径一致性")
    lines.append("")
    lines.append(
        f"- semantic embedding vs LLM-as-judge Spearman correlation: `{rho_str}` (n={len(sem_emb_pairs)})"
    )
    lines.append("- AC-5 (semantic embedding delta ≥ 0.30) threshold: 见下方 per-sample summary")
    lines.append("")

    # Per-sample summary (semantic embedding delta)
    lines.append("### REQ-030 per-sample summary (semantic embedding metric)")
    lines.append("")
    lines.append("| Sample | baseline sem_emb | weighted sem_emb | delta | 判定 (sem_emb) | LLM-judge delta | 判定 (judge) |")
    lines.append("|--------|------------------|------------------|-------|-----------------|-----------------|----------------|")
    sem_emb_above = 0
    sem_emb_lift = 0
    judge_lift = 0
    for (group, qid), scenario_runs in grouped.items():
        if group != "REQ-028":
            continue
        baseline = scenario_runs.get("baseline_rule_no_edge")
        weighted = scenario_runs.get("weighted_rrf")
        if not baseline or not weighted:
            continue
        delta = weighted.keypoint_semantic_embedding_pct - baseline.keypoint_semantic_embedding_pct
        if delta >= 0.30:
            verdict_se = "正向"
            sem_emb_lift += 1
        elif delta <= -0.30:
            verdict_se = "退化"
        else:
            verdict_se = "中性"
        if weighted.keypoint_semantic_embedding_pct >= 0.5:
            sem_emb_above += 1
        if (
            isinstance(baseline.keypoint_llm_judge_pct, (int, float))
            and isinstance(weighted.keypoint_llm_judge_pct, (int, float))
        ):
            judge_delta = weighted.keypoint_llm_judge_pct - baseline.keypoint_llm_judge_pct
            if judge_delta >= 0.30:
                verdict_j = "正向"
                judge_lift += 1
            elif judge_delta <= -0.30:
                verdict_j = "退化"
            else:
                verdict_j = "中性"
        else:
            judge_delta = 0.0
            verdict_j = "-"
        lines.append(
            f"| {qid} | {baseline.keypoint_semantic_embedding_pct:.2f} | "
            f"{weighted.keypoint_semantic_embedding_pct:.2f} | {delta:+.2f} | {verdict_se} | "
            f"{judge_delta:+.2f} | {verdict_j} |"
        )
    lines.append("")
    lines.append("### REQ-030 三口径决策依据")
    lines.append("")
    lines.append("- **substring 口径 (历史基线)**: 与 REQ-026/027 报告一致。子串匹配，**不能识别 LLM 同义改写**——这是 REQ-028 v3 重跑后 AC 退步的根因。")
    lines.append("- **semantic 口径 (REQ-028)**: term + synonyms 子串匹配集合，weight 加权。")
    lines.append("- **semantic embedding 口径 (REQ-030, 主验收)**: 硅流 embedding 计算 answer 与 keypoint 余弦相似度，threshold 0.5 命中。**能识别同义改写**。")
    lines.append("- **LLM-as-judge 口径 (REQ-028+030 secondary signal)**: LLM 评估 answer 与 keypoints 覆盖度，输出 JSON。仅在 `--allow-llm` 启用。")
    lines.append("- **决策规则**: 在真 vector 召回下，substring / semantic 口径系统性低估 P2 长链能力；semantic embedding 是主验收口径，LLM-as-judge 是双口径一致性验证。")
    lines.append("")
    lines.append(f"- **AC-4 (semantic_emb ≥ 0.50)**: `{sem_emb_above}` 样例达标")
    lines.append(f"- **AC-5 (semantic_emb lift >= 0.30)**: `{sem_emb_lift}` 样例达标")
    lines.append(f"- **AC-5 (LLM-judge lift >= 0.30)**: `{judge_lift}` 样例达标 (secondary signal)")
    if sem_emb_lift < 4:
        lines.append("- **未达成**: AC-5 semantic embedding 模式仍不达 4/10。已登记 REQ-031 接力。")
    lines.append("")
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> int:
    _load_dotenv(REPO_ROOT / ".env")
    _load_dotenv(SERVER_PYTHON / ".env")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import settings

    tenant_id = args.tenant_id or os.environ.get("AI_CHAT_TENANT_ID") or DEFAULT_TENANT_ID
    db_url = os.environ.get("DATABASE_URL") or settings.database_url
    questions = _load_questions(
        Path(args.req016_samples),
        Path(args.req018_samples),
        Path(args.weak_recall_samples),
        Path(getattr(args, "req028_samples", DEFAULT_REQ028_SAMPLES)),
    )
    if args.limit and args.limit > 0:
        questions = questions[: args.limit]
    scenarios = _default_scenarios()
    started_at = datetime.now().astimezone().isoformat()
    errors: list[str] = []
    runs: list[ScenarioRun] = []

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            for q in questions:
                for scenario in scenarios:
                    try:
                        runs.append(
                            await _run_question(
                                session,
                                tenant_id,
                                q,
                                scenario,
                                allow_llm=args.allow_llm,
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(
                            f"{q.group}/{q.question_id}/{scenario.name}: "
                            f"{type(exc).__name__}: {exc}"
                        )
    finally:
        await engine.dispose()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _render_report(
            runs=runs,
            tenant_id=tenant_id,
            db_url=db_url,
            allow_llm=args.allow_llm,
            started_at=started_at,
            errors=errors,
            report_title=args.report_title,
            lift_mode=getattr(args, "lift_mode", "residual"),
        ),
        encoding="utf-8",
    )
    if args.json_out:
        json_out = Path(args.json_out)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps([asdict(run) for run in runs], ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    print(f"report written: {out}")
    if errors:
        print(f"completed with {len(errors)} scenario error(s)", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate_req024_p2_real_validation")
    parser.add_argument("--req016-samples", default=str(DEFAULT_REQ016_SAMPLES))
    parser.add_argument("--req018-samples", default=str(DEFAULT_REQ018_SAMPLES))
    parser.add_argument("--weak-recall-samples", default=str(DEFAULT_REQ026_SAMPLES))
    parser.add_argument("--req028-samples", default=str(DEFAULT_REQ028_SAMPLES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--json-out", default="")
    parser.add_argument("--tenant-id", default="")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of samples (0 = no limit)")
    parser.add_argument("--report-title", default="REQ-024 P2 真实验收补强报告")
    parser.add_argument(
        "--allow-llm",
        action="store_true",
        help="Allow sending retrieved context / prompt to the configured LLM provider.",
    )
    parser.add_argument(
        "--lift-mode",
        choices=["residual", "absolute"],
        default="residual",
        help="REQ-029 AC-5 threshold mode: 'residual' (default, (weighted - baseline) / (1 - baseline)) or 'absolute' (REQ-026/028 baseline, weighted - baseline).",
    )
    return parser


def main() -> int:
    return asyncio.run(_run(_build_parser().parse_args()))


if __name__ == "__main__":
    sys.exit(main())
