from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_listens_for_draft_ready_transitions() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert (
        "types: [opened, synchronize, reopened, ready_for_review, converted_to_draft]"
        in workflow
    )


def test_ci_passes_draft_state_to_selector() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert "PR_DRAFT: ${{ github.event.pull_request.draft || false }}" in workflow
    assert 'selector_args+=(--draft)' in workflow


def test_ci_runs_risk_targeted_through_targeted_step() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert "steps.backend_tests.outputs.mode == 'risk-targeted'" in workflow
    assert "steps.backend_tests.outputs.mode == 'full'" in workflow


def test_risk_targeted_defers_mypy_to_ready_full() -> None:
    workflow = CI_WORKFLOW.read_text()
    mypy_step = workflow.split("- name: mypy baseline", maxsplit=1)[1].split(
        "- name:", maxsplit=1
    )[0]
    assert "steps.backend_tests.outputs.mode != 'risk-targeted'" in mypy_step


def test_required_check_names_remain_stable() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert "'Backend iteration' || 'Backend'" in workflow
    assert "name: Frontend" in workflow
    assert "name: Engineering docs" in workflow


def test_draft_result_cannot_reuse_required_backend_check_name() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert "github.event.pull_request.draft && 'Backend iteration'" in workflow
    assert "github.event_name == 'pull_request'" in workflow
