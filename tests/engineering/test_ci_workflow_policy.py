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
    """TD-107 P0: full 模式下 shard 失败/取消/skipped 时 summary 必须运行并失败。

    GitHub branch protection 把 skipped 的 required check 视为通过，因此
    summary 绝不能用 job-level if 把自己 gate 在 shard success 之后；
    必须 always() 运行并在首个 step 显式断言两个 shard 的 result。
    """
    block = _summary_job_block(CI_WORKFLOW.read_text())
    # job-level if 必须以 always() 开头，且不得混入 shard result 条件。
    assert "if: always()" in block
    header = block.split("steps:")[0]
    assert "needs.backend-full-shard-1.result == 'success'" not in header
    assert "needs.backend-full-shard-2.result == 'success'" not in header
    # 首个 step 必须是 shard result 门禁，且对 failure / cancelled / skipped 一律 exit 1。
    first_step = block.split("steps:", maxsplit=1)[1].split("- name:", maxsplit=1)[1]
    assert "Gate on shard results" in first_step
    assert "needs.backend-full-shard-1.result" in first_step
    assert "needs.backend-full-shard-2.result" in first_step
    assert '!= "success"' in first_step
    assert "exit 1" in first_step


def test_summary_only_runs_in_full_mode() -> None:
    """TD-107 P0-1 修复: 非 full 模式 summary 必须 skipped（不得运行后失败）。

    targeted / risk-targeted / docs-only 模式下 shard jobs 被跳过；若 summary
    无条件 always() 运行，Gate step 会读到 skipped 而失败——这会把所有非
    full PR 打成红。因此 job-level if 必须同时含 always() 与
    needs.backend.outputs.mode == 'full'（needs 须含 backend 以读取 mode）。
    """
    block = _summary_job_block(CI_WORKFLOW.read_text())
    header = block.split("steps:")[0]
    assert "needs: [backend, backend-full-shard-1, backend-full-shard-2]" in header
    assert "always()" in header
    assert "needs.backend.outputs.mode == 'full'" in header


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


def _shard_region(workflow: str) -> str:
    start = workflow.index("  backend-full-shard-1:")
    end = workflow.index("  backend-full-summary:")
    return workflow[start:end]


def _code_lines(block: str) -> str:
    """剥离注释行，避免断言语料与注释说明互相污染。"""
    return "\n".join(
        line for line in block.splitlines() if not line.strip().startswith("#")
    )


def test_durations_baseline_resolved_once_not_per_shard() -> None:
    """TD-107 P2-1: 基线只在 backend job 单点解析，shard 消费同一 pinned 身份。"""
    workflow = CI_WORKFLOW.read_text()
    backend_block = workflow[
        workflow.index("  backend:") : workflow.index("  backend-full-shard-1:")
    ]
    assert "Resolve pinned durations baseline" in backend_block
    assert "resolve_durations_baseline.py" in backend_block
    # job outputs 把 pinned 身份传给下游
    assert "durations_baseline_status: ${{ steps.durations_baseline.outputs.baseline_status }}" in backend_block
    assert "durations_baseline_sha256: ${{ steps.durations_baseline.outputs.baseline_sha256 }}" in backend_block
    # shard 区域禁止任何“自己查最新”的逻辑
    shard_region = _shard_region(workflow)
    assert "resolve_durations_baseline" not in shard_region
    assert "gh run list" not in shard_region
    assert "actions/runs/" not in shard_region
    # 两个 shard 消费同一 pinned run id 与 sha256（各至少出现两次：verify + generate）
    assert shard_region.count("needs.backend.outputs.durations_baseline_run_id") >= 2
    assert shard_region.count("needs.backend.outputs.durations_baseline_sha256") >= 2
    # 跨 run 只读解析需要 actions: read 权限
    assert "actions: read" in workflow


def test_selected_baseline_download_failure_fails_loudly() -> None:
    """TD-107 P2-1: 已选定基线下载/校验失败 = 硬性失败，不得伪装冷启动。"""
    shard_region = _shard_region(CI_WORKFLOW.read_text())
    download_step = shard_region.split("Download pinned durations baseline", 1)[1].split(
        "- name:", maxsplit=1
    )[0]
    assert "continue-on-error" not in _code_lines(download_step)
    assert "if-no-files-found: ignore" not in _code_lines(download_step)
    # sha256 一致性 + 格式校验，任一失败 exit 1
    assert "sha256sum" in shard_region
    assert "baseline sha256 mismatch" in shard_region
    assert "--validate-durations" in shard_region


def test_cold_start_is_explicitly_logged_in_shards() -> None:
    """TD-107 P2-1: 冷启动允许等权回退，但必须在两个 shard 显式记录原因。"""
    shard_region = _shard_region(CI_WORKFLOW.read_text())
    assert shard_region.count("::warning title=durations baseline::") == 2
    assert shard_region.count("needs.backend.outputs.durations_baseline_reason") >= 2


def test_baseline_publication_gated_on_gate_and_union_success() -> None:
    """TD-107 P2-1: 失败 run 不得发布空白/不完整基线；JUnit 诊断仍保留。"""
    block = _summary_job_block(CI_WORKFLOW.read_text())
    build_step = block.split("Build next durations baseline", maxsplit=1)[1].split(
        "- name:", maxsplit=1
    )[0]
    # 无 if: always() → 默认 success() 门控：Gate / union 校验失败时不运行
    assert "if: always()" not in _code_lines(build_step)
    # 产物完整性（双 JUnit 齐备）+ 格式校验，缺一即失败
    assert "refusing to build baseline" in build_step
    assert "--validate-durations" in build_step
    upload_step = block.split("Upload next durations baseline", maxsplit=1)[1]
    assert "if: always()" not in _code_lines(upload_step)
    assert "if-no-files-found: error" in upload_step
    # shard 的 JUnit 诊断 artifact 仍在失败时上传
    shard_region = _shard_region(CI_WORKFLOW.read_text())
    upload_junit = shard_region.split("Upload shard-1 JUnit + collect list", maxsplit=1)[1].split(
        "- name:", maxsplit=1
    )[0]
    assert "if: always()" in upload_junit


def test_baseline_builder_maps_classnames_via_shard_lists() -> None:
    """TD-107 P2-1: pytest JUnit 无 file 属性——构建器必须经 shard 清单映射。"""
    block = _summary_job_block(CI_WORKFLOW.read_text())
    build_step = block.split("Build next durations baseline", maxsplit=1)[1].split(
        "- name:", maxsplit=1
    )[0]
    assert "shard1.list" in build_step and "shard2.list" in build_step
    assert "classname" in build_step
    # 不再容忍解析失败/空产物静默通过
    assert "except ET.ParseError" not in build_step
    assert "no testcase durations extracted" in build_step


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
