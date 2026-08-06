#!/usr/bin/env python3
"""Select backend pytest scope from changed repository paths."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_PREFIX = "packages/server-python/"
SMOKE_TESTS = (
    "tests/shared/test_health.py",
    "tests/test_bug013_db_unavailable_handler.py",
)

AGENT_RISK_TESTS = (
    "tests/composition/test_s3c_fenced_port.py",
    "tests/composition/test_s3c_writer_fence_e2e.py",
    "tests/composition/test_s3e_fenced_port_no_bypass.py",
    "tests/contexts/agent_control_plane/test_integration_contract.py",
    "tests/contexts/agent_control_plane/test_output_bridge.py",
    "tests/contexts/agent_control_plane/test_run_api.py",
    "tests/contexts/agent_control_plane/test_s2c_ingress_and_title_fence.py",
    "tests/contexts/agent_control_plane/test_s3e_dispatch_output_late_write.py",
    "tests/contexts/agent_control_plane/test_s3e_dispatch_output_round1.py",
    "tests/contexts/agent_control_plane/test_s3e_execution_race.py",
    "tests/contexts/agent_control_plane/test_turn_bridge.py",
    "tests/contexts/agent_control_plane/test_writer_fence.py",
    "tests/contexts/agent_execution/test_run_coordinator.py",
    "tests/contexts/agent_execution/test_run_state_machine.py",
    "tests/contexts/agent_execution/test_runtime_ingest_and_terminal.py",
    "tests/contexts/agent_execution/test_snapshots_and_ingest_contract.py",
    "tests/contexts/agent_workspace",
    "tests/contexts/ai/test_direct_rag_compatibility_recording.py",
)

TRANSPORT_RISK_TESTS = (
    "tests/composition/test_agent_transport_backfill.py",
    "tests/composition/test_agent_transport_backfill_m4.py",
    "tests/composition/test_agent_transport_locks.py",
    "tests/composition/test_agent_transport_schema.py",
)

ERASURE_RISK_TESTS = (
    "tests/composition/test_agent_erasure_locks.py",
    "tests/composition/test_agent_erasure_migration_roundtrip.py",
    "tests/composition/test_agent_erasure_registry.py",
    "tests/composition/test_agent_erasure_schema.py",
    "tests/contexts/agent_control_plane/test_s2de_workspace_erasure.py",
    "tests/contexts/agent_control_plane/test_s3d_execution_blocked.py",
    "tests/contexts/agent_control_plane/test_s3d_execution_clear_actions.py",
    "tests/contexts/agent_control_plane/test_s3d_execution_fencing.py",
    "tests/contexts/agent_control_plane/test_s3d_execution_scan_ack.py",
)

MIGRATION_RISK_TESTS = (
    "tests/composition/test_agent_erasure_fence_index_cleanup.py",
    "tests/composition/test_agent_erasure_migration_roundtrip.py",
    "tests/composition/test_agent_erasure_schema.py",
    "tests/composition/test_agent_transport_schema.py",
    "tests/contexts/agent_control_plane/test_bridge_migration.py",
    "tests/contexts/agent_control_plane/test_s3d_run_event_guard.py",
    "tests/contexts/agent_execution/test_compatibility_output_migration.py",
    "tests/contexts/agent_execution/test_execution_durable_core_migration.py",
    "tests/contexts/agent_execution/test_execution_identity_migration.py",
    "tests/contexts/agent_workspace/test_workspace_migration.py",
    "tests/contexts/due_diligence/test_dd_workbench_migration.py",
    "tests/contexts/mcp_registry/test_mcp_registry_migration.py",
    "tests/contexts/skill_registry/test_skill_registry_migration.py",
    "tests/contexts/structured_data/test_alembic_migrations.py",
)

# Values are reverse dependencies: tests that can observe a change in the key context.
CONTEXT_TESTS: dict[str, tuple[str, ...]] = {
    "ai_app": ("ai_app",),
    "document": ("ai", "document", "knowledge", "structured_data", "template"),
    "due_diligence": ("due_diligence",),
    "knowledge": ("ai", "document", "knowledge", "structured_data"),
    "mcp_registry": (
        "due_diligence",
        "mcp_registry",
        "skill_registry",
        "structured_data",
    ),
    "resource": ("resource",),
    "skill_registry": ("due_diligence", "skill_registry"),
    "structured_data": ("ai", "knowledge", "skill_registry", "structured_data"),
    "template": ("document", "template"),
    "agent_control_plane": ("agent_control_plane", "agent_execution", "agent_workspace"),
    "agent_execution": ("agent_execution", "agent_control_plane", "agent_workspace"),
    "agent_workspace": ("agent_workspace", "agent_control_plane"),
}

IGNORED_PREFIXES = (
    ".claude/",
    ".trae/",
    "docs/",
    "packages/mcp-server/",
    "packages/shared/",
    "packages/web/",
    "scripts/engineering/",
    "tests/engineering/",
)
IGNORED_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "turbo.json",
}
GLOBAL_FULL_PREFIXES = (
    ".github/",
    ".githooks/",
    "scripts/ci/",
)
GLOBAL_FULL_FILES = {
    "deploy/Dockerfile.postgres",
    "scripts/install-git-hooks",
}


@dataclass(frozen=True)
class Selection:
    mode: str
    reason: str
    pytest_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "pytest_paths": list(self.pytest_paths),
        }


def _normalize(path: str) -> str:
    normalized = path.removeprefix("./")
    if "\n" in normalized or "\r" in normalized:
        raise ValueError("changed path contains a newline")
    return normalized


def _full(reason: str) -> Selection:
    return Selection(mode="full", reason=reason)


def _is_ignored(path: str) -> bool:
    return path in IGNORED_FILES or path.endswith(".md") or path.startswith(IGNORED_PREFIXES)


def _select_test_change(relative: str) -> tuple[set[str], str | None]:
    if relative in {"tests/conftest.py", "tests/_paths.py"}:
        return set(), "global-test-fixture"

    parts = Path(relative).parts
    if len(parts) >= 4 and parts[:2] == ("tests", "contexts"):
        context = parts[2]
        if context not in set(CONTEXT_TESTS) | {"ai"}:
            return set(), f"unknown-test-context:{context}"
        if parts[-1] == "conftest.py" or not parts[-1].startswith("test_"):
            return {f"tests/contexts/{context}"}, None
        return {relative}, None

    direct_roots = (
        "tests/shared/",
        "tests/scripts/",
        "tests/internal_mcp/",
        "tests/composition/",
    )
    if relative.startswith(direct_roots) and relative.endswith(".py"):
        return {relative}, None
    if len(parts) == 2 and parts[0] == "tests" and parts[1].startswith("test_"):
        return {relative}, None

    return set(), f"broad-test-change:{relative}"


def _risk_targeted(
    selected: set[str], reasons: set[str], risk_tests: tuple[str, ...]
) -> Selection:
    selected.update(risk_tests)
    return Selection(
        mode="risk-targeted",
        reason="draft-risk:" + ",".join(sorted(reasons)),
        pytest_paths=tuple(sorted(selected)),
    )


def select_backend_tests(
    paths: Iterable[str], *, force_full: bool = False, draft: bool = False
) -> Selection:
    if force_full:
        return _full("explicit-full")

    selected = set(SMOKE_TESTS)
    reasons: set[str] = set()
    risk_reasons: set[str] = set()
    risk_tests = set(AGENT_RISK_TESTS)
    backend_seen = False

    for raw_path in paths:
        try:
            path = _normalize(raw_path)
        except ValueError:
            return _full("unsafe-changed-path")

        if _is_ignored(path):
            continue
        if path in GLOBAL_FULL_FILES or path.startswith(GLOBAL_FULL_PREFIXES):
            return _full(f"ci-infrastructure:{path}")
        if not path.startswith(BACKEND_PREFIX):
            return _full(f"unknown-repository-path:{path}")

        backend_seen = True
        relative = path.removeprefix(BACKEND_PREFIX)

        if relative.startswith("app/shared/") or relative in {
            "app/__init__.py",
            "app/celery_app.py",
            "app/config.py",
            "app/main.py",
            "pyproject.toml",
            "uv.lock",
        }:
            return _full(f"shared-runtime:{relative}")
        if relative.startswith("alembic/"):
            if not draft:
                return _full(f"database-migration:{relative}")
            risk_tests.update(MIGRATION_RISK_TESTS)
            risk_reasons.add(f"database-migration:{relative}")
            continue

        if relative.startswith("app/composition/"):
            if not draft:
                return _full(f"composition-root:{relative}")
            filename = Path(relative).name
            if filename.startswith("agent_transport_"):
                risk_tests.update(TRANSPORT_RISK_TESTS)
            elif filename.startswith("agent_erasure_"):
                risk_tests.update(ERASURE_RISK_TESTS)
            risk_reasons.add(f"composition-root:{relative}")
            continue

        if relative.startswith("app/contexts/"):
            parts = Path(relative).parts
            if len(parts) < 3:
                return _full(f"context-root:{relative}")
            context = parts[2]
            if context == "identity":
                return _full(f"security-context:{context}")
            if context in {"agent_control_plane", "agent_execution", "agent_workspace"}:
                if not draft:
                    return _full(f"agent-context:{context}")
                risk_reasons.add(f"agent-context:{context}")
                continue
            impacted = CONTEXT_TESTS.get(context)
            if impacted is None:
                return _full(f"unknown-context:{context}")
            for test_context in impacted:
                selected.add(f"tests/contexts/{test_context}")
            if context == "structured_data":
                selected.add("tests/internal_mcp")
            reasons.add(f"context:{context}")
            continue

        if relative.startswith("tests/"):
            test_paths, full_reason = _select_test_change(relative)
            if full_reason:
                return _full(full_reason)
            selected.update(test_paths)
            reasons.add(f"test:{relative}")
            continue

        return _full(f"unmapped-backend-path:{relative}")

    if not backend_seen:
        return Selection(mode="none", reason="no-backend-change")
    if risk_reasons:
        return _risk_targeted(selected, risk_reasons, tuple(sorted(risk_tests)))
    return Selection(
        mode="targeted",
        reason=",".join(sorted(reasons)) or "targeted-backend-change",
        pytest_paths=tuple(sorted(selected)),
    )


def _git_changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "-z", base, head],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def _write_github_output(path: Path, selection: Selection) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as output:
        output.write(f"mode={selection.mode}\n")
        output.write(f"reason={selection.reason}\n")
        output.write("pytest_paths<<METAEDU_PYTEST_PATHS\n")
        output.write("\n".join(selection.pytest_paths))
        output.write("\nMETAEDU_PYTEST_PATHS\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()

    if args.all:
        paths: list[str] = []
    elif args.base:
        paths = _git_changed_paths(args.base, args.head)
    elif args.paths:
        paths = args.paths
    else:
        parser.error("provide --all, --base REF, or explicit changed paths")

    selection = select_backend_tests(paths, force_full=args.all, draft=args.draft)
    print(json.dumps(selection.as_dict(), ensure_ascii=False, sort_keys=True))
    if args.github_output:
        _write_github_output(args.github_output, selection)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
