"""Entry point: arg parsing + orchestration for REQ-024 P2 real validation.

Split out of the original monolithic script (TD-032 slice 8).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .loader import _load_dotenv, _load_questions
from .models import (
    DEFAULT_OUT,
    DEFAULT_REQ016_SAMPLES,
    DEFAULT_REQ018_SAMPLES,
    DEFAULT_REQ026_SAMPLES,
    DEFAULT_REQ028_SAMPLES,
    DEFAULT_TENANT_ID,
    REPO_ROOT,
    SERVER_PYTHON,
    ScenarioRun,
)
from .report import _render_report
from .runner import _default_scenarios, _run_question


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
                                semantic_emb_threshold=args.semantic_emb_threshold,
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
    parser.add_argument(
        "--semantic-emb-threshold",
        type=float,
        default=0.5,
        help="REQ-032: cosine similarity threshold for semantic embedding coverage hit (default 0.5; lower to 0.35 for Chinese short keypoints).",
    )
    return parser


def main() -> int:
    return asyncio.run(_run(_build_parser().parse_args()))
