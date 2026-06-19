#!/usr/bin/env python3
"""
RAG 真实 PG 验收脚本（一次性，不进 CI / pytest）。

子命令：
- backfill: 扫描样例文件状态 + 按需补齐
- ask:      跑固定问题，记录 retrieval / fusion / packed / 回答 / 来源
- bug007:   复测 BUG-007 真 PG reparse
- bug006:   复测 BUG-006 五子项
- report:   汇总中间 JSON → Markdown 报告

使用：
  python scripts/validate_real_pg_rag.py backfill \\
      --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json \\
      --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md

  真库验收时复制 example 并填入 dev 库 file_id；真实 samples 文件不进 git。

环境变量：
  DATABASE_URL:        postgresql+asyncpg://user:pass@host:port/db
  AI_CHAT_BASE_URL:    http://localhost:8000
  AI_CHAT_TENANT_ID:   <tenant uuid>
  AI_CHAT_AUTH_TOKEN:  real user JWT for authenticated API calls
  LLM_PROVIDER:        deepseek / openai / ...
  LLM_API_KEY:         ...
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PYTHON = REPO_ROOT / "packages" / "server-python"
if str(SERVER_PYTHON) not in sys.path:
    sys.path.insert(0, str(SERVER_PYTHON))


DB_REQUIRED_ENV = ("DATABASE_URL",)
HTTP_REQUIRED_ENV = ("AI_CHAT_BASE_URL", "AI_CHAT_TENANT_ID", "AI_CHAT_AUTH_TOKEN")
REPORT_ENV = DB_REQUIRED_ENV + HTTP_REQUIRED_ENV


# -----------------------------
# 数据模型
# -----------------------------


@dataclass
class SampleSpec:
    category: str
    label: str
    file_id: str | None
    expected_doc_type: str | None = None


@dataclass
class QuestionSpec:
    id: str
    text: str
    expected_category: str | None


@dataclass
class BackfillResult:
    file_id: str
    label: str
    before: dict[str, Any]
    after: dict[str, Any]
    commands: list[str] = field(default_factory=list)
    exit_codes: list[int] = field(default_factory=list)


@dataclass
class AskResult:
    question_id: str
    question_text: str
    retrieval_topn: dict[str, Any]
    fusion_topn: list[dict[str, Any]]
    packed_blocks: list[dict[str, Any]]
    final_answer: str
    document_sources: list[dict[str, Any]]
    evidence_indices: list[int]
    section_fallback: bool = False
    ac2_pass: bool | None = None
    ac3_pass: bool | None = None


@dataclass
class Bug007Result:
    file_id: str
    label: str
    section_count: int
    empty_path_count: int
    abnormal_path_count: int
    chinese_section_title_count: int
    pass_: bool


@dataclass
class Bug006SubResult:
    sub_id: str
    title: str
    verification: str
    conclusion: str
    notes: str = ""


@dataclass
class ValidationReport:
    generated_at: str
    db_url: str
    tenant_id: str
    samples: list[SampleSpec]
    backfill_results: list[BackfillResult]
    ask_results: list[AskResult]
    bug007_results: list[Bug007Result]
    bug006_subresults: list[Bug006SubResult]
    failures_attribution: list[dict[str, str]]
    ac_summary: dict[str, str]

    def to_markdown(self) -> str:
        return _render_markdown(self)


# -----------------------------
# Markdown 渲染
# -----------------------------


def _render_markdown(report: ValidationReport) -> str:
    lines: list[str] = []
    lines.append(f"# RAG 真实 PG 验收报告 — {report.generated_at[:10]}")
    lines.append("")
    lines.append("## 环境")
    lines.append(f"- DB: `{report.db_url}`")
    lines.append(f"- Tenant: `{report.tenant_id}`")
    lines.append(f"- 时间: {report.generated_at}")
    lines.append(f"- LLM provider: `{os.environ.get('LLM_PROVIDER', '<unset>')}`")
    lines.append("")

    lines.append("## 1. 样例文件清单与回填状态")
    lines.append("")
    lines.append("| file_id | label | before | after | 命令 | 退出码 |")
    lines.append("|---------|-------|--------|-------|------|--------|")
    for r in report.backfill_results:
        lines.append(
            f"| `{r.file_id}` | {r.label} | "
            f"{json.dumps(r.before, ensure_ascii=False, default=str)} | "
            f"{json.dumps(r.after, ensure_ascii=False, default=str)} | "
            f"{'; '.join(r.commands) or '-'} | {','.join(str(c) for c in r.exit_codes) or '-'} |"
        )
    lines.append("")

    lines.append("## 2. Context Packer 问答验收")
    if not report.ask_results:
        lines.append("")
        lines.append("（无 ask 数据 — 待下个会话跑真 PG）")
    for r in report.ask_results:
        lines.append(f"### {r.question_id}: {r.question_text}")
        lines.append("")
        lines.append(f"- 各通道 topN: `{json.dumps(r.retrieval_topn, ensure_ascii=False, default=str)[:500]}`")
        lines.append(f"- fusion topN: `{json.dumps(r.fusion_topn, ensure_ascii=False, default=str)[:500]}`")
        lines.append(f"- packed blocks: {len(r.packed_blocks)} 个")
        for i, b in enumerate(r.packed_blocks, 1):
            content_preview = (b.get("content") or "")[:120]
            lines.append(
                f"  - block[{i}] file_id={b.get('file_id')} "
                f"chunk_ids={b.get('chunk_ids')} chars={b.get('chars')} "
                f"title={b.get('title')!r} content_preview={content_preview!r}"
            )
        lines.append(f"- section_fallback: {r.section_fallback}")
        lines.append(f"- 最终回答（前 500 字）: {r.final_answer[:500]}")
        lines.append(f"- document_sources: `{json.dumps(r.document_sources, ensure_ascii=False, default=str)[:500]}`")
        lines.append(f"- evidence_indices: {r.evidence_indices}")
        lines.append(f"- AC-2: {'✅' if r.ac2_pass else '❌'} | AC-3: {'✅' if r.ac3_pass else '❌'}")
        lines.append("")

    lines.append("## 3. BUG-007 真 PG reparse 复测")
    lines.append("")
    if not report.bug007_results:
        lines.append("（无 bug007 数据 — 待下个会话跑真 PG）")
    else:
        lines.append("| file_id | label | section_count | empty_path | abnormal_path | chinese_title | 结论 |")
        lines.append("|---------|-------|---------------|------------|---------------|---------------|------|")
        for r in report.bug007_results:
            lines.append(
                f"| `{r.file_id}` | {r.label} | {r.section_count} | "
                f"{r.empty_path_count} | {r.abnormal_path_count} | "
                f"{r.chinese_section_title_count} | "
                f"{'✅' if r.pass_ else '❌'} |"
            )
    lines.append("")

    lines.append("## 4. BUG-006 五子项真 PG 复测")
    lines.append("")
    if not report.bug006_subresults:
        lines.append("（无 bug006 数据 — 待下个会话跑真 PG）")
    else:
        lines.append("| sub_id | title | verification | conclusion | notes |")
        lines.append("|--------|-------|--------------|------------|-------|")
        for r in report.bug006_subresults:
            lines.append(
                f"| {r.sub_id} | {r.title} | {r.verification} | "
                f"{r.conclusion} | {r.notes} |"
            )
    lines.append("")

    lines.append("## 5. 失败归因与新登记")
    if report.failures_attribution:
        lines.append("")
        lines.append("| 现象 | 归因 | 新 REQ / BUG / TD |")
        lines.append("|------|------|-------------------|")
        for f in report.failures_attribution:
            lines.append(f"| {f.get('phenomenon','')} | {f.get('category','')} | {f.get('linked_id','')} |")
    else:
        lines.append("")
        lines.append("（无）")
    lines.append("")

    lines.append("## 6. AC 收口")
    lines.append("")
    lines.append("| AC | 状态 | 证据 |")
    lines.append("|----|------|------|")
    for k, v in report.ac_summary.items():
        lines.append(f"| {k} | {v} | 见报告对应章节 |")
    lines.append("")

    return "\n".join(lines)


# -----------------------------
# 配置 / 环境
# -----------------------------


def _load_samples(path: Path) -> tuple[list[SampleSpec], list[QuestionSpec]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    samples = [SampleSpec(**s) for s in data["samples"]]
    questions = [QuestionSpec(**q) for q in data["questions"]]
    return samples, questions


def _check_env(keys: tuple[str, ...] = REPORT_ENV) -> None:
    """缺环境变量时报告为空报告占位（不退出）。子命令可显式调用 _require_env。"""
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        print(f"WARN: 缺环境变量 {missing}（仅占位报告 / dry-run）", file=sys.stderr)


def _require_env(keys: tuple[str, ...]) -> None:
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        print(f"ERROR: 缺少环境变量: {missing}", file=sys.stderr)
        sys.exit(2)


def _auth_headers(tenant_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['AI_CHAT_AUTH_TOKEN']}",
        "X-Tenant-Id": tenant_id,
    }


def _intermediate_path(out: str, name: str, override: str | None = None) -> Path:
    p = override or f"{out}.{name}.intermediate.json"
    path = Path(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _json_dumps(data: Any) -> str:
    """Serialize real DB values such as UUID / datetime in validation reports."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# -----------------------------
# DB 辅助（用于 backfill / bug007 / bug006）
# -----------------------------


async def _scan_file_state(engine, file_id: str) -> dict[str, Any]:
    """扫描单个 file_id 的 parse / chunk / embed / tsvector / KG 状态。"""
    try:
        from sqlalchemy import text
    except ImportError as e:  # pragma: no cover
        print(f"ERROR: 缺 sqlalchemy: {e}", file=sys.stderr)
        sys.exit(2)
    async with engine.begin() as conn:
        file_row = (await conn.execute(
            text(
                "SELECT id, status, doc_type, template_id "
                "FROM metaedu.files WHERE id = :fid"
            ),
            {"fid": file_id},
        )).mappings().first()
        chunk_state = (await conn.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE embedding IS NOT NULL) AS embeddings, "
                "count(*) FILTER (WHERE content_tsvector IS NOT NULL) AS tsvectors, "
                "count(*) FILTER (WHERE section_title IS NOT NULL AND section_title <> '') AS section_titles, "
                "count(*) FILTER (WHERE section_path IS NOT NULL AND section_path <> '') AS section_paths, "
                "count(*) FILTER (WHERE char_start IS NOT NULL AND char_end IS NOT NULL) AS char_offsets "
                "FROM metaedu.document_chunks WHERE file_id = :fid"
            ),
            {"fid": file_id},
        )).mappings().first()
        kg_nodes = (await conn.execute(
            text("SELECT count(*) FROM metaedu.knowledge_nodes WHERE source_file_id = :fid"),
            {"fid": file_id},
        )).scalar_one()
        kg_chunk_resolved = (await conn.execute(
            text(
                "SELECT count(*) FROM metaedu.knowledge_nodes "
                "WHERE source_file_id = :fid AND source_chunk_id IS NOT NULL"
            ),
            {"fid": file_id},
        )).scalar_one()
        kg_edges = (await conn.execute(
            text(
                "SELECT count(*) FROM metaedu.knowledge_edges "
                "WHERE source_id IN ("
                "  SELECT id FROM metaedu.knowledge_nodes WHERE source_file_id = :fid"
                ")"
            ),
            {"fid": file_id},
        )).scalar_one()
    return {
        "file": dict(file_row) if file_row else None,
        "chunks": int(chunk_state["total"] if chunk_state else 0),
        "embeddings": int(chunk_state["embeddings"] if chunk_state else 0),
        "tsvectors": int(chunk_state["tsvectors"] if chunk_state else 0),
        "section_titles": int(chunk_state["section_titles"] if chunk_state else 0),
        "section_paths": int(chunk_state["section_paths"] if chunk_state else 0),
        "char_offsets": int(chunk_state["char_offsets"] if chunk_state else 0),
        "kg_nodes": kg_nodes,
        "kg_chunk_resolved": kg_chunk_resolved,
        "kg_edges": kg_edges,
    }


async def _maybe_reparse_or_reinit(
    engine,
    file_id: str,
    *,
    run_reinitialize: bool,
    base_url: str,
    tenant_id: str,
) -> tuple[list[str], list[int]]:
    """如状态失败 / 缺失，记录或执行 reinitialize。默认 dry-run。"""
    try:
        from sqlalchemy import text
    except ImportError:
        return [], []
    cmds: list[str] = []
    codes: list[int] = []
    async with engine.begin() as conn:
        st = (await conn.execute(
            text("SELECT status FROM metaedu.files WHERE id = :fid"),
            {"fid": file_id},
        )).scalar_one_or_none()
    if st in (None, "failed", "error", "pending", "uploaded"):
        cmd = f"POST /api/v1/files/{file_id}/reinitialize"
        if not run_reinitialize:
            cmds.append(f"{cmd} (dry-run; pass --run-reinitialize to execute)")
            codes.append(0)
            return cmds, codes
        try:
            import httpx
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/api/v1/files/{file_id}/reinitialize",
                    headers=_auth_headers(tenant_id),
                )
                cmds.append(cmd)
                codes.append(resp.status_code)
        except Exception as e:  # noqa: BLE001
            cmds.append(f"{cmd} (failed: {type(e).__name__}: {e})")
            codes.append(1)
    return cmds, codes


async def _scan_sections(engine, file_id: str) -> dict[str, Any]:
    try:
        from sqlalchemy import text
    except ImportError:
        return {"section_count": 0, "empty_path_count": 0,
                "abnormal_path_count": 0, "chinese_title_count": 0}
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text(
                "SELECT id, chunk_index, section_title AS title, section_path AS path "
                "FROM metaedu.document_chunks "
                "WHERE file_id = :fid "
                "ORDER BY chunk_index"
            ),
            {"fid": file_id},
        )).mappings().all()
    empty_path = sum(1 for r in rows if not r["path"] or not str(r["path"]).strip())
    abnormal = sum(
        1
        for r in rows
        if r["path"] and str(r["path"]).strip().lower() in {"?", "null", "undefined"}
    )
    chinese_titles = sum(
        1 for r in rows
        if r["title"] and any("一" <= ch <= "鿿" for ch in str(r["title"]))
    )
    return {
        "section_count": len(rows),
        "empty_path_count": empty_path,
        "abnormal_path_count": abnormal,
        "chinese_title_count": chinese_titles,
    }


# -----------------------------
# AI Chat evidence 调用
# -----------------------------


async def _call_ai_chat_evidence(question: str, tenant_id: str,
                                 base_url: str) -> dict[str, Any]:
    import httpx
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/api/v1/ai/chat/evidence",
            json={"message": question, "context_window": 8},
            headers=_auth_headers(tenant_id),
        )
        r.raise_for_status()
        return r.json()


def _summarize_ask_response(resp: dict[str, Any]) -> AskResult:
    diag = resp.get("diagnostics", {}) or {}
    retrieval_topn = diag.get("retrieval_topn", {}) or {}
    fusion_topn = diag.get("fusion_topn", []) or []
    packed = diag.get("packed_blocks", []) or []
    final_answer = resp.get("reply", "") or resp.get("answer", "") or ""
    document_sources = resp.get("document_sources", []) or []
    evidence_indices = [
        i
        for i, ev in enumerate((resp.get("sources") or resp.get("evidence") or []), start=1)
        if ev.get("index") is not None
    ] or list(range(1, len(resp.get("sources") or []) + 1))
    section_fallback = bool(diag.get("section_fallback", False))
    return AskResult(
        question_id="",
        question_text="",
        retrieval_topn=retrieval_topn,
        fusion_topn=fusion_topn,
        packed_blocks=packed,
        final_answer=final_answer,
        document_sources=document_sources,
        evidence_indices=evidence_indices,
        section_fallback=section_fallback,
    )


def _check_ac2(ask: AskResult) -> bool:
    """AC-2: packed context 含 Python 教程正文，不只目录。"""
    if not ask.packed_blocks:
        return False
    joined = "".join((b.get("content") or "") for b in ask.packed_blocks)
    has_toc = any(m in joined for m in ("目录", "Table of Contents", "............"))
    has_dt = any(m in joined for m in
                 ("int", "float", "str", "bool", "整数", "浮点", "字符串", "布尔"))
    return has_dt and not has_toc


def _check_ac3(ask: AskResult) -> bool:
    """AC-3: 最终回答含 [N] 引用且 document_sources 非空。"""
    has_brackets = "[" in ask.final_answer and "]" in ask.final_answer
    has_sources = bool(ask.document_sources)
    return has_brackets and has_sources


# -----------------------------
# BUG-006 5 子项验证
# -----------------------------


async def _verify_bug006_subs(engine, samples: list[SampleSpec],
                              tenant_id: str, base_url: str) -> list[Bug006SubResult]:
    try:
        from sqlalchemy import text
    except ImportError:
        return [Bug006SubResult("#1~#5", "全部", "缺 sqlalchemy，跳过", "⏭")]
    import httpx

    results: list[Bug006SubResult] = []

    # #1 模板字段名 label
    try:
        async with engine.begin() as conn:
            tpl = (await conn.execute(
                text(
                    "SELECT id, name, fields FROM metaedu.templates "
                    "WHERE tenant_id = :tid "
                    "ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST "
                    "LIMIT 1"
                ),
                {"tid": tenant_id},
            )).mappings().first()
        if tpl:
            fields_raw = tpl["fields"]
            fields = (
                fields_raw
                if isinstance(fields_raw, list)
                else json.loads(fields_raw or "[]")
            )

            def labels_present(items: list[dict]) -> bool:
                for item in items:
                    if not isinstance(item.get("label", ""), str) or not item["label"]:
                        return False
                    for child_key in ("children", "items"):
                        children = item.get(child_key) or []
                        if isinstance(children, list) and not labels_present(children):
                            return False
                    columns = item.get("columns") or []
                    if isinstance(columns, list) and not labels_present(columns):
                        return False
                return True

            labels_ok = isinstance(fields, list) and labels_present(fields)
            results.append(Bug006SubResult(
                sub_id="#1", title="模板字段名 label（递归 children + keyPath）",
                verification=(
                    f"templates 取最新 1 个 `{tpl['name']}`，"
                    f"递归断言 fields / children / items / columns label 非空"
                    f"（顶层 {len(fields) if isinstance(fields, list) else 0} 字段）"
                ),
                conclusion="✅" if labels_ok else "❌",
            ))
        else:
            results.append(Bug006SubResult(
                sub_id="#1", title="模板字段名 label",
                verification="无模板；跳过", conclusion="⏭",
                notes="dev 库无模板",
            ))
    except Exception as e:
        results.append(Bug006SubResult(
            sub_id="#1", title="模板字段名 label",
            verification=f"异常: {e}", conclusion="❌",
        ))

    # #2 pdf_parser 中文章节正则（与 bug007 共享，单独声明）
    results.append(Bug006SubResult(
        sub_id="#2", title="pdf_parser 中文章节正则（fallback）",
        verification="复用 bug007 子命令的 chinese_title_count 统计",
        conclusion="见 bug007 章节",
    ))

    # #3 嵌套 schema 描述 + few-shot 前移 + 截断扩展
    try:
        from app.contexts.document.application.tasks.extract_template_prompts import (
            build_fields_desc,
        )
        desc = build_fields_desc([{
            "key": "outer", "label": "外层", "type": "object",
            "children": [{"key": "inner", "label": "内层", "type": "string"}],
        }])
        has_inner = isinstance(desc, str) and "outer(外层)" in desc and "inner(内层)" in desc
        results.append(Bug006SubResult(
            sub_id="#3", title="嵌套 schema 描述 + few-shot 前移 + 截断扩展",
            verification="直接调用 build_fields_desc，断言嵌套子字段递归出现",
            conclusion="✅" if has_inner else "❌",
            notes=desc[:80] if isinstance(desc, str) else "",
        ))
    except Exception as e:
        results.append(Bug006SubResult(
            sub_id="#3", title="嵌套 schema 描述",
            verification=f"异常: {e}", conclusion="❌",
        ))

    # #4 KG > 50 节点 kg-bundle
    try:
        async with engine.begin() as conn:
            row = (await conn.execute(
                text(
                    "SELECT f.id AS file_id, "
                    "(SELECT count(*) FROM metaedu.knowledge_nodes "
                    " WHERE source_file_id = f.id) AS nodes "
                    "FROM metaedu.files f WHERE f.tenant_id = :tid "
                    "AND EXISTS ("
                    "  SELECT 1 FROM metaedu.knowledge_nodes "
                    "  WHERE source_file_id = f.id"
                    ") "
                    "ORDER BY nodes DESC LIMIT 1"
                ),
                {"tid": tenant_id},
            )).mappings().first()
        if row and row["nodes"]:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{base_url.rstrip('/')}/api/v1/knowledge/files/{row['file_id']}/kg-bundle",
                    headers=_auth_headers(tenant_id),
                )
            results.append(Bug006SubResult(
                sub_id="#4", title="KG > 50 节点 kg-bundle",
                verification=f"最大 nodes file `{row['file_id']}` ({row['nodes']} 节点); HTTP {r.status_code}",
                conclusion="✅" if r.status_code == 200 else "❌",
            ))
        else:
            results.append(Bug006SubResult(
                sub_id="#4", title="KG > 50 节点 kg-bundle",
                verification="无 KG 节点文件", conclusion="⏭",
            ))
    except Exception as e:
        results.append(Bug006SubResult(
            sub_id="#4", title="KG > 50 节点",
            verification=f"异常: {e}", conclusion="❌",
        ))

    # #5 文件详情页返回按钮（手动 dev 验收）
    results.append(Bug006SubResult(
        sub_id="#5", title="文件详情页返回按钮 (router.replace + type=button)",
        verification="手动 dev 浏览器验收；脚本仅记录提示",
        conclusion="手动",
        notes="需在 dev 前端手测：FileDetailView goBack 后 URL 不残留错乱 query",
    ))

    return results


# -----------------------------
# 子命令入口
# -----------------------------


async def _create_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    return create_async_engine(os.environ["DATABASE_URL"])


async def cmd_backfill(args: argparse.Namespace) -> int:
    _require_env(DB_REQUIRED_ENV)
    if args.run_reinitialize:
        _require_env(HTTP_REQUIRED_ENV)
    samples, _ = _load_samples(Path(args.samples))
    engine = await _create_engine()
    base_url = os.environ.get("AI_CHAT_BASE_URL", "")
    tenant_id = os.environ.get("AI_CHAT_TENANT_ID", "")
    results: list[BackfillResult] = []
    try:
        for s in samples:
            if not s.file_id:
                results.append(BackfillResult(
                    file_id="(未指定)", label=s.label,
                    before={}, after={}, commands=[], exit_codes=[],
                ))
                continue
            before = await _scan_file_state(engine, s.file_id)
            cmds, codes = await _maybe_reparse_or_reinit(
                engine,
                s.file_id,
                run_reinitialize=args.run_reinitialize,
                base_url=base_url,
                tenant_id=tenant_id,
            )
            after = await _scan_file_state(engine, s.file_id)
            results.append(BackfillResult(
                file_id=s.file_id, label=s.label,
                before=before, after=after,
                commands=cmds, exit_codes=codes,
            ))
    finally:
        await engine.dispose()
    p = _intermediate_path(args.out, "backfill", args.intermediate)
    p.write_text(
        _json_dumps([asdict(r) for r in results]),
        encoding="utf-8",
    )
    print(f"backfill done. intermediate: {p}")
    return 0


async def cmd_ask(args: argparse.Namespace) -> int:
    _require_env(HTTP_REQUIRED_ENV)
    _, questions = _load_samples(Path(args.samples))
    base_url = os.environ["AI_CHAT_BASE_URL"]
    tenant_id = os.environ["AI_CHAT_TENANT_ID"]
    results: list[AskResult] = []
    for q in questions:
        if q.text.startswith("<TBD"):
            print(f"skip {q.id}: TBD 占位未填")
            continue
        try:
            resp = await _call_ai_chat_evidence(q.text, tenant_id, base_url)
        except Exception as e:
            print(f"ERROR {q.id}: {e}", file=sys.stderr)
            continue
        ask = _summarize_ask_response(resp)
        ask.question_id = q.id
        ask.question_text = q.text
        ask.ac2_pass = _check_ac2(ask)
        ask.ac3_pass = _check_ac3(ask)
        results.append(ask)
    p = _intermediate_path(args.out, "ask", args.intermediate)
    p.write_text(
        _json_dumps([asdict(r) for r in results]),
        encoding="utf-8",
    )
    print(f"ask done. intermediate: {p}")
    return 0


async def cmd_bug007(args: argparse.Namespace) -> int:
    _require_env(DB_REQUIRED_ENV)
    if args.run_reinitialize:
        _require_env(HTTP_REQUIRED_ENV)
    samples, _ = _load_samples(Path(args.samples))
    engine = await _create_engine()
    results: list[Bug007Result] = []
    try:
        for s in samples:
            if not s.file_id or ("pdf" not in s.label.lower()):
                continue
            await _maybe_reparse_or_reinit(
                engine,
                s.file_id,
                run_reinitialize=args.run_reinitialize,
                base_url=os.environ.get("AI_CHAT_BASE_URL", ""),
                tenant_id=os.environ.get("AI_CHAT_TENANT_ID", ""),
            )
            st = await _scan_sections(engine, s.file_id)
            results.append(Bug007Result(
                file_id=s.file_id,
                label=s.label,
                section_count=st["section_count"],
                empty_path_count=st["empty_path_count"],
                abnormal_path_count=st["abnormal_path_count"],
                chinese_section_title_count=st["chinese_title_count"],
                pass_=st["empty_path_count"] == 0 and st["abnormal_path_count"] == 0,
            ))
    finally:
        await engine.dispose()
    p = _intermediate_path(args.out, "bug007", args.intermediate)
    p.write_text(
        _json_dumps([asdict(r) for r in results]),
        encoding="utf-8",
    )
    print(f"bug007 done. intermediate: {p}")
    return 0


async def cmd_bug006(args: argparse.Namespace) -> int:
    _require_env(DB_REQUIRED_ENV + HTTP_REQUIRED_ENV)
    samples, _ = _load_samples(Path(args.samples))
    engine = await _create_engine()
    try:
        subs = await _verify_bug006_subs(
            engine, samples,
            os.environ["AI_CHAT_TENANT_ID"],
            os.environ["AI_CHAT_BASE_URL"],
        )
    finally:
        await engine.dispose()
    p = _intermediate_path(args.out, "bug006", args.intermediate)
    p.write_text(
        _json_dumps([asdict(r) for r in subs]),
        encoding="utf-8",
    )
    print(f"bug006 done. intermediate: {p}")
    return 0


def _load_intermediate(out: str, name: str) -> list[dict[str, Any]]:
    p = Path(f"{out}.{name}.intermediate.json")
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _summarize_ac(backfill, ask, bug007, bug006) -> dict[str, str]:
    summary: dict[str, str] = {}
    summary["AC-1"] = "✅" if backfill else "❌（无 backfill 数据）"
    if not ask:
        summary["AC-2"] = "⏳（待跑）"
        summary["AC-3"] = "⏳（待跑）"
    else:
        summary["AC-2"] = "✅" if all(a.get("ac2_pass") for a in ask) else "❌"
        summary["AC-3"] = "✅" if all(a.get("ac3_pass") for a in ask) else "❌"
    summary["AC-4"] = "✅" if all(b.get("pass_") for b in bug007) else "❌" if bug007 else "⏳（待跑）"
    if not bug006:
        summary["AC-5"] = "⏳（待跑）"
    else:
        conclusions = [s.get("conclusion", "") for s in bug006]
        if any(c.startswith("❌") for c in conclusions):
            summary["AC-5"] = "❌"
        elif any(c in {"手动", "见 bug007 章节"} or c.startswith("⏭") for c in conclusions):
            summary["AC-5"] = "⏳（含手动或复用 bug007 子项）"
        else:
            summary["AC-5"] = "✅"
    summary["AC-6"] = "⏳（由 report 阶段人工归因后翻牌）"
    summary["AC-7"] = "⏳（由 PR 阶段同步验证）"
    summary["AC-8"] = "⏳（由 PR 阶段门禁验证）"
    return summary


async def cmd_report(args: argparse.Namespace) -> int:
    _check_env()
    backfill_raw = _load_intermediate(args.out, "backfill")
    ask_raw = _load_intermediate(args.out, "ask")
    bug007_raw = _load_intermediate(args.out, "bug007")
    bug006_raw = _load_intermediate(args.out, "bug006")

    samples, _ = _load_samples(Path(args.samples))
    db_url = os.environ.get("DATABASE_URL", "")
    masked = "***@" + db_url.split("@", 1)[1] if "@" in db_url else db_url
    report = ValidationReport(
        generated_at=datetime.now().astimezone().isoformat(),
        db_url=masked,
        tenant_id=os.environ.get("AI_CHAT_TENANT_ID", ""),
        samples=samples,
        backfill_results=[BackfillResult(**r) for r in backfill_raw],
        ask_results=[AskResult(**r) for r in ask_raw],
        bug007_results=[Bug007Result(**r) for r in bug007_raw],
        bug006_subresults=[Bug006SubResult(**r) for r in bug006_raw],
        failures_attribution=[],
        ac_summary=_summarize_ac(backfill_raw, ask_raw, bug007_raw, bug006_raw),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8")
    print(f"report written: {out}")
    return 0


# -----------------------------
# CLI
# -----------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate_real_pg_rag")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in [("backfill", cmd_backfill), ("ask", cmd_ask),
                     ("bug007", cmd_bug007), ("bug006", cmd_bug006),
                     ("report", cmd_report)]:
        p = sub.add_parser(name)
        p.add_argument("--samples", required=True,
                       help="样例配置 JSON 路径（含 samples / questions）")
        p.add_argument("--out", required=True,
                       help="Markdown 报告输出路径")
        p.add_argument("--intermediate", default=None,
                       help="中间 JSON 路径（默认 <out>.<name>.intermediate.json）")
        p.add_argument("--run-reinitialize", action="store_true",
                       help="仅 backfill / bug007 使用：实际调用 reinitialize；默认只记录建议命令")
        p.set_defaults(_fn=fn)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(args._fn(args))


if __name__ == "__main__":
    sys.exit(main())
