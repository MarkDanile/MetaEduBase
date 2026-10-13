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
    # TD-107: full 模式由 backend-full-shard-{1,2} + summary 接管；
    # 断言 full 模式的下游触发条件存在（needs.backend.outputs.mode）。
    assert "needs.backend.outputs.mode == 'full'" in workflow


def _summary_job_block(workflow: str) -> str:
    """Return the backend-full-summary job block as raw text."""
    marker = "  backend-full-summary:"
    start = workflow.index(marker)
    # The summary job is the last job before `frontend:` at top level.
    tail = workflow[start:]
    end = tail.index("\n  frontend:")
    return tail[:end]


def test_summary_job_always_runs_and_gates_on_shard_results() -> None:
    """TD-107 P0: shard 失败/取消/skipped 时 summary 必须运行并失败。

    GitHub branch protection 把 skipped 的 required check 视为通过，因此
    summary 绝不能用 job-level if 把自己 gate 在 shard success 之后；
    必须 always() 运行并在首个 step 显式断言两个 shard 的 result。
    """
    block = _summary_job_block(CI_WORKFLOW.read_text())
    # job-level if 必须恰好是 always()，不得混入 shard result 条件。
    assert "if: always()" in block
    assert "needs.backend-full-shard-1.result == 'success'" not in block.split("steps:")[0]
    assert "needs.backend-full-shard-2.result == 'success'" not in block.split("steps:")[0]
    # 首个 step 必须是 shard result 门禁，且对 failure / cancelled / skipped 一律 exit 1。
    first_step = block.split("steps:", maxsplit=1)[1].split("- name:", maxsplit=1)[1]
    assert "Gate on shard results" in first_step
    assert "needs.backend-full-shard-1.result" in first_step
    assert "needs.backend-full-shard-2.result" in first_step
    assert '!= "success"' in first_step
    assert "exit 1" in first_step


def test_summary_still_verifies_union_equals_serial_collection() -> None:
    """TD-107: summary 仍须校验 shard 合集与串行全集一致且无重叠。"""
    block = _summary_job_block(CI_WORKFLOW.read_text())
    assert "shard union does not match serial full collection" in block
    assert "comm -12" in block  # overlap 检查（无重复）
    assert "shard_backend_tests.py" in block


def test_backend_job_no_longer_runs_serial_full_pytest() -> None:
    """TD-107: full hermetic pytest 已移出 backend job（避免串行+并行双倍运行）。"""
    workflow = CI_WORKFLOW.read_text()
    backend_start = workflow.index("  backend:")
    backend_end = workflow.index("  backend-full-shard-1:")
    backend_block = workflow[backend_start:backend_end]
    assert "Backend full hermetic tests" not in backend_block
    assert "Backend scheduled hermetic tests" not in backend_block
    # PG 生命周期步骤在 full 模式下应跳过（full pytest 已委托分片）。
    assert "steps.backend_tests.outputs.mode != 'full'" in backend_block


def test_shard_jobs_use_independent_postgres_and_serial_in_shard() -> None:
    """TD-107: 每个 shard job 独立 PostgreSQL（独立容器名 + 独立初始化）。"""
    workflow = CI_WORKFLOW.read_text()
    shard1 = workflow.split("  backend-full-shard-1:")[1].split("  backend-full-shard-2:")[0]
    shard2 = workflow.split("  backend-full-shard-2:")[1].split("  backend-full-summary:")[0]
    assert "metaedu-ci-postgres-shard1" in shard1
    assert "metaedu-ci-postgres-shard2" in shard2
    assert "test_db_setup" in shard1 and "test_db_setup" in shard2
    # 每个分片内部串行：无 pytest -n / xdist 并行标志。
    for block in (shard1, shard2):
        assert "-n auto" not in block and "--numprocesses" not in block


def test_ci_rejects_every_unknown_backend_selector_mode() -> None:
    workflow = CI_WORKFLOW.read_text()
    assert "case \"$TEST_MODE\" in" in workflow
    assert "targeted|risk-targeted|full)" in workflow
    assert "Unknown backend test selection mode" in workflow


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
