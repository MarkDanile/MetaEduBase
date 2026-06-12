from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINEERING_CHECKER = (
    REPO_ROOT / "scripts" / "engineering" / "check_engineering_docs.py"
)
SCRIPT_WRAPPER = REPO_ROOT / "scripts" / "check-engineering-docs"


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def make_minimal_docs(root: Path) -> None:
    write(
        root / "docs/03-engineering-governance/current-work.md",
        """
        # 当前开发工作台

        ## 当前进行中

        当前无进行中任务。

        ## 下一批候选任务

        | 任务 | 状态 | 优先级 | 领域 | 下一步 |
        |------|------|--------|------|--------|
        | TD-001 示例任务 | 🔵 就绪 | P2 | Docs | 处理文档。 |

        ## 最近完成

        | 日期 | 任务 | 状态 | 摘要 | 事实源 |
        |------|------|------|------|--------|
        | 2026-06-05 | DOC-001 示例完成 | 🟢 完成 | 已完成。 | docs/03-engineering-governance/work-log.md |
        """,
    )
    write(
        root / "docs/03-engineering-governance/work-log.md",
        """
        # 工程工作日志索引

        ## 索引

        | 日期 | 任务 | 类型 | PR 可选 | Merge Commit 可选 | 归档位置 |
        |------|------|------|----|-------------------|----------|
        | 2026-06-05 | DOC-001 示例完成 | 文档 |  |  | `docs/03-engineering-governance/current-work.md` |
        """,
    )
    write(
        root / "docs/03-engineering-governance/technical-debt.md",
        """
        # 技术债总账

        ## 任务总览

        | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
        |------|------|------|--------|------|--------|
        | TD-001 | 示例任务 | 🔵 就绪 | P2 | Docs | - |
        """,
    )
    write(
        root / "docs/02-delivery-plans/01-specs/example.md",
        """
        # Example Spec

        See [work log](../../03-engineering-governance/work-log.md).
        """,
    )
    write(
        root / "docs/02-delivery-plans/02-plans/example-plan.md",
        """
        # Example Plan

        > 状态：🔵 就绪

        - [ ] 未完成计划项。
        """,
    )
    write(
        root / "AGENTS.md",
        """
        # AGENTS.md

        本文件是跨 AI IDE 的仓库入口，只保留导航和开工顺序。规则正文以 `docs/` 下的事实源为准，不在入口文件复制第二份。
        """,
    )
    write(
        root / "CLAUDE.md",
        """
        # CLAUDE.md

        本文件是 Claude Code 的仓库入口，只保留导航和开工顺序。规则正文以 `docs/` 下的事实源为准，不在入口文件复制第二份。
        """,
    )


def run_checker(
    root: Path, checker: Path = ENGINEERING_CHECKER
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(checker), "--root", str(root)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def run_checker_inproc(root: Path) -> "subprocess.CompletedProcess[str]":
    """DOC-060: 在 pytest 进程内直接调 check_engineering_docs.main，
    让 `unittest.mock.patch` 能影响子 check（subprocess 隔离 mock 不生效）。
    返回的 CompletedProcess 与 run_checker 形状一致（returncode + stdout + stderr）。"""
    import io
    import contextlib
    from scripts.engineering.check_engineering_docs import main as _main

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    rc = 1
    with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
        try:
            rc = _main(["--root", str(root)])
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    return subprocess.CompletedProcess(
        args=["inproc", "--root", str(root)],
        returncode=rc,
        stdout=buf_out.getvalue(),
        stderr=buf_err.getvalue(),
    )


def test_passes_minimal_valid_docs(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "engineering docs checks passed" in result.stdout


def test_scripts_wrapper_delegates_to_tools_checker(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)

    result = run_checker(tmp_path, SCRIPT_WRAPPER)

    assert result.returncode == 0, result.stderr
    assert "engineering docs checks passed" in result.stdout


def test_fails_when_candidate_contains_completed_task(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    current_work.write_text(
        current_work.read_text(encoding="utf-8").replace("🔵 就绪", "🟢 完成", 1),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "候选区不得出现完成任务" in result.stderr
    assert "current-work.md" in result.stderr


def test_fails_when_recent_completed_exceeds_twenty_rows(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    rows = "\n".join(
        f"| 2026-06-05 | DOC-00{i} 示例完成 | 🟢 完成 | 已完成。 | docs/03-engineering-governance/work-log.md |"
        for i in range(1, 22)
    )
    current_work.write_text(
        textwrap.dedent(
            f"""
            # 当前开发工作台

            ## 当前进行中

            当前无进行中任务。

            ## 下一批候选任务

            | 任务 | 状态 | 优先级 | 领域 | 下一步 |
            |------|------|--------|------|--------|
            | TD-001 示例任务 | 🔵 就绪 | P2 | Docs | 处理文档。 |

            ## 最近完成

            | 日期 | 任务 | 状态 | 摘要 | 事实源 |
            |------|------|------|------|--------|
            {rows}
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "最近完成最多 20 行" in result.stderr
    assert "只保留最新 12 行" in result.stderr


def test_fails_when_recent_completed_summary_is_too_long(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    current_work = tmp_path / "docs/03-engineering-governance/current-work.md"
    current_work.write_text(
        current_work.read_text(encoding="utf-8").replace(
            "已完成。",
            "这是一段过长的最近完成摘要，" * 20,
            1,
        ),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "最近完成摘要过长" in result.stderr


def test_fails_when_completed_plan_has_active_checkbox(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    plan = tmp_path / "docs/02-delivery-plans/02-plans/example-plan.md"
    plan.write_text(
        plan.read_text(encoding="utf-8").replace("状态：🔵 就绪", "状态：🟢 完成"),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "已完成 plan 不得残留活动式" in result.stderr


def test_fails_when_markdown_link_target_is_missing(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/02-delivery-plans/01-specs/broken.md",
        """
        # Broken

        See [missing](../../03-engineering-governance/missing.md).
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "Markdown 链接目标不存在" in result.stderr


def test_fails_when_work_log_index_row_is_deleted(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    work_log = tmp_path / "docs/03-engineering-governance/work-log.md"
    work_log.write_text(
        "\n".join(
            line
            for line in work_log.read_text(encoding="utf-8").splitlines()
            if "DOC-001 示例完成" not in line
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "work-log.md 默认只新增索引" in result.stderr


def test_allows_work_log_index_row_path_migration(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "initial",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    work_log = tmp_path / "docs/03-engineering-governance/work-log.md"
    work_log.write_text(
        work_log.read_text(encoding="utf-8").replace(
            "docs/03-engineering-governance/current-work.md",
            "docs/03-engineering-governance/README.md",
        ),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert "work-log.md 默认只新增索引" not in result.stderr


def test_fails_when_full_pytest_passed_claim_has_no_evidence(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/02-delivery-plans/01-specs/claim.md",
        """
        # Claim

        验证摘要：全量 pytest 152 passed。
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "验证通过声明缺少可复核证据" in result.stderr


def test_fails_when_debt_overview_and_detail_status_diverge(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    debt = tmp_path / "docs/03-engineering-governance/technical-debt.md"
    debt.write_text(
        textwrap.dedent(
            """
            # 技术债总账

            ## 任务总览

            | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
            |------|------|------|--------|------|--------|
            | TD-001 | 示例任务 | 🟢 完成 | P2 | Docs | PR #1 |

            ## 任务详情

            ### TD-001: 示例任务

            状态：⚫ 待办

            **交付记录**
            - 未完成。
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "技术债总览和详情状态不一致" in result.stderr


def test_fails_when_completed_debt_detail_still_says_unfinished(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    debt = tmp_path / "docs/03-engineering-governance/technical-debt.md"
    debt.write_text(
        textwrap.dedent(
            """
            # 技术债总账

            ## 任务总览

            | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
            |------|------|------|--------|------|--------|
            | TD-001 | 示例任务 | 🟢 完成 | P2 | Docs | PR #1 |

            ## 任务详情

            ### TD-001: 示例任务

            状态：🟢 完成

            **交付记录**
            - 未完成。
            """
        ).lstrip(),
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "完成任务的交付记录仍写未完成" in result.stderr


def test_fails_when_new_followup_id_is_used(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/02-delivery-plans/01-specs/followup.md",
        """
        # Followup

        后续任务：TD-999-FOLLOWUP。
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "发现临时 follow-up 编号" in result.stderr


def test_fails_when_done_backlog_task_has_no_index_or_fact_source(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/01-product-planning/04-backlog.md",
        """
        # Product Backlog

        ## Backlog

        | ID | 类型 | 状态 | 优先级 | 里程碑 | 摘要 | 下一步 | External |
        |----|------|------|--------|--------|------|--------|----------|
        | DOC-999 | DOC | 🟢 Done | P2 | P3 | 示例完成任务 | 已完成 |  |
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "缺少 work-log 或明确事实源" in result.stderr


def test_fails_when_agents_and_claude_entries_drift(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8") + "\n额外入口规则正文。\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "AGENTS.md 与 CLAUDE.md 的导航内容不一致" in result.stderr


def test_fails_when_ide_rule_entry_contains_body_text(tmp_path: Path) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / ".claude/rules/quality-gates.md",
        """
        # Quality Gates

        本文件仅作为 Claude Code 的兼容入口。

        共享规则事实源已迁移到：

        `docs/03-engineering-governance/01-rules/quality-gates.md`

        请以该文件为准，不要在 `.claude/rules/` 中维护第二份规则正文。

        ## 重复规则正文

        这里不应该复制完整规则。
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "IDE 兼容规则入口过长" in result.stderr


def test_fails_when_implemented_gate_candidate_has_no_script_mapping(
    tmp_path: Path,
) -> None:
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/03-engineering-governance/01-rules/quality-gates.md",
        """
        # Quality Gates

        ## 脚本门禁候选清单

        | 候选门禁 | 当前状态 | 触发价值 |
        |----------|----------|----------|
        | 未登记的新脚本门禁 | 已实现 | 示例 |
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "脚本门禁候选标为已实现" in result.stderr


def test_source_size_no_large_files_passes(tmp_path: Path) -> None:
    """No files >1000 lines → gate passes."""
    make_minimal_docs(tmp_path)
    # Create a small source file so the scan has something to look at.
    write(tmp_path / "packages" / "server-python" / "app" / "small.py", "x = 1\n")
    write(
        tmp_path / "docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md",
        """
        # TD-032 源码文件行数基线

        ## 文件清单

        ### >1000 行

        | 文件 | 行数 | 状态 | 例外 / 拆分说明 |
        |------|------|------|-----------------|
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "engineering docs checks passed" in result.stdout


def test_source_size_unregistered_large_file_fails(tmp_path: Path) -> None:
    """A file >1000 lines not registered in baseline → gate fails."""
    make_minimal_docs(tmp_path)
    # Create a large source file.
    large_content = "\n".join(["x = 1"] * 1001) + "\n"
    write(tmp_path / "packages" / "server-python" / "app" / "huge.py", large_content)
    write(
        tmp_path / "docs/03-engineering-governance/02-baselines/td-032-source-file-sizes.md",
        """
        # TD-032 源码文件行数基线

        ## 文件清单

        ### >1000 行

        | 文件 | 行数 | 状态 | 例外 / 拆分说明 |
        |------|------|------|-----------------|
        """,
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "huge.py" in result.stderr
    assert "超过 1000 行硬限制" in result.stderr


def test_parent_and_child_req_with_different_status_do_not_collide(
    tmp_path: Path,
) -> None:
    """REQ-002 (parent) and REQ-002-3 (child) with different statuses must not
    trip `req-status-consistency` (DOC-056).

    Prior to DOC-056, `REQ_ID_RE.search` matched `REQ-002` inside `REQ-002-3`
    and merged both into the same status set, causing false-positive
    `状态不一致` warnings whenever a child task status diverged from its
    parent. After the fix, parent and child are kept as separate task ids.
    """
    make_minimal_docs(tmp_path)
    write(
        tmp_path / "docs/01-product-planning/04-backlog.md",
        """
        # Product Backlog

        ## Backlog

        | ID | 类型 | 状态 | 优先级 | 里程碑 | 摘要 | 下一步 | External |
        |----|------|------|--------|--------|------|--------|----------|
        | REQ-002 | REQ | 🔵 Ready | P2 | P2 | 父任务 | 待子任务链 |  |
        | REQ-002-3 | REQ | 🟢 Done | P2 | P2 | 子任务 | 已完成 |  |
        """,
    )
    write(
        tmp_path / "docs/01-product-planning/02-milestones/example.md",
        """
        # Example Milestone

        | ID | 状态 | 标题 | 事实源 |
        |----|------|------|------|
        | REQ-002 | 🔵 Ready | 父任务 | - |
        | REQ-002-3 | 🟢 Done | 子任务 | - |
        """,
    )
    write(
        tmp_path / "docs/03-engineering-governance/current-work.md",
        """
        # 当前开发工作台

        ## 当前进行中

        | 任务 | 状态 | 优先级 | 领域 | 当前进展 | 下一步 | 验证 |
        |------|------|--------|------|----------|--------|------|
        | REQ-002 父任务 | 🔵 Ready | P2 | Docs | 待子任务链 | 等子任务 | - |

        ## 下一批候选任务

        | 任务 | 状态 | 优先级 | 领域 | 下一步 |
        |------|------|--------|------|--------|
        | 候选示例 | ⚫ Candidate | P3 | Docs | 调研。 |

        ## 最近完成

        | 日期 | 任务 | 状态 | 摘要 | 事实源 |
        |------|------|------|------|------|
        | 2026-06-10 | REQ-002-3 子任务 | 🟢 Done | 已完成。 | docs/03-engineering-governance/work-log.md |
        """,
    )

    result = run_checker(tmp_path)

    assert "状态不一致" not in result.stderr, result.stderr
    assert "req-status-consistency" not in result.stderr, result.stderr


# DOC-060: 任务卡 vs 代码 / 声明语义校验。`_common.check_task_card_claim_vs_code`
# 通用函数 + `scripts/engineering/checks/task_card_claims.py` 注册 2 个 check。
# 任务卡 L2115 明确要求"新增测试 test_task_card_stale_completion +
# test_task_card_stale_residual 各 1 个锁定"。本测试通过 minimal docs 模拟
# 假完成 / 假残留量场景，验证脚本能精确捕获并报告对应的
# task-card-stale-* issue；白名单（KNOWN_ISSUES）通过 mock 掉让 issue 暴露。
def test_fails_when_completed_debt_card_uses_open_pr_state(tmp_path: Path) -> None:
    """DOC-060: 已完成任务卡 PR 实际 state != MERGED 时报
    `task-card-stale-completion` issue。"""
    from unittest.mock import patch

    from scripts.engineering.checks import _common

    make_minimal_docs(tmp_path)
    debt = tmp_path / "docs/03-engineering-governance/technical-debt.md"
    debt.write_text(
        textwrap.dedent(
            """
            # 技术债总账

            ## 任务总览

            | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
            |------|------|------|--------|------|--------|
            | TD-001 | 测试任务 | 🟢 完成 | P2 | Docs | - |

            ### TD-001: 测试任务

            状态：🟢 完成

            | 交付 PR | [PR #99](https://github.com/MarkDanile/MetaEduBase/pull/99) |
            | Merge Commit | `1234567890abcdef1234567890abcdef12345678` (squash merge) |
            """
        ).lstrip()
    )

    # DOC-063: 默认走 git plumbing 校验（`git rev-parse --verify <merge_commit>`）。
    # mock `is_known` 永远返回 False（绕过 KNOWN_ISSUES 白名单），
    # 并把 `check_merge_commit_in_git_history` 强制返回 NOT_MERGED 状态
    # 模拟"任务卡 PR 链接存在但 merge commit 不在 git 历史"场景。
    # 注：用 run_checker_inproc 走 pytest 进程内调用，让 mock 生效；
    # 普通 run_checker 走 subprocess.run 会与子进程 mock 隔离。
    with patch.object(_common, "is_known", return_value=False), \
         patch.object(
             _common,
             "check_merge_commit_in_git_history",
             return_value=("NOT_MERGED", "mock: merge commit 不在 git 历史"),
         ):
        result = run_checker_inproc(tmp_path)

    # 退码 1（active issue 存在）；stderr 含 git rev-parse 校验 NOT_MERGED 描述。
    # 注：check_engineering_docs.print_issue 用 issue.message 输出，
    # issue.code 不会进 stderr，所以这里断言 message 关键词。
    assert result.returncode == 1, result.stderr
    assert "git rev-parse 校验" in result.stderr
    assert "TD-001" in result.stderr
    assert "PR #99" in result.stderr or "#99" in result.stderr
    assert "NOT_MERGED" in result.stderr


def test_fails_when_residual_count_claim_diverges_from_ripgrep(tmp_path: Path) -> None:
    """DOC-060: 残留量声明与 `rg -c` 实测命中数偏差时报
    `task-card-stale-residual` issue。"""
    from unittest.mock import patch

    from scripts.engineering.checks import _common

    make_minimal_docs(tmp_path)
    debt = tmp_path / "docs/03-engineering-governance/technical-debt.md"
    debt.write_text(
        textwrap.dedent(
            """
            # 技术债总账

            ## 任务总览

            | 编号 | 任务 | 状态 | 优先级 | 领域 | 事实源 |
            |------|------|------|--------|------|--------|
            | TD-001 | 测试任务 | 🟢 完成 | P2 | Docs | - |

            ### TD-001: 测试任务

            状态：🟢 完成

            **事实源**

            - 目标文件 `docs/03-engineering-governance/technical-debt.md`
            - 残留量声明：23 处 `liquid-card`
            """
        ).lstrip()
    )

    # mock `is_known` 返回 False（绕白名单），让 check_engineering_docs 报 issue。
    # 沙箱下 `rg` 不可用，python fallback 仍能跑出真实命中数 1（technical-debt.md
    # 第 1 次出现 "liquid-card" 就是 L10 的 claim 行自身）。
    # 走 inproc 调用，让 mock 生效。
    with patch.object(_common, "is_known", return_value=False):
        result = run_checker_inproc(tmp_path)

    # 退码 1；stderr 含 task-card-stale-residual。
    assert result.returncode == 1, result.stderr
    # print_issue 用 issue.message，code 不直接出现在 stderr。
    # 验证 message 含关键标识："残留量声明" + 声明值 23 + 实测值 1。
    assert "残留量声明" in result.stderr
    assert "23" in result.stderr
    assert "TD-001" in result.stderr
