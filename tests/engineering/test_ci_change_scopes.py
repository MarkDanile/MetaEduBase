from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "detect-change-scopes"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _classify(*paths: str) -> dict[str, str]:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--", *paths],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines())


def test_docs_only_activates_engineering() -> None:
    assert _classify("docs/README.md") == {
        "backend": "false",
        "frontend": "false",
        "mcp": "false",
        "engineering": "true",
        "engineering_tests": "false",
        "full": "false",
    }


def test_backend_package_markdown_is_engineering_only() -> None:
    scopes = _classify("packages/server-python/README.md")
    assert scopes["engineering"] == "true"
    assert scopes["backend"] == "false"


def test_empty_change_set_activates_nothing() -> None:
    assert _classify() == {
        "backend": "false",
        "frontend": "false",
        "mcp": "false",
        "engineering": "false",
        "engineering_tests": "false",
        "full": "false",
    }


def test_each_runtime_scope_is_independent() -> None:
    assert _classify("packages/server-python/app/main.py")["backend"] == "true"
    assert _classify("packages/web/src/main.ts")["frontend"] == "true"
    assert _classify("packages/mcp-server/uv.lock")["mcp"] == "true"


def test_ci_and_unknown_paths_fail_safe_to_all_scopes() -> None:
    for path in (".github/workflows/ci.yml", "new-runtime/file.txt"):
        scopes = _classify(path)
        assert all(
            scopes[key] == "true"
            for key in ("backend", "frontend", "mcp", "engineering", "engineering_tests")
        )
        assert scopes["full"] == "false"


def test_engineering_implementation_activates_its_tests() -> None:
    scopes = _classify("scripts/engineering/checks/current_work.py")
    assert scopes["engineering"] == "true"
    assert scopes["engineering_tests"] == "true"


def test_force_all_marks_full_run() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--all"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    scopes = dict(line.split("=", 1) for line in result.stdout.splitlines())
    assert all(value == "true" for value in scopes.values())


def test_github_output_matches_stdout() -> None:
    with tempfile.NamedTemporaryFile(delete=False) as output:
        output_path = output.name
    try:
        result = subprocess.run(
            ["bash", str(SCRIPT), "--github-output", output_path, "--", "docs/README.md"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert Path(output_path).read_text() == result.stdout
    finally:
        os.unlink(output_path)


def test_ci_uses_node24_actions_and_hermetic_pytest_boundary() -> None:
    workflow = WORKFLOW.read_text()
    expected_actions = {
        "actions/checkout@v7",
        "actions/setup-node@v7",
        "pnpm/action-setup@v6",
        "astral-sh/setup-uv@v9",
        "docker/setup-buildx-action@v4",
        "docker/build-push-action@v7",
    }
    for action in expected_actions:
        assert action in workflow

    legacy_actions = {
        "actions/checkout@v4",
        "actions/setup-node@v4",
        "pnpm/action-setup@v4",
        "astral-sh/setup-uv@v6",
        "docker/setup-buildx-action@v3",
        "docker/build-push-action@v6",
    }
    for action in legacy_actions:
        assert action not in workflow

    assert "not slow" not in workflow
    assert workflow.count('-m "not external_network"') == 3
    assert workflow.count("prune-cache: true") == 2
