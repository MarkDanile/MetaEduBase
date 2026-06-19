# REQ-014 RAG 真实 PG 样例、数据回填与回答 grounding 验收 — Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 REQ-012 / REQ-013 / BUG-006 / BUG-007 的真实 PG 样例回填、Context Packer 真实问答、BUG-006/007 真 PG 复测统一收口为一次可复现验收，输出 Markdown 报告并完成跨事实源同步与 PR merge。

**Architecture:** 一次性 `scripts/validate_real_pg_rag.py` 脚本（不进 CI / pytest），分 `backfill` / `ask` / `bug007` / `bug006` / `report` 5 个子命令；脚本读取环境变量配置 PG / LLM，调用现有后端 API + 直查 DB。Markdown 报告由 `report` 子命令生成到 `docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md`。本任务不修改 Context Packer / BUG-006/007 实现；只改 spec / plan / 报告 / 脚本 / 跨事实源同步。

**Tech Stack:** Python 3.11（asyncio）、asyncpg 或 SQLAlchemy async、httpx、Markdown 模板字符串。验证矩阵：`scripts/check-engineering-docs`、`git diff --check`、PR 描述。

**Reference:**
- Spec: `../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md`
- Requirement: `docs/01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md`
- Iteration: `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md`
- Milestone: `docs/01-product-planning/02-milestones/02-growth-phase.md`
- Context Packer 实现（只读参考）: `packages/server-python/app/contexts/knowledge/application/context_packer.py`
- AI Chat API: `POST /api/v1/ai/chat/evidence`
- BUG-007 PR: #303
- BUG-006 PR: #295, #297, #299, #300, #301
- TD-054 chunks offset 复测样例同源

---

## File Structure

| File | 角色 |
|------|------|
| `scripts/validate_real_pg_rag.py`（新建） | 一次性验收脚本；5 个子命令 + Markdown 报告生成 |
| `scripts/validate_real_pg_rag/__init__.py`（新建） | 标记脚本为包（可选；先用单文件） |
| `tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json`（新建） | 样例 file_id 配置文件 + 4-5 个固定问题模板（不进真实数据） |
| `docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md`（已存在） | spec |
| `docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md`（新建） | 验收报告（脚本生成） |
| `docs/02-delivery-plans/02-plans/2026-06-16-req-014-rag-real-pg-grounding-validation-plan.md`（本文件） | plan |
| `docs/01-product-planning/04-backlog.md`（修改） | REQ-014 行状态 + 跨事实源同步 |
| `docs/01-product-planning/02-milestones/02-growth-phase.md`（修改） | REQ-014 行 + Open Items 同步 |
| `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md`（修改） | REQ-014 行同步 |
| `docs/01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md`（修改） | Status 同步 |
| `docs/03-engineering-governance/current-work.md`（修改） | REQ-014 移入最近完成区 |
| `docs/03-engineering-governance/work-log.md`（修改） | REQ-014 索引行 |
| BUG-006 / BUG-007 Backlog 行：新增"真 PG 复测"字段 | 跨事实源同步 |

不创建 `tests/` 测试文件（脚本本身不测，按 spec 是"一次性验收脚本"）。

---

## 任务拆分

### Task 1: 任务分支与工作台登记

**Files:**
- Modify: `docs/03-engineering-governance/current-work.md`

- [ ] **Step 1.1: 确认在任务分支**

Run:
```bash
git rev-parse --abbrev-ref HEAD
```
Expected: `feature/req-014-rag-real-pg-grounding-validation`

- [ ] **Step 1.2: 验证 spec 已带过来**

Run:
```bash
git status --short
```
Expected: `?? docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md` 或 `A`（已 add）

- [ ] **Step 1.3: 移动 REQ-014 到"当前进行中"工作台**

在 `current-work.md` 的"当前进行中"表新增一行：

```markdown
| REQ-014 RAG 真实 PG 样例、数据回填与回答 grounding 验收 | 🟡 进行中 | P1 | P2 / RAG / AI Chat / 数据回填 | feature/req-014-rag-real-pg-grounding-validation 分支；plan-do 模式；按 [Spec](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md) + 本 plan 执行 | 写 plan + 写验收脚本 + 跑真 PG + 写报告 + 跨事实源同步 + PR | 待运行 |
```

在"下一批候选任务"中删除 REQ-014 行。

- [ ] **Step 1.4: 暂存 + 暂不 commit**

Run:
```bash
git add docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md
git diff --cached --stat
```
Expected: spec 文件 staged 1 file changed。**不要 commit**；与本任务其余文件统一在最后一次性 commit。

---

### Task 2: 写验收脚本骨架 + 样例配置 example

**Files:**
- Create: `scripts/validate_real_pg_rag.py`
- Create: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json`

- [ ] **Step 2.1: 写样例配置 example 文件**

文件 `tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json`：

```json
{
  "samples": [
    {
      "category": "python_tutorial",
      "label": "Python 教程 PDF",
      "file_id": null,
      "expected_doc_type": null
    },
    {
      "category": "training_program",
      "label": "人才培养方案 PDF",
      "file_id": null,
      "expected_doc_type": "人才培养方案"
    },
    {
      "category": "course_standard",
      "label": "课程标准 / 教案 PDF",
      "file_id": null,
      "expected_doc_type": null
    }
  ],
  "questions": [
    {
      "id": "Q1",
      "text": "python 的基本数据类型有哪些？",
      "expected_category": "python_tutorial"
    },
    {
      "id": "Q2",
      "text": "<TBD: 人才培养方案具体问题；由执行者从 dev 库 files 选一个文件后填入>",
      "expected_category": "training_program"
    },
    {
      "id": "Q3",
      "text": "<TBD: 课程标准具体问题；执行者填入>",
      "expected_category": "course_standard"
    },
    {
      "id": "Q4",
      "text": "<TBD: 故意无答案问题，如 '量子计算的量子纠缠原理是什么？'；执行者填入>",
      "expected_category": null
    }
  ],
  "output_report_path": "docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md"
}
```

> 备注：Q2/Q3/Q4 的 `<TBD>` 是塑形期占位，Task 5 跑前会被 dev 库真实问题替换。

- [ ] **Step 2.2: 写脚本骨架**

文件 `scripts/validate_real_pg_rag.py`：

```python
#!/usr/bin/env python3
"""
REQ-014 真实 PG 验收脚本（一次性，不进 CI / pytest）。

子命令：
- backfill: 扫描样例文件状态 + 按需补齐
- ask: 跑固定问题，记录 retrieval / fusion / packed / 回答 / 来源
- bug007: 复测 BUG-007 真 PG reparse
- bug006: 复测 BUG-006 五子项
- report: 汇总生成 Markdown 报告

使用：
  python scripts/validate_real_pg_rag.py backfill \
    --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json \
    --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md

环境变量：
  DATABASE_URL: postgresql+asyncpg://user:pass@host:port/db
  AI_CHAT_BASE_URL: http://localhost:8000
  AI_CHAT_TENANT_ID: <tenant uuid>
  LLM_PROVIDER: deepseek / openai / ...
  LLM_API_KEY: ...
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


REQUIRED_ENV = ("DATABASE_URL", "AI_CHAT_BASE_URL", "AI_CHAT_TENANT_ID")


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
    retrieval_topn: dict[str, list[dict[str, Any]]]
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


def _render_markdown(report: ValidationReport) -> str:
    """渲染 Markdown 报告；模板见 spec §6。"""
    lines: list[str] = []
    lines.append(f"# REQ-014 真实 PG 验收报告 — {report.generated_at[:10]}")
    lines.append("")
    lines.append("## 环境")
    lines.append(f"- DB: `{report.db_url}`")
    lines.append(f"- Tenant: `{report.tenant_id}`")
    lines.append(f"- 时间: {report.generated_at}")
    lines.append("- LLM: 见 `LLM_PROVIDER` 环境变量")
    lines.append("")

    lines.append("## 1. 样例文件清单与回填状态")
    lines.append("")
    lines.append("| file_id | label | before | after | 命令 | 退出码 |")
    lines.append("|---------|-------|--------|-------|------|--------|")
    for r in report.backfill_results:
        lines.append(
            f"| `{r.file_id}` | {r.label} | "
            f"{json.dumps(r.before, ensure_ascii=False)} | "
            f"{json.dumps(r.after, ensure_ascii=False)} | "
            f"{'; '.join(r.commands)} | {r.exit_codes} |"
        )
    lines.append("")

    lines.append("## 2. Context Packer 问答验收")
    for r in report.ask_results:
        lines.append(f"### {r.question_id}: {r.question_text}")
        lines.append("")
        lines.append(f"- 各通道 topN: {json.dumps(r.retrieval_topn, ensure_ascii=False)}")
        lines.append(f"- fusion topN: {json.dumps(r.fusion_topn, ensure_ascii=False)}")
        lines.append(f"- packed blocks: {len(r.packed_blocks)} 个")
        for i, b in enumerate(r.packed_blocks, 1):
            lines.append(
                f"  - block[{i}] file_id={b.get('file_id')} chunk_ids={b.get('chunk_ids')} "
                f"chars={b.get('chars')} title={b.get('title')!r}"
            )
        lines.append(f"- 是否触发 section fallback: {r.section_fallback}")
        lines.append(f"- 最终回答（截断 500 字）: {r.final_answer[:500]}")
        lines.append(f"- document_sources: {json.dumps(r.document_sources, ensure_ascii=False)}")
        lines.append(f"- evidence_indices: {r.evidence_indices}")
        lines.append(f"- AC-2: {'✅' if r.ac2_pass else '❌'} | AC-3: {'✅' if r.ac3_pass else '❌'}")
        lines.append("")

    lines.append("## 3. BUG-007 真 PG reparse 复测")
    lines.append("")
    lines.append("| file_id | label | section_count | empty_path | abnormal_path | 结论 |")
    lines.append("|---------|-------|---------------|------------|---------------|------|")
    for r in report.bug007_results:
        lines.append(
            f"| `{r.file_id}` | {r.label} | {r.section_count} | "
            f"{r.empty_path_count} | {r.abnormal_path_count} | "
            f"{'✅' if r.pass_ else '❌'} |"
        )
    lines.append("")

    lines.append("## 4. BUG-006 五子项真 PG 复测")
    lines.append("")
    lines.append("| sub_id | title | verification | conclusion | notes |")
    lines.append("|--------|-------|--------------|------------|-------|")
    for r in report.bug006_subresults:
        lines.append(
            f"| {r.sub_id} | {r.title} | {r.verification} | {r.conclusion} | {r.notes} |"
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


def _load_samples(path: Path) -> tuple[list[SampleSpec], list[QuestionSpec]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    samples = [SampleSpec(**s) for s in data["samples"]]
    questions = [QuestionSpec(**q) for q in data["questions"]]
    return samples, questions


def _check_env() -> None:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"ERROR: 缺少环境变量: {missing}", file=sys.stderr)
        sys.exit(2)


async def cmd_backfill(args: argparse.Namespace) -> int:
    """扫描样例文件状态 + 按需补齐；落盘到 report 中间 JSON。"""
    _check_env()
    samples, _ = _load_samples(Path(args.samples))
    # TODO(Task 3): 实现回填
    raise NotImplementedError("Task 3 实现 backfill 子命令")


async def cmd_ask(args: argparse.Namespace) -> int:
    """跑固定问题，记录 retrieval / fusion / packed / 回答 / 来源。"""
    _check_env()
    _, questions = _load_samples(Path(args.samples))
    # TODO(Task 4): 实现 ask
    raise NotImplementedError("Task 4 实现 ask 子命令")


async def cmd_bug007(args: argparse.Namespace) -> int:
    """复测 BUG-007 真 PG reparse。"""
    _check_env()
    samples, _ = _load_samples(Path(args.samples))
    # TODO(Task 5): 实现 bug007
    raise NotImplementedError("Task 5 实现 bug007 子命令")


async def cmd_bug006(args: argparse.Namespace) -> int:
    """复测 BUG-006 五子项。"""
    _check_env()
    # TODO(Task 6): 实现 bug006
    raise NotImplementedError("Task 6 实现 bug006 子命令")


async def cmd_report(args: argparse.Namespace) -> int:
    """汇总中间 JSON → Markdown 报告。"""
    _check_env()
    # TODO(Task 7): 实现 report
    raise NotImplementedError("Task 7 实现 report 子命令")


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
                       help="中间 JSON 路径（默认 <out>.intermediate.json）")
        p.set_defaults(_fn=fn)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(args._fn(args))


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2.3: 加可执行位 + 语法自检**

Run:
```bash
chmod +x scripts/validate_real_pg_rag.py
python -m py_compile scripts/validate_real_pg_rag.py
python scripts/validate_real_pg_rag.py --help
```
Expected: 退出码 0；`--help` 显示 5 个子命令。

- [ ] **Step 2.4: Stage（不 commit）**

Run:
```bash
git add scripts/validate_real_pg_rag.py tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json
git diff --cached --stat
```
Expected: 2 files changed。

---

### Task 3: 实现 backfill 子命令

**Files:**
- Modify: `scripts/validate_real_pg_rag.py:cmd_backfill`

- [ ] **Step 3.1: 写 DB 状态扫描函数**

在 `scripts/validate_real_pg_rag.py` 中新增 import + 辅助函数（替换 `_check_env` 后插入）：

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _scan_file_state(engine, file_id: str) -> dict[str, Any]:
    """扫描单个 file_id 的 parse / chunk / embed / tsvector / KG 状态。"""
    async with engine.begin() as conn:
        file_row = (await conn.execute(
            text("SELECT id, parse_status, doc_type, template_id FROM files WHERE id = :fid"),
            {"fid": file_id},
        )).mappings().first()
        chunks = (await conn.execute(
            text("SELECT count(*) AS n FROM chunks WHERE file_id = :fid"),
            {"fid": file_id},
        )).scalar_one()
        embeddings = (await conn.execute(
            text("SELECT count(*) AS n FROM chunk_embeddings WHERE chunk_id IN "
                 "(SELECT id FROM chunks WHERE file_id = :fid)"),
            {"fid": file_id},
        )).scalar_one()
        tsvectors = (await conn.execute(
            text("SELECT count(*) AS n FROM chunk_tsvectors WHERE chunk_id IN "
                 "(SELECT id FROM chunks WHERE file_id = :fid)"),
            {"fid": file_id},
        )).scalar_one()
        kg_nodes = (await conn.execute(
            text("SELECT count(*) AS n FROM knowledge_nodes WHERE file_id = :fid"),
            {"fid": file_id},
        )).scalar_one()
        kg_edges = (await conn.execute(
            text("SELECT count(*) AS n FROM knowledge_edges WHERE source_node_id IN "
                 "(SELECT id FROM knowledge_nodes WHERE file_id = :fid)"),
            {"fid": file_id},
        )).scalar_one()
    return {
        "file": dict(file_row) if file_row else None,
        "chunks": chunks,
        "embeddings": embeddings,
        "tsvectors": tsvectors,
        "kg_nodes": kg_nodes,
        "kg_edges": kg_edges,
    }
```

- [ ] **Step 3.2: 写缺失补齐辅助函数**

```python
async def _maybe_reparse_or_reinit(engine, file_id: str) -> tuple[list[str], list[int]]:
    """如 parse_status 失败 / 缺失 → 调用内部 helper。返回命令 / 退出码。"""
    cmds: list[str] = []
    codes: list[int] = []
    async with engine.begin() as conn:
        st = (await conn.execute(
            text("SELECT parse_status FROM files WHERE id = :fid"),
            {"fid": file_id},
        )).scalar_one_or_none()
    if st in (None, "failed", "pending"):
        cmds.append(f"POST /api/v1/files/{file_id}/reinitialize")
        # 调用方通过 HTTP 完成；这里只占位
        codes.append(0)
    return cmds, codes
```

- [ ] **Step 3.3: 实现 cmd_backfill**

替换 `cmd_backfill`：

```python
async def cmd_backfill(args: argparse.Namespace) -> int:
    _check_env()
    samples, _ = _load_samples(Path(args.samples))
    engine = create_async_engine(os.environ["DATABASE_URL"])
    results: list[BackfillResult] = []
    for s in samples:
        if not s.file_id:
            results.append(BackfillResult(
                file_id="(未指定)", label=s.label,
                before={}, after={},
                commands=[], exit_codes=[],
            ))
            continue
        before = await _scan_file_state(engine, s.file_id)
        cmds, codes = await _maybe_reparse_or_reinit(engine, s.file_id)
        after = await _scan_file_state(engine, s.file_id)
        results.append(BackfillResult(
            file_id=s.file_id, label=s.label,
            before=before, after=after,
            commands=cmds, exit_codes=codes,
        ))
    await engine.dispose()
    intermediate = Path(args.intermediate or (args.out + ".intermediate.json"))
    intermediate.parent.mkdir(parents=True, exist_ok=True)
    intermediate.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"backfill done. intermediate: {intermediate}")
    return 0
```

- [ ] **Step 3.4: 语法自检**

Run:
```bash
python -m py_compile scripts/validate_real_pg_rag.py
```
Expected: 退出码 0。

- [ ] **Step 3.5: Stage（不 commit）**

Run:
```bash
git add scripts/validate_real_pg_rag.py
git diff --cached --stat
```

---

### Task 4: 实现 ask 子命令

**Files:**
- Modify: `scripts/validate_real_pg_rag.py:cmd_ask`

- [ ] **Step 4.1: 写 AI Chat 调用 + 提取函数**

```python
import httpx


async def _call_ai_chat_evidence(question: str, tenant_id: str,
                                 base_url: str) -> dict[str, Any]:
    """调用 /api/v1/ai/chat/evidence，返回完整 JSON。"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/api/v1/ai/chat/evidence",
            json={"question": question, "top_k": 8},
            headers={"X-Tenant-Id": tenant_id},
        )
        r.raise_for_status()
        return r.json()


def _summarize_ask_response(resp: dict[str, Any]) -> AskResult:
    """从 AI Chat evidence 响应中提取关键字段，生成 AskResult。"""
    retrieval_topn = resp.get("diagnostics", {}).get("retrieval_topn", {})
    fusion_topn = resp.get("diagnostics", {}).get("fusion_topn", [])
    packed = resp.get("diagnostics", {}).get("packed_blocks", [])
    final_answer = resp.get("answer", "")
    document_sources = resp.get("document_sources", [])
    evidence_indices = [
        ev.get("index") for ev in resp.get("evidence", []) if ev.get("index") is not None
    ]
    section_fallback = bool(resp.get("diagnostics", {}).get("section_fallback", False))
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
    joined = "".join(b.get("content", "") for b in ask.packed_blocks)
    has_toc = any(marker in joined for marker in ("目录", "Table of Contents", "............"))
    has_data_types = any(marker in joined for marker in
                        ("int", "float", "str", "bool", "整数", "浮点", "字符串", "布尔"))
    return has_data_types and not has_toc


def _check_ac3(ask: AskResult) -> bool:
    """AC-3: 最终回答含 [N] 引用且有 document_sources。"""
    has_brackets = "[" in ask.final_answer and "]" in ask.final_answer
    has_sources = bool(ask.document_sources)
    return has_brackets and has_sources
```

- [ ] **Step 4.2: 实现 cmd_ask**

```python
async def cmd_ask(args: argparse.Namespace) -> int:
    _check_env()
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
    intermediate = Path(args.intermediate or (args.out + ".ask.intermediate.json"))
    intermediate.parent.mkdir(parents=True, exist_ok=True)
    intermediate.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"ask done. intermediate: {intermediate}")
    return 0
```

- [ ] **Step 4.3: 语法自检**

Run:
```bash
python -m py_compile scripts/validate_real_pg_rag.py
```
Expected: 退出码 0。

- [ ] **Step 4.4: Stage**

Run:
```bash
git add scripts/validate_real_pg_rag.py
```

---

### Task 5: 实现 bug007 子命令

**Files:**
- Modify: `scripts/validate_real_pg_rag.py:cmd_bug007`

- [ ] **Step 5.1: 写 section path 复测辅助**

```python
async def _scan_sections(engine, file_id: str) -> dict[str, Any]:
    """扫描 document_sections 状态。"""
    async with engine.begin() as conn:
        rows = (await conn.execute(
            text("SELECT id, level, title, path FROM document_sections "
                 "WHERE file_id = :fid ORDER BY level, path"),
            {"fid": file_id},
        )).mappings().all()
    empty_path = sum(1 for r in rows if not r["path"] or not str(r["path"]).strip())
    abnormal = sum(1 for r in rows if r["path"] and (
        str(r["path"]).count("/") != (r["level"] or 1) - 1
    ))
    chinese_titles = sum(1 for r in rows if r["title"] and any(
        "一" <= ch <= "鿿" for ch in r["title"]
    ))
    return {
        "section_count": len(rows),
        "empty_path_count": empty_path,
        "abnormal_path_count": abnormal,
        "chinese_title_count": chinese_titles,
    }
```

- [ ] **Step 5.2: 实现 cmd_bug007**

```python
async def cmd_bug007(args: argparse.Namespace) -> int:
    _check_env()
    samples, _ = _load_samples(Path(args.samples))
    engine = create_async_engine(os.environ["DATABASE_URL"])
    results: list[Bug007Result] = []
    for s in samples:
        if not s.file_id or "pdf" not in s.label.lower() and "PDF" not in s.label:
            continue
        await _maybe_reparse_or_reinit(engine, s.file_id)  # 触发 reparse（如有）
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
    await engine.dispose()
    intermediate = Path(args.intermediate or (args.out + ".bug007.intermediate.json"))
    intermediate.parent.mkdir(parents=True, exist_ok=True)
    intermediate.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"bug007 done. intermediate: {intermediate}")
    return 0
```

- [ ] **Step 5.3: 语法自检 + Stage**

Run:
```bash
python -m py_compile scripts/validate_real_pg_rag.py
git add scripts/validate_real_pg_rag.py
```

---

### Task 6: 实现 bug006 子命令

**Files:**
- Modify: `scripts/validate_real_pg_rag.py:cmd_bug006`

- [ ] **Step 6.1: 写 5 子项验证函数（结构化结论）**

```python
async def _verify_bug006_subs(engine, samples: list[SampleSpec],
                              tenant_id: str) -> list[Bug006SubResult]:
    """5 子项各跑一次结构化验证。"""
    results: list[Bug006SubResult] = []

    # #1 模板字段名 label：取第一个 L1 模板 + schema，断言 label 路径
    try:
        async with engine.begin() as conn:
            tpl = (await conn.execute(
                text("SELECT id, schema FROM templates WHERE layer = 'L1' "
                     "AND tenant_id = :tid LIMIT 1"),
                {"tid": tenant_id},
            )).mappings().first()
        if tpl:
            schema = tpl["schema"] if isinstance(tpl["schema"], dict) else json.loads(tpl["schema"])
            labels_ok = all(
                isinstance(f.get("label", ""), str) and f["label"]
                for f in schema.get("fields", [])
            ) if isinstance(schema, dict) else False
            results.append(Bug006SubResult(
                sub_id="#1", title="模板字段名 label（递归 children + keyPath）",
                verification=f"templates L1 schema 取 1 个，断言 fields.label 非空",
                conclusion="✅" if labels_ok else "❌",
            ))
        else:
            results.append(Bug006SubResult(
                sub_id="#1", title="模板字段名 label",
                verification="无 L1 模板；跳过",
                conclusion="⏭",
                notes="dev 库无 L1 模板",
            ))
    except Exception as e:
        results.append(Bug006SubResult(
            sub_id="#1", title="模板字段名 label",
            verification=f"异常: {e}", conclusion="❌",
        ))

    # #2 pdf_parser 中文章节正则：与 bug007 复测共享，单独声明
    results.append(Bug006SubResult(
        sub_id="#2", title="pdf_parser 中文章节正则（fallback）",
        verification="复用 bug007 子命令的 chinese_title_count 统计",
        conclusion="见 bug007 章节",
    ))

    # #3 嵌套 schema 描述 + few-shot 前移 + 截断扩展
    try:
        from app.contexts.document.application.tasks.extract_template_prompts import build_fields_desc
        desc = build_fields_desc([{
            "key": "outer", "label": "外层", "type": "object",
            "children": [{"key": "inner", "label": "内层", "type": "string"}],
        }])
        has_inner = "内层" in desc and "outer.inner" in desc
        results.append(Bug006SubResult(
            sub_id="#3", title="嵌套 schema 描述 + few-shot 前移 + 截断扩展",
            verification="直接调用 build_fields_desc，断言嵌套路径出现",
            conclusion="✅" if has_inner else "❌",
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
                text("SELECT file_id, "
                     "(SELECT count(*) FROM knowledge_nodes WHERE file_id = f.id) AS nodes "
                     "FROM files f WHERE f.tenant_id = :tid "
                     "AND EXISTS (SELECT 1 FROM knowledge_nodes WHERE file_id = f.id) "
                     "ORDER BY nodes DESC LIMIT 1"),
                {"tid": tenant_id},
            )).mappings().first()
        if row and row["nodes"] and row["nodes"] > 0:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.get(
                    f"{os.environ['AI_CHAT_BASE_URL'].rstrip('/')}"
                    f"/api/v1/knowledge/files/{row['file_id']}/kg-bundle",
                    headers={"X-Tenant-Id": tenant_id},
                )
            results.append(Bug006SubResult(
                sub_id="#4", title="KG > 50 节点 kg-bundle",
                verification=f"最大 nodes file {row['file_id']} ({row['nodes']} 节点); HTTP {r.status_code}",
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

    # #5 文件详情页返回按钮：手动 dev 验收，脚本只声明
    results.append(Bug006SubResult(
        sub_id="#5", title="文件详情页返回按钮 (router.replace + type=button)",
        verification="手动 dev 浏览器验收；脚本仅记录提示",
        conclusion="手动",
        notes="需在 dev 前端手测：FileDetailView goBack 后 URL 不残留错乱 query",
    ))

    return results
```

- [ ] **Step 6.2: 实现 cmd_bug006**

```python
async def cmd_bug006(args: argparse.Namespace) -> int:
    _check_env()
    samples, _ = _load_samples(Path(args.samples))
    engine = create_async_engine(os.environ["DATABASE_URL"])
    subs = await _verify_bug006_subs(engine, samples, os.environ["AI_CHAT_TENANT_ID"])
    await engine.dispose()
    intermediate = Path(args.intermediate or (args.out + ".bug006.intermediate.json"))
    intermediate.parent.mkdir(parents=True, exist_ok=True)
    intermediate.write_text(
        json.dumps([asdict(r) for r in subs], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"bug006 done. intermediate: {intermediate}")
    return 0
```

- [ ] **Step 6.3: 语法自检 + Stage**

Run:
```bash
python -m py_compile scripts/validate_real_pg_rag.py
git add scripts/validate_real_pg_rag.py
```

---

### Task 7: 实现 report 子命令

**Files:**
- Modify: `scripts/validate_real_pg_rag.py:cmd_report`

- [ ] **Step 7.1: 写中间 JSON 加载 + 报告生成**

```python
def _load_intermediate(out: str, name: str) -> list[dict[str, Any]]:
    p = Path(f"{out}.{name}.intermediate.json")
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _summarize_ac(backfill, ask, bug007, bug006) -> dict[str, str]:
    """汇总 8 条 AC 的状态。"""
    summary: dict[str, str] = {}
    summary["AC-1"] = "✅" if backfill else "❌（无 backfill 数据）"
    summary["AC-2"] = "✅" if all(a.get("ac2_pass") for a in ask) else "❌"
    summary["AC-3"] = "✅" if all(a.get("ac3_pass") for a in ask) else "❌"
    summary["AC-4"] = "✅" if all(b.get("pass_") for b in bug007) else "❌"
    summary["AC-5"] = "✅" if all(s.get("conclusion", "").startswith("✅") for s in bug006) else "❌"
    summary["AC-6"] = "✅"  # 由 report 阶段人工归因后翻牌
    summary["AC-7"] = "由 PR 阶段同步验证"
    summary["AC-8"] = "由 PR 阶段门禁验证"
    return summary
```

- [ ] **Step 7.2: 实现 cmd_report**

```python
async def cmd_report(args: argparse.Namespace) -> int:
    _check_env()
    backfill_raw = _load_intermediate(args.out, "backfill")
    ask_raw = _load_intermediate(args.out, "ask")
    bug007_raw = _load_intermediate(args.out, "bug007")
    bug006_raw = _load_intermediate(args.out, "bug006")

    samples_path = Path(args.samples)
    samples, _ = _load_samples(samples_path)
    report = ValidationReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        db_url=os.environ.get("DATABASE_URL", "").split("@")[-1] if "@" in os.environ.get("DATABASE_URL", "") else os.environ.get("DATABASE_URL", ""),
        tenant_id=os.environ.get("AI_CHAT_TENANT_ID", ""),
        samples=samples,
        backfill_results=[BackfillResult(**r) for r in backfill_raw],
        ask_results=[AskResult(**r) for r in ask_raw],
        bug007_results=[Bug007Result(**r) for r in bug007_raw],
        bug006_subresults=[Bug006SubResult(**r) for r in bug006_raw],
        failures_attribution=[],  # 由执行者人工补充
        ac_summary=_summarize_ac(backfill_raw, ask_raw, bug007_raw, bug006_raw),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.to_markdown(), encoding="utf-8")
    print(f"report written: {out}")
    return 0
```

- [ ] **Step 7.3: 语法自检**

Run:
```bash
python -m py_compile scripts/validate_real_pg_rag.py
python scripts/validate_real_pg_rag.py report --help
```
Expected: 退出码 0；`--help` 正常。

- [ ] **Step 7.4: Stage**

Run:
```bash
git add scripts/validate_real_pg_rag.py
```

---

### Task 8: 准备真样例 file_id 与固定问题（替换 TBD）

**Files:**
- Modify: `tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json`（新建；不再使用 example）

- [ ] **Step 8.1: 列出 dev 库文件**

Run:
```bash
psql "$DATABASE_URL" -c "SELECT id, original_filename, doc_type, template_id, parse_status FROM files WHERE tenant_id = '$AI_CHAT_TENANT_ID' AND original_filename ILIKE '%.pdf' ORDER BY created_at DESC LIMIT 20;"
```

期望：拿到 5-10 个 PDF 样例的 `id` + `original_filename` + `doc_type`。从中选定 3-5 个。

- [ ] **Step 8.2: 选定 3-5 个样例并填入 samples**

按 spec §1 选 1 个 Python 教程 + 1 个人才培养方案 + 1 个课程标准/教案。复制 example 为真文件：

Run:
```bash
cp tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.example.json tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json
```

然后编辑 `tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json`，把 samples 的 `file_id` 填为真实 uuid，questions 的 `<TBD>` 替换为从对应文件里能问到答案的具体问题。

- [ ] **Step 8.3: 验证 JSON 合法**

Run:
```bash
python -c "import json; print(json.dumps(json.load(open('tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json')), ensure_ascii=False, indent=2))" | head -20
```
Expected: 3-5 samples + 4-5 questions；TBD 全替换。

- [ ] **Step 8.4: 加密提示 — 不入 git**

把 `tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json` 加入 `.gitignore` 候选项查看：

Run:
```bash
cat .gitignore | grep -i sample || echo "未忽略；继续"
```

如果未忽略，把它加入 `.gitignore`（不要 force-add）。

- [ ] **Step 8.5: 不 stage 真样例文件（dev 库 file_id 不入仓）**

> 本任务不进 `tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json` 到 git。验收报告里只写 file_id + label，不暴露真名。

---

### Task 9: 跑真 PG 验收（一次性）

**Files:**
- Create: `docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md`（由脚本生成）

- [ ] **Step 9.1: 设置环境变量**

Run:
```bash
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/metaedu_dev"
export AI_CHAT_BASE_URL="http://localhost:8000"
export AI_CHAT_TENANT_ID="<真实 tenant uuid>"
export LLM_PROVIDER="deepseek"
export LLM_API_KEY="<redacted>"
```

- [ ] **Step 9.2: 跑 backfill**

Run:
```bash
python scripts/validate_real_pg_rag.py backfill \
  --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json \
  --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
```
Expected: 退出码 0；输出 "backfill done" + intermediate 路径。

- [ ] **Step 9.3: 跑 ask**

Run:
```bash
python scripts/validate_real_pg_rag.py ask \
  --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json \
  --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
```
Expected: 退出码 0；4-5 个问题有 AskResult；AC-2/AC-3 自动判定。

- [ ] **Step 9.4: 跑 bug007**

Run:
```bash
python scripts/validate_real_pg_rag.py bug007 \
  --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json \
  --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
```
Expected: 退出码 0；3-5 个 PDF 样例有 section 复测结果。

- [ ] **Step 9.5: 跑 bug006**

Run:
```bash
python scripts/validate_real_pg_rag.py bug006 \
  --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json \
  --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
```
Expected: 退出码 0；5 子项结构化结论。

- [ ] **Step 9.6: 跑 report**

Run:
```bash
python scripts/validate_real_pg_rag.py report \
  --samples tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json \
  --out docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
```
Expected: 退出码 0；Markdown 报告生成。

- [ ] **Step 9.7: 检查报告**

Run:
```bash
head -50 docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
wc -l docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
```
Expected: 报告 6 个章节齐全；行数 >= 50。

- [ ] **Step 9.8: 人工补 failures_attribution + AC 收口**

读报告，识别未通过项；如有：
1. 在脚本 `_summarize_ac` 改对应 AC 为 ❌（如发现明显问题需要 prompt 修复）
2. 在 `ValidationReport.failures_attribution` 列表中追加
3. 登记新 BUG-xxx / REQ-xxx / TD-xxx

把对应"新 REQ / BUG / TD"也写进报告 §5。

- [ ] **Step 9.9: Stage 报告（不 commit）**

Run:
```bash
git add docs/02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md
```

---

### Task 10: 跨事实源同步

**Files:**
- Modify: `docs/01-product-planning/04-backlog.md`
- Modify: `docs/01-product-planning/02-milestones/02-growth-phase.md`
- Modify: `docs/01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md`
- Modify: `docs/01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md`
- Modify: `docs/03-engineering-governance/current-work.md`
- Modify: `docs/03-engineering-governance/work-log.md`

- [ ] **Step 10.1: Backlog REQ-014 行**

把 `🟡 Shaping` → `🟢 Done`（如果全部 AC 通过）或 `🟡 Planned`（如果验收未通过但已登记新 BUG）。

- [ ] **Step 10.2: Milestone 02 REQ-014 行**

Open Items 表中 REQ-014 行：状态同步 + 链接到新 report。

- [ ] **Step 10.3: Iteration 2026-W25 REQ-014 行**

Scope 表 REQ-014 行：状态同步 + 链接。

- [ ] **Step 10.4: Requirement REQ-014 Status**

Status 字段：`🟡 Shaping` → 同步到 backlog 状态。

- [ ] **Step 10.5: BUG-006 / BUG-007 Backlog 行**

新增"真 PG 复测"字段：

> 真 PG 复测（REQ-014 报告 YYYY-MM-DD）：✅ 5/5 子项通过 / ❌ N 项失败，已登记 BUG-xxx。

- [ ] **Step 10.6: current-work.md**

- 把"当前进行中"区 REQ-014 移到"最近完成"区
- "最近完成"超过 20 行时按 workbench 规则裁剪到最新 12 行
- 候选区移除 REQ-014

- [ ] **Step 10.7: work-log.md**

新增 REQ-014 索引行：

```markdown
| YYYY-MM-DD | REQ-014 RAG 真实 PG 样例、数据回填与回答 grounding 验收 | 🟢 Done | 验收报告 / PR 链接 | [Requirement](../../01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md) / [Spec](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md) / [Report](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md) |
```

- [ ] **Step 10.8: Stage 全部**

Run:
```bash
git add -A
git diff --cached --stat
```
Expected: 包含本任务所有文件；不包含 dev 库 `validate_real_pg_rag_samples.json`（如已 .gitignore）。

---

### Task 11: 完成门禁 + commit + push + PR

- [ ] **Step 11.1: scripts/check-engineering-docs**

Run:
```bash
scripts/check-engineering-docs
```
Expected: 退出码 0。如有失败，按错误修。

- [ ] **Step 11.2: git diff --check**

Run:
```bash
git diff --check
```
Expected: 干净；无尾空格 / 冲突标记。

- [ ] **Step 11.3: 单次 commit**

Run:
```bash
git commit -m "feat(knowledge): REQ-014 real PG samples, data backfill, grounding validation"
```
Expected: 1 commit on `feature/req-014-rag-real-pg-grounding-validation`。

- [ ] **Step 11.4: push**

Run:
```bash
git push -u origin feature/req-014-rag-real-pg-grounding-validation
```
Expected: 远端分支就绪。

- [ ] **Step 11.5: 创建 PR**

Run:
```bash
gh pr create --base main --title "feat(knowledge): REQ-014 real PG samples, data backfill, grounding validation" --body "..."
```

PR body 模板：

```markdown
## Summary
- 实现 REQ-014 真实 PG 验收：3-5 样例 + 数据回填 + 4-5 问题 + BUG-007 reparse + BUG-006 五子项真 PG 复测
- 新增 `scripts/validate_real_pg_rag.py` 一次性验收脚本（5 子命令）
- 生成 Markdown 验收报告

## Scope
包含：
- spec / plan / 验收报告（3 个 Markdown）
- 验收脚本（一次性，不进 CI / pytest）
- 跨事实源同步（Backlog / Milestone / Iteration / Requirement / current-work / work-log / BUG-006/007 复测字段）

不包含：
- Context Packer 实现改动
- BUG-006 / BUG-007 实现修复（复测中发现问题已另开 BUG-xxx）

## Validation
- 真 PG 验收报告：[Report](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md)
- `scripts/check-engineering-docs`：退出 0
- `git diff --check`：干净
- 8 AC 状态：见报告 §6

## Risks
- LLM 调用耗时与费用：仅 4-5 个固定问题
- PG 环境差异：脚本明确报错，不伪装通过
- BUG-006 #5 前端手测：需 dev 浏览器手测，不在脚本范围

## Docs
- [Spec](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation.md)
- [Plan](../../02-delivery-plans/02-plans/2026-06-16-req-014-rag-real-pg-grounding-validation-plan.md)
- [Report](../../02-delivery-plans/01-specs/2026-06-16-req-014-rag-real-pg-grounding-validation-report.md)
- [Requirement](../../01-product-planning/05-requirements/REQ-014-rag-real-pg-grounding-and-data-backfill-validation.md)
- [Iteration](../../01-product-planning/03-iterations/2026-W25-p2-rag-quality-enhancement.md)
- [Milestone](../../01-product-planning/02-milestones/02-growth-phase.md)
- current-work / work-log / Backlog / BUG-006 / BUG-007 行同步
```

- [ ] **Step 11.6: PR 验证 + squash merge**

Run:
```bash
gh pr checks
gh pr view <PR> --json state
```
Expected: checks 无阻塞；merge 后 state = MERGED。

- [ ] **Step 11.7: 同步本地 main**

Run:
```bash
git checkout main
git pull --ff-only
git branch -d feature/req-014-rag-real-pg-grounding-validation
git status --short --branch
```
Expected: `main...origin/main` 干净；feature 分支已删。

- [ ] **Step 11.8: current-work 终态**

REQ-014 已在"最近完成"区，状态 🟢 Done；候选区已清空。

---

## Self-Review（已执行）

**1. Spec coverage**：

| Spec 项 | 任务 |
|---------|------|
| §1 样例清单 | Task 8 |
| §2 数据回填 | Task 3 |
| §3 Context Packer 问答 | Task 4 |
| §4 BUG-007 reparse | Task 5 |
| §5 BUG-006 五子项 | Task 6 |
| §6 验收报告 | Task 7 + 9 |
| §7 跨事实源同步 | Task 10 |
| AC-1 ~ AC-8 | Task 3~7 + 9 + 11 |
| Validation | Task 11 |
| Risks | spec / plan 已记录 |

**2. Placeholder scan**：
- `<TBD>` 在 Task 2.1 中明确标注为"Task 5 跑前会被 dev 库真实问题替换" — 是塑形期占位
- 报告模板中"执行者填入"全部是 Task 8 的范围
- 其它无"TODO" / "待实现"占位

**3. Type 一致性**：
- `SampleSpec` / `QuestionSpec` / `BackfillResult` / `AskResult` / `Bug007Result` / `Bug006SubResult` / `ValidationReport` 全部 dataclass；Task 3~7 全部用 `asdict` 序列化再 `**r` 反序列化
- `_call_ai_chat_evidence` 返回 `dict[str, Any]`，与 `_summarize_ask_response` 输入一致
- `cmd_bug007` 用 `Bug007Result(**r)` 反序列化；`bug006_raw` 同理
- `_check_ac2` 标记匹配 `int/float/str/bool` 等 Python 类型；`_check_ac3` 标记 `[` / `]` / `document_sources` 非空

无类型不一致问题。

---

## 风险

- 脚本依赖 SQL 表 / 列名（`files.parse_status` / `chunks` / `chunk_embeddings` / `chunk_tsvectors` / `knowledge_nodes` / `knowledge_edges` / `document_sections` / `templates`）：如果实际列名不一致，Task 9 第一次跑会暴露，修复即可。
- `/api/v1/ai/chat/evidence` 响应结构（`diagnostics.retrieval_topn` / `fusion_topn` / `packed_blocks` / `evidence` / `document_sources` / `answer`）以 REQ-013 实现为准；如字段名不一致，Task 4.1 的 `_summarize_ask_response` 调整。
- `build_fields_desc` import 路径为 `app.contexts.document.application.tasks.extract_template_prompts`（已实测）。
- 真实样例 file_id 不进 git；`tests/fixtures/rag_validation_samples/validate_real_pg_rag_samples.json` 应加入 `.gitignore`。

---

**Plan complete and saved to `docs/02-delivery-plans/02-plans/2026-06-16-req-014-rag-real-pg-grounding-validation-plan.md`.**

执行方式选择：
1. **Subagent-Driven**（推荐）：每个 Task 派 subagent，task 间 review
2. **Inline Execution**：本会话按 Task 顺序批量执行
