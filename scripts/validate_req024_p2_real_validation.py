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
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PYTHON = REPO_ROOT / "packages" / "server-python"
if str(SERVER_PYTHON) not in sys.path:
    sys.path.insert(0, str(SERVER_PYTHON))

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_REQ016_SAMPLES = REPO_ROOT / "scripts" / "validate_real_pg_rag_req016.example.json"
DEFAULT_REQ018_SAMPLES = REPO_ROOT / "scripts" / "validate_real_pg_rag_req018.example.json"
DEFAULT_OUT = (
    REPO_ROOT
    / "docs"
    / "02-delivery-plans"
    / "01-specs"
    / "2026-06-18-req-024-p2-real-validation-report.md"
)


@dataclass
class Question:
    group: str
    question_id: str
    text: str
    expected: dict[str, Any]


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
    graph_edge_chunk_ids: list[str]
    fusion_chunk_ids: list[str]


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


def _load_questions(req016: Path, req018: Path) -> list[Question]:
    questions: list[Question] = []
    for group, path in [("REQ-016", req016), ("REQ-018", req018)]:
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("questions", []):
            expected = {
                k: v
                for k, v in item.items()
                if k not in {"id", "text", "expected_category"}
            }
            questions.append(
                Question(
                    group=group,
                    question_id=item["id"],
                    text=item["text"],
                    expected=expected,
                )
            )
    return questions


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
    return service


def _trace_chunk_ids(items: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for item in items:
        cid = item.get("source_chunk_id") or item.get("chunk_id")
        if cid:
            ids.append(str(cid))
    return ids


async def _run_question(session, tenant_id: str, q: Question, scenario: Scenario, *, allow_llm: bool) -> ScenarioRun:
    from app.contexts.knowledge.application.ai_chat_service import ChatRequest

    service = await _build_service(session, tenant_id, scenario, allow_llm=allow_llm)
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
    graph_edge_chunk_ids = _trace_chunk_ids(graph_edge_items)
    fusion_edge_count = sum(
        1 for item in fusion_topn
        if "graph_edge" in (item.get("channels") or []) or item.get("source_type") == "knowledge_edge"
    )
    packed_edge_count = sum(
        1 for block in packed_blocks
        if "graph_edge" in (block.get("channels") or []) or block.get("source_type") == "knowledge_edge"
    )
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
        final_answer_preview=(result.reply or "")[:800],
        document_sources_count=len(result.document_sources or []),
        graph_edge_retrieval_count=len(graph_edge_items),
        graph_edge_fusion_count=fusion_edge_count,
        graph_edge_packed_count=packed_edge_count,
        graph_edge_chunk_ids=graph_edge_chunk_ids,
        fusion_chunk_ids=_trace_chunk_ids(fusion_topn),
    )


def _json_preview(value: Any, *, limit: int = 260) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text[:limit] + ("..." if len(text) > limit else "")


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


def _render_report(
    *,
    runs: list[ScenarioRun],
    tenant_id: str,
    db_url: str,
    allow_llm: bool,
    started_at: str,
    errors: list[str],
) -> str:
    grouped = _group_runs(runs)
    lines: list[str] = []
    lines.append("# REQ-024 P2 真实验收补强报告")
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
    lines.append("| Query | Scenario | method | confidence | expanded_terms | retrieval_topn | packed_blocks | answer preview |")
    lines.append("|-------|----------|--------|------------|----------------|----------------|---------------|----------------|")
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
    lines.append("")

    lines.append("## 原始 JSON 摘要")
    lines.append("")
    lines.append("```json")
    lines.append(_json_preview([asdict(run) for run in runs], limit=4000))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> int:
    _load_dotenv(REPO_ROOT / ".env")
    _load_dotenv(SERVER_PYTHON / ".env")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import settings

    tenant_id = args.tenant_id or os.environ.get("AI_CHAT_TENANT_ID") or DEFAULT_TENANT_ID
    db_url = os.environ.get("DATABASE_URL") or settings.database_url
    questions = _load_questions(Path(args.req016_samples), Path(args.req018_samples))
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
        ),
        encoding="utf-8",
    )
    if args.json_out:
        json_out = Path(args.json_out)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(_json_preview([asdict(run) for run in runs], limit=1_000_000), encoding="utf-8")
    print(f"report written: {out}")
    if errors:
        print(f"completed with {len(errors)} scenario error(s)", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate_req024_p2_real_validation")
    parser.add_argument("--req016-samples", default=str(DEFAULT_REQ016_SAMPLES))
    parser.add_argument("--req018-samples", default=str(DEFAULT_REQ018_SAMPLES))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--json-out", default="")
    parser.add_argument("--tenant-id", default="")
    parser.add_argument(
        "--allow-llm",
        action="store_true",
        help="Allow sending retrieved context / prompt to the configured LLM provider.",
    )
    return parser


def main() -> int:
    return asyncio.run(_run(_build_parser().parse_args()))


if __name__ == "__main__":
    sys.exit(main())
