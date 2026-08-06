from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "select_backend_tests.py"
SPEC = importlib.util.spec_from_file_location("backend_test_selection", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
select_backend_tests = MODULE.select_backend_tests


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ("ai_app", {"tests/contexts/ai_app"}),
        ("resource", {"tests/contexts/resource"}),
        ("due_diligence", {"tests/contexts/due_diligence"}),
        (
            "skill_registry",
            {"tests/contexts/skill_registry", "tests/contexts/due_diligence"},
        ),
        (
            "mcp_registry",
            {
                "tests/contexts/mcp_registry",
                "tests/contexts/skill_registry",
                "tests/contexts/due_diligence",
                "tests/contexts/structured_data",
            },
        ),
        ("template", {"tests/contexts/template", "tests/contexts/document"}),
    ],
)
def test_context_reverse_dependencies_are_selected(context: str, expected: set[str]) -> None:
    result = select_backend_tests(
        [f"packages/server-python/app/contexts/{context}/application/service.py"]
    )
    assert result.mode == "targeted"
    assert expected.issubset(set(result.pytest_paths))
    assert "tests/shared/test_health.py" in result.pytest_paths


def test_structured_data_adds_legacy_ai_and_internal_mcp() -> None:
    result = select_backend_tests(
        ["packages/server-python/app/contexts/structured_data/application/query_service.py"]
    )
    assert result.mode == "targeted"
    assert {
        "tests/contexts/structured_data",
        "tests/contexts/skill_registry",
        "tests/contexts/knowledge",
        "tests/contexts/ai",
        "tests/internal_mcp",
    }.issubset(set(result.pytest_paths))


def test_document_and_knowledge_include_cross_context_consumers() -> None:
    result = select_backend_tests(
        [
            "packages/server-python/app/contexts/document/application/cleanup.py",
            "packages/server-python/app/contexts/knowledge/application/ai_chat_service.py",
        ]
    )
    assert result.mode == "targeted"
    assert {
        "tests/contexts/document",
        "tests/contexts/knowledge",
        "tests/contexts/structured_data",
        "tests/contexts/template",
        "tests/contexts/ai",
    }.issubset(set(result.pytest_paths))


@pytest.mark.parametrize(
    "path",
    [
        "packages/server-python/app/main.py",
        "packages/server-python/app/shared/infrastructure/database.py",
        "packages/server-python/app/contexts/identity/application/auth_service.py",
        "packages/server-python/alembic/versions/999_example.py",
        "packages/server-python/tests/conftest.py",
        ".github/workflows/ci.yml",
        "new-runtime/file.py",
    ],
)
def test_high_risk_and_unknown_paths_fail_closed_to_full(path: str) -> None:
    result = select_backend_tests([path])
    assert result.mode == "full"
    assert result.pytest_paths == ()


def test_changed_test_file_runs_directly_with_smoke() -> None:
    path = "packages/server-python/tests/contexts/resource/test_resource.py"
    result = select_backend_tests([path])
    assert result.mode == "targeted"
    assert "tests/contexts/resource/test_resource.py" in result.pytest_paths
    assert "tests/shared/test_health.py" in result.pytest_paths


def test_context_conftest_runs_whole_context() -> None:
    result = select_backend_tests(
        ["packages/server-python/tests/contexts/mcp_registry/conftest.py"]
    )
    assert result.mode == "targeted"
    assert "tests/contexts/mcp_registry" in result.pytest_paths


def test_irrelevant_documentation_returns_none() -> None:
    result = select_backend_tests(["docs/README.md", "packages/web/src/main.ts"])
    assert result.mode == "none"
    assert result.pytest_paths == ()


def test_paths_are_deduplicated_and_sorted() -> None:
    path = "packages/server-python/app/contexts/resource/interfaces/api/router.py"
    result = select_backend_tests([path, path])
    assert result.pytest_paths == tuple(sorted(set(result.pytest_paths)))


def test_cli_writes_json_and_github_outputs(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--github-output",
            str(output),
            "packages/server-python/app/contexts/resource/interfaces/api/router.py",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["mode"] == "targeted"
    github_output = output.read_text()
    assert "mode=targeted\n" in github_output
    assert "tests/contexts/resource" in github_output


def test_cli_draft_writes_risk_targeted_mode(tmp_path: Path) -> None:
    output = tmp_path / "github-output"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--draft",
            "--github-output",
            str(output),
            "packages/server-python/alembic/versions/040_transport_external_scope.py",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["mode"] == "risk-targeted"
    assert "mode=risk-targeted\n" in output.read_text()


def test_explicit_full_mode() -> None:
    result = select_backend_tests([], force_full=True)
    assert result.mode == "full"
    assert result.reason == "explicit-full"


def test_draft_migration_uses_risk_targeted_suite() -> None:
    result = select_backend_tests(
        ["packages/server-python/alembic/versions/040_transport_external_scope.py"],
        draft=True,
    )
    assert result.mode == "risk-targeted"
    assert "draft" in result.reason
    assert "tests/composition/test_agent_transport_schema.py" in result.pytest_paths
    assert "tests/contexts/structured_data/test_alembic_migrations.py" in result.pytest_paths


def test_ready_migration_remains_full() -> None:
    result = select_backend_tests(
        ["packages/server-python/alembic/versions/040_transport_external_scope.py"],
        draft=False,
    )
    assert result.mode == "full"


def test_draft_agent_composition_uses_risk_targeted_suite() -> None:
    result = select_backend_tests(
        ["packages/server-python/app/composition/agent_transport_backfill.py"],
        draft=True,
    )
    assert result.mode == "risk-targeted"
    assert "tests/composition/test_agent_transport_backfill.py" in result.pytest_paths
    assert "tests/contexts/agent_control_plane/test_run_api.py" in result.pytest_paths
    assert "tests/contexts/agent_execution/test_run_coordinator.py" in result.pytest_paths
    assert "tests/contexts/agent_workspace" in result.pytest_paths


def test_ready_agent_composition_remains_full() -> None:
    result = select_backend_tests(
        ["packages/server-python/app/composition/agent_transport_backfill.py"],
        draft=False,
    )
    assert result.mode == "full"


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/ci.yml",
        "packages/server-python/app/shared/infrastructure/database.py",
        "packages/server-python/app/contexts/identity/application/auth_service.py",
        "new-runtime/file.py",
    ],
)
def test_draft_always_full_paths_cannot_use_risk_targeted(path: str) -> None:
    result = select_backend_tests([path], draft=True)
    assert result.mode == "full"


def test_agent_test_file_stays_targeted() -> None:
    result = select_backend_tests(
        ["packages/server-python/tests/contexts/agent_execution/test_run_api.py"],
        draft=True,
    )
    assert result.mode == "targeted"
    assert "tests/contexts/agent_execution/test_run_api.py" in result.pytest_paths


def test_always_full_path_dominates_draft_risk_path() -> None:
    result = select_backend_tests(
        [
            "packages/server-python/alembic/versions/040_transport_external_scope.py",
            "packages/server-python/app/shared/infrastructure/database.py",
        ],
        draft=True,
    )
    assert result.mode == "full"
    assert result.reason.startswith("shared-runtime:")


def test_draft_risk_keeps_leaf_context_reverse_dependencies() -> None:
    result = select_backend_tests(
        [
            "packages/server-python/alembic/versions/040_transport_external_scope.py",
            "packages/server-python/app/contexts/resource/application/service.py",
        ],
        draft=True,
    )
    assert result.mode == "risk-targeted"
    assert "tests/contexts/resource" in result.pytest_paths
    assert "tests/composition/test_agent_transport_schema.py" in result.pytest_paths
