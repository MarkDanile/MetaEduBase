from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "detect-change-scopes"


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


def test_required_check_names_remain_stable_with_backend_aggregation() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "\n  backend:\n    name: Backend\n" in workflow
    assert "\n  frontend:\n    name: Frontend\n" in workflow
    assert "\n  engineering-docs:\n    name: Engineering docs\n" in workflow
    assert "      - backend-checks\n      - backend-tests\n" in workflow
