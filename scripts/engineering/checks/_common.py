"""Shared dataclasses, constants, regexes, and small parse helpers.

集中放 cross-check 公共符号。所有聚焦模块从此处 import；本模块**不**引用任何
聚焦模块，避免循环。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

DOC_GLOBS: tuple[str, ...] = (
    "docs/*.md",
    "docs/03-engineering-governance/*.md",
    "docs/03-engineering-governance/02-baselines/*.md",
    "docs/03-engineering-governance/03-matrices/*.md",
    "docs/03-engineering-governance/04-retrospectives/*.md",
    "docs/03-engineering-governance/01-rules/*.md",
    "docs/01-product-planning/*.md",
    "docs/01-product-planning/*/*.md",
    "docs/02-delivery-plans/01-specs/*.md",
    "docs/02-delivery-plans/02-plans/*.md",
)

CURRENT_WORK_RECENT_LIMIT = 20
CURRENT_WORK_RECENT_SUMMARY_LIMIT = 220
LEGACY_DOC_ROOT_NAMES: tuple[str, ...] = (
    "engineering",
    "specs",
    "plans",
    "product",
    "superpowers",
)
TASK_ID_RE = re.compile(r"\b(?:REQ|TD|DOC|BUG|APP)-\d{3}\b")
# REQ-NNN (parent) and REQ-NNN-K (child subtask) are distinct task ids.
# DOC-056: prior `\bREQ-\d{3}\b` matched `REQ-002` inside `REQ-002-3`,
# causing `check_req_status_consistency` to merge parent/child statuses.
# The trailing `(?![-\d])` prevents backtracking into a parent prefix
# while still allowing whitespace / `.md` / end-of-string after the id.
REQ_ID_RE = re.compile(r"\bREQ-\d{3}(?:-\d+)?(?![-\d])")
FOLLOWUP_ID_RE = re.compile(r"\b(?:REQ|TD)-\d{3}-FOLLOWUP\b")
LEGACY_FOLLOWUP_REFS: frozenset[tuple[str, str]] = frozenset(
    {
        ("docs/02-delivery-plans/01-specs/2026-06-05-td-006-llm-model-fallback.md", "TD-006-FOLLOWUP"),
        ("docs/02-delivery-plans/01-specs/2026-06-05-td-007-databaseview-vue-query.md", "TD-007-FOLLOWUP"),
        ("docs/03-engineering-governance/technical-debt.md", "TD-002-FOLLOWUP"),
        ("docs/03-engineering-governance/work-log.md", "TD-002-FOLLOWUP"),
    }
)
BACKLOG_DONE_TYPES: frozenset[str] = frozenset({"REQ", "DOC", "BUG", "APP"})
SCRIPTED_GATE_CANDIDATES: frozenset[str] = frozenset(
    {
        "`current-work.md` 最近完成最多 20 行，超过后只保留最新 12 行",
        "`current-work.md` 下一批候选最多 3 行，且不允许 `🟢 完成`",
        "已完成任务不得残留 `未运行`、`待提交`、`以最终回复为准` 等占位",
        "禁止把 `REQ-xxx-FOLLOWUP` / `TD-xxx-FOLLOWUP` 作为长期任务编号",
        "`Done` 任务在 Backlog / current-work / work-log 之间有最小索引闭环",
        "旧 docs 路径残留检查",
        "Markdown 相对链接存在性检查",
        "AGENTS.md / CLAUDE.md 与 IDE 兼容入口同步检查",
        "源码文件超过 1000 行硬限制检查",
    }
)

KNOWN_ISSUES: tuple[tuple[str, str, str], ...] = (
    # DOC-060 历史债：14 个 task 卡事实源段未按 DOC-060 模板补
    # `target_files` / `claim_pattern` 段。DOC-060 收口后由独立 PR 清理。
    # 白名单匹配规则见 `is_known`：精确到 task_id 维度，不影响新 task 触发的
    # 新 issue 报告。
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-055",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：DOC-055 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-058",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：DOC-058 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-059",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：DOC-059 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-060",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：DOC-060 自身任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-008",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-008 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-025",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-025 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-030",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-030 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-032",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-032 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-035",
        "task-card-stale-residual",
        "DOC-060 历史债：TD-035 任务卡『3 处 Yoda 条件』声明对整段描述做子串匹配误报，需手工补 claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-040",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-040 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-045",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-045 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-048",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-048 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-049",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-049 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-050",
        "task-card-stale-residual-unavailable",
        "DOC-060 历史债：TD-050 任务卡未按 DOC-060 模板补 target_files / claim_pattern",
    ),
    # DOC-059 历史债：14 个老 task 状态写 `🟢 完成` 但任务卡里既没写
    # `| 交付 PR |` 也没写 `| Merge Commit |` 字段，且 git log --grep <ID>
    # 命中 0 行（pre-2026 老 commit message 不带 ID 关键字）。DOC-059 收口
    # 时统一加白名单，避免门禁退回历史债；后续由独立 PR 决定是否补字段。
    # 白名单匹配规则：path = "docs/03-engineering-governance/technical-debt.md"
    # + message 以 "TD-XXX:" 开头 → 视为 known。
    (
        "docs/03-engineering-governance/technical-debt.md#TD-001",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-001 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-002",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-002 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-003",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-003 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-004",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-004 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-005",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-005 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-006",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-006 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-007",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-007 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-008",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-008 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-009",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-009 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-010",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-010 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#TD-011",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：TD-011 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-051",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：DOC-051 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-045",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：DOC-045 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-042",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：DOC-042 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-055",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：DOC-055 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
    (
        "docs/03-engineering-governance/technical-debt.md#DOC-056",
        "task-pr-consistency-fallback",
        "DOC-059 历史债：DOC-056 任务卡未写 PR 字段，git log 兜底 0 命中",
    ),
)

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


@dataclass(frozen=True)
class Issue:
    path: Path
    line: int
    code: str
    message: str
    suggestion: str


@dataclass(frozen=True)
class DebtDetail:
    line: int
    status: str | None
    body: list[tuple[int, str]]


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_known(issue: Issue, root: Path) -> bool:
    """判定 issue 是否在 KNOWN_ISSUES 白名单内。

    匹配规则：
    - `known_path` 是绝对或相对路径；若 issue.path 与之相等，或以
      `known_path + '#' + task_id`（如 `docs/.../technical-debt.md#TD-035`）
      形式结尾，则视作 known。
    - 这样 `_common` 仍保持单文件级粒度，但 task_card_claims 等新 check
      可以按 `task_id` 维度精确白名单（每个 task_id 独立 allowlist）。
    """
    issue_path = rel(issue.path, root)
    for known_path, known_code, _reason in KNOWN_ISSUES:
        if issue.code != known_code:
            continue
        if issue_path == known_path:
            return True
        # task_id 级白名单：`known_path = "docs/.../technical-debt.md#TD-035"`
        # 匹配所有 task_card_claims 报该 task_id 的 issue（path 字段是文件级，
        # task_id 在 message 字段里）。
        if "#" in known_path and issue_path == known_path.split("#", 1)[0]:
            # 提取 message 里的 task_id（前缀匹配，如 "TD-035: ..."）
            tail = known_path.split("#", 1)[1]
            if issue.message.startswith(f"{tail}:"):
                return True
    return False


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def section(lines: list[str], title: str) -> tuple[int, list[tuple[int, str]]]:
    start = -1
    for index, line in enumerate(lines, start=1):
        if line.strip() == f"## {title}":
            start = index
            break
    if start == -1:
        return -1, []

    body: list[tuple[int, str]] = []
    for index, line in enumerate(lines[start:], start=start + 1):
        if line.startswith("## "):
            break
        body.append((index, line))
    return start, body


def table_rows(body: list[tuple[int, str]]) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for line_no, line in body:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(" ", "")) == set():
            continue
        if "任务 | 状态" in stripped or "日期 | 任务" in stripped:
            continue
        if "暂无" in stripped:
            continue
        rows.append((line_no, stripped))
    return rows


def split_table_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def iter_doc_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in DOC_GLOBS:
        files.update(root.glob(pattern))
    return sorted(path for path in files if path.is_file())


def normalize_link_target(raw: str) -> str:
    target = raw.strip()
    if " " in target and not target.startswith("<"):
        target = target.split(" ", 1)[0]
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return target.split("#", 1)[0]


def should_skip_link(target: str) -> bool:
    return (
        not target
        or target.startswith("#")
        or target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("mailto:")
    )


# DOC-059: 兜底扫『任务卡 🟢 完成但未写 PR 编号 / Merge Commit 字段』，
# 用 `git log --grep <ID>` 检查 git history 是否含任务 ID 关键字。
# 任务卡 L2071 原计划走 `gh pr list --state merged --search <ID>` 路径，
# DOC-060（PR #206）+ DOC-063（PR #209）已将该路径演化为 git plumbing fast
# path；DOC-059 收口时调整为 git log 兜底（DOC-060 已用
# `check_merge_commit_in_git_history` 覆盖『任务卡写明 PR 编号 + mergeCommit』
# 维度；本函数专扫『任务卡 🟢 完成但任务卡里既没写 PR 编号、也没写 Merge
# Commit 字段』的兜底维度）。
DOC_059_TASK_ID_RE = re.compile(r"\b(?:TD|DOC|REQ)-\d{3}(?:-\d+)?\b")
DOC_059_DONE_STATUS_RE = re.compile(r"状态[:：]\s*🟢\s*完成")
DOC_059_GIT_LOG_TIMEOUT_S = 5


def _git_log_grep(
    task_id: str, repo_root: Path | None = None
) -> tuple[str, int | str]:
    """DOC-059: 对单个任务 ID 跑 `git log --oneline --all --grep <task_id>`
    检查 git history 是否含任务 ID 关键字（commit message / body）。

    返回 `(status, detail)`：
    - `status = "OK"` 时 `detail` 是命中行数（int，0 也算 OK 但调用方视为可疑）；
    - `status = "UNAVAILABLE"` 时 `detail` 是 `未运行: <原因>` 文本（git 不在
      PATH / 不是 git 仓库 / 超时等），按 `quality-gates.md#验证表述规范` 的
      `未运行` 分支处理。

    沙箱回退：本函数只走 `subprocess.run` 一条路径（与
    `check_merge_commit_in_git_history` 同款），无 Python fallback——git log
    的"匹配 commit message"语义在 Python 里无等价实现。

    性能：单次 git log --grep 在本地仓库 < 1s（沙箱实测）；CI 上（Linux）更快。
    """
    try:
        proc = subprocess.run(
            [
                "git",
                "log",
                "--oneline",
                "--all",
                f"--grep={task_id}",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=DOC_059_GIT_LOG_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return ("UNAVAILABLE", "未运行: git CLI 不可用 (FileNotFoundError)")
    except subprocess.TimeoutExpired:
        return (
            "UNAVAILABLE",
            f"未运行: git log 超时 ({DOC_059_GIT_LOG_TIMEOUT_S}s)",
        )
    if proc.returncode not in {0, 128}:
        stderr = (proc.stderr or "").strip().splitlines()
        hint = stderr[-1] if stderr else f"exit={proc.returncode}"
        return ("UNAVAILABLE", f"未运行: git log 失败 ({hint})")
    # exit=128 通常是 not a git repository；按"未运行"语义放过。
    if proc.returncode == 128:
        return (
            "UNAVAILABLE",
            "未运行: 当前目录不是 git 仓库（git log 退出 128）",
        )
    # 命中行数 = stdout 非空行数。
    hits = sum(1 for line in (proc.stdout or "").splitlines() if line.strip())
    return ("OK", hits)


def _git_log_text(repo_root: Path | None = None) -> tuple[str, str]:
    """Return `(status, detail)` for one full git-log read.

    `status="OK"` returns the combined commit subject/body text.  The caller can
    match every task id in memory instead of spawning `git log --grep` once per
    completed task card.
    """
    try:
        proc = subprocess.run(
            ["git", "log", "--all", "--format=%s%n%b"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=DOC_059_GIT_LOG_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return ("UNAVAILABLE", "未运行: git CLI 不可用 (FileNotFoundError)")
    except subprocess.TimeoutExpired:
        return (
            "UNAVAILABLE",
            f"未运行: git log 超时 ({DOC_059_GIT_LOG_TIMEOUT_S}s)",
        )
    if proc.returncode == 128:
        return (
            "UNAVAILABLE",
            "未运行: 当前目录不是 git 仓库（git log 退出 128）",
        )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        hint = stderr[-1] if stderr else f"exit={proc.returncode}"
        return ("UNAVAILABLE", f"未运行: git log 失败 ({hint})")
    return ("OK", proc.stdout or "")


def check_task_completion_pr_consistency_fallback(
    technical_debt_path: Path,
    work_log_path: Path,
    current_work_path: Path,
    *,
    repo_root: Path,
) -> list[Issue]:
    """DOC-059: git log 兜底路径。

    任务卡 L2071 原计划走 `gh pr list --state merged --search <ID>`（49+ 次
    串行 gh，DOC-063 已重构成 git plumbing fast path）。DOC-059 收口时调整
    实现为 git log 兜底：DOC-060 已用 `check_merge_commit_in_git_history`
    覆盖『任务卡写明 PR 编号 + mergeCommit』维度；本函数专扫『任务卡 🟢 完成
    但任务卡里既没写 PR 编号、也没写 Merge Commit 字段』的兜底维度。

    算法：
    1. 扫 3 份文档的 `### XXX: ...` 头，记录 task_id + 起始行（task-modes.md
       `### TD-NNN` 形式）。
    2. 向后扫到 `状态：🟢 完成` 行（窗口 1-6 行，与 DOC-060
       `_parse_done_task_cards` 同款）。
    3. 一次读取 git log，然后在内存里按 task_id 匹配。
    4. 0 命中时报 `task-pr-consistency-fallback` issue。
    5. 沙箱降级：UNAVAILABLE 按 `quality-gates.md#验证表述规范` 的 `未运行`
       分支放过，不视为硬失败。
    """
    issues: list[Issue] = []
    DOC_059_HEADER_RE = re.compile(r"^###\s+((?:TD|DOC|REQ)-\d{3}(?:-\d+)?)\s*[:：]")
    completed_cards: list[tuple[Path, int, str]] = []

    for path in (technical_debt_path, work_log_path, current_work_path):
        if not path.exists():
            continue
        lines = read_lines(path)
        n = len(lines)
        i = 0
        while i < n:
            header_match = DOC_059_HEADER_RE.match(lines[i])
            if not header_match:
                i += 1
                continue
            task_id = header_match.group(1)
            # 找后续 1-6 行窗口内的"状态：🟢 完成"行（DOC-060 同款算法）。
            status_line = -1
            for offset in range(1, 7):
                if i + offset >= n:
                    break
                if DOC_059_HEADER_RE.match(lines[i + offset]):
                    break
                if "### " in lines[i + offset] and "### " != lines[i + offset][:4]:
                    break
                if DOC_059_DONE_STATUS_RE.search(lines[i + offset]):
                    status_line = i + offset + 1
                    break
            if status_line == -1:
                i += 1
                continue

            # DOC-059 is only the fallback for cards without explicit PR /
            # merge fields. Cards with those fields are handled by DOC-060's
            # faster `check_merge_commit_in_git_history` path.
            card_preview = "\n".join(lines[i : min(n, i + 13)])
            has_pr_or_merge_field = re.search(
                r"^\|\s*(?:交付 PR|Merge Commit)\s*\|",
                card_preview,
                flags=re.MULTILINE,
            )
            if has_pr_or_merge_field:
                i += 1
                continue

            completed_cards.append((path, status_line, task_id))
            i += 1

    if not completed_cards:
        return issues

    git_status, git_detail = _git_log_text(repo_root=repo_root)
    git_log_text = git_detail if git_status == "OK" else ""

    for path, status_line, task_id in completed_cards:
        if git_status == "UNAVAILABLE":
            issues.append(
                Issue(
                    path,
                    status_line,
                    "task-pr-consistency-fallback-unavailable",
                    f"{task_id}: 任务卡片声明完成但 git log 兜底未运行，{git_detail}（PR 编号 / Merge Commit 字段也未提供，无法走 DOC-060 fast path）",
                    "在任务卡『交付 PR』段下补 `| 交付 PR |` + `| Merge Commit |` 字段让 DOC-060 接管；或在 KNOWN_ISSUES 跳过本任务。",
                )
            )
        elif task_id not in git_log_text:
            issues.append(
                Issue(
                    path,
                    status_line,
                    "task-pr-consistency-fallback",
                    f"{task_id}: 任务卡片声明完成但 git history 无该 ID 关键字命中（0 commit，PR 编号 / Merge Commit 字段也未提供）",
                    "复核任务是否真的已合并 main；在任务卡『交付 PR』段下补 `| 交付 PR |` + `| Merge Commit |` 字段；或在 KNOWN_ISSUES 跳过本任务。",
                )
            )
    return issues


# DOC-060: 任务卡 vs 代码 / 声明语义校验的通用工具。
# 与 DOC-059 (`check_task_completion_pr_consistency_fallback`) 互补：
# - DOC-060 扫"任务卡写明 PR 编号 / mergeCommit" + 校验 git rev-parse；
# - DOC-059 兜底扫"任务卡完成但未写 PR 字段"。
# 不强依赖 `gh` / `rg`：调用方需要时再决定是否触发 `subprocess`。
TASK_CARD_PR_REF_RE = re.compile(
    r"\[#(\d+)\]\(https://github\.com/[^)]+/pull/(\d+)\)|PR\s*#(\d+)"
)
# DOC-060 任务卡里通常会写 `| Merge Commit | `<sha>` |` 字段；本正则从
# 任务卡 body 里抽出 merge commit hash（40-char hex）。
TASK_CARD_MERGE_COMMIT_RE = re.compile(
    r"\|\s*Merge Commit\s*\|\s*`([0-9a-f]{6,40})`"
)
# DOC-063 兼容：很多历史任务卡 `事实源` 字段写 `merge commit `<sha>``（短 hash）
# 而非独立 `Merge Commit` 行；本正则抓事实源字段里嵌的短 hash。
TASK_CARD_MERGE_COMMIT_INLINE_RE = re.compile(
    r"merge commit\s+`?([0-9a-f]{6,40})`?"
)
GH_PR_VIEW_TIMEOUT_S = 10
# DOC-063: 默认校验 PR 真实状态用 git plumbing（< 5ms/次，零网络）。
# `--verify-pr-state` 显式 CLI 开关切到 `check_gh_pr_state_legacy`（慢速但
# 校验 GitHub 端状态），opt-in。
PR_STATE_VERIFY_VIA_GH = False  # 默认 False；由 CLI 开关覆盖


def is_pr_state_via_gh_enabled() -> bool:
    """DOC-063: CLI 开关 `--verify-pr-state` 控制 `check_task_card_stale_completion`
    走 `check_gh_pr_state_legacy`（慢速但查 GitHub 端），默认 False 走
    `check_merge_commit_in_git_history`（快速，零网络）。
    """
    import os

    return os.environ.get("METAEDU_CHECK_VERIFY_PR_STATE") == "1"


def _merge_commit_unavailable_detail(pr_number: int | None, repo_root: Path | None) -> str:
    """DOC-063: 任务卡缺 Merge Commit 字段时，给出明确"为什么用 git 路径需要
    mergeCommit"的说明，避免外部调用方困惑。"""
    return "DOC-063 fast path 要求任务卡写 Merge Commit 字段（`git rev-parse` 校验）"


def check_merge_commit_in_git_history(
    merge_commit: str, repo_root: Path | None = None
) -> tuple[str, str]:
    """DOC-063: 用 `git rev-parse --verify <commit>` 校验 merge commit 是否
    真实存在于 git 历史中（squash merge 后会作为独立 commit 进入 main，
    本地 git 即可查，无网络依赖）。

    返回 `(status, detail)`：
    - `status = "MERGED"` 时 merge commit 存在，`detail` 是空字符串；
    - `status = "UNAVAILABLE"` 时 `detail` 是 `未运行: <原因>` 文本（git 不在
      PATH / 不是 git 仓库 / merge commit 40 字符不合法等），按
      `quality-gates.md#验证表述规范` 的 `未运行` 分支处理。
    - `status = "NOT_MERGED"` 时 merge commit 在 git 历史里但 hash 与 `git
      log` 检索不符（理论上 squash merge 后 MERGED 状态不可逆，这种情况
      极少；保留用于未来 rebase / force-push 场景）。
    """
    sha = merge_commit.strip()
    if not re.match(r"^[0-9a-f]{6,40}$", sha):
        return ("UNAVAILABLE", f"未运行: merge commit 哈希 {sha!r} 不合法")
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", f"{sha}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        return ("UNAVAILABLE", "未运行: git CLI 不可用 (FileNotFoundError)")
    except subprocess.TimeoutExpired:
        return ("UNAVAILABLE", "未运行: git rev-parse 超时 (5s)")
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        hint = stderr[-1] if stderr else f"exit={proc.returncode}"
        return ("UNAVAILABLE", f"未运行: git rev-parse 失败 ({hint})")
    return ("MERGED", "")


def _is_valid_oid(merge_commit: str) -> bool:
    return bool(re.match(r"^[0-9a-f]{6,40}$", merge_commit.strip()))


def check_gh_pr_state_legacy(
    pr_number: int, repo_root: Path | None = None
) -> tuple[str, str]:
    """DOC-063 保留的 legacy 路径：对单个 PR 调 `gh pr view <N> --json state` 校验。
    默认不调用；opt-in by `--verify-pr-state` CLI flag（环境变量
    `METAEDU_CHECK_VERIFY_PR_STATE=1`）。
    """
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(pr_number),
                "--json",
                "state",
                "-q",
                ".state",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=GH_PR_VIEW_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return ("UNAVAILABLE", "未运行: gh CLI 不可用 (FileNotFoundError)")
    except subprocess.TimeoutExpired:
        return (
            "UNAVAILABLE",
            f"未运行: gh pr view 超时 ({GH_PR_VIEW_TIMEOUT_S}s)",
        )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        hint = stderr[-1] if stderr else f"exit={proc.returncode}"
        return ("UNAVAILABLE", f"未运行: gh pr view 失败 ({hint})")
    state = (proc.stdout or "").strip()
    if state not in {"MERGED", "OPEN", "CLOSED"}:
        return ("UNAVAILABLE", f"未运行: gh pr view 返回未知 state={state!r}")
    return (state, "")


# DOC-063 向后兼容别名：保留 `check_gh_pr_state` 名字给历史调用方，行为
# 默认改为 `check_merge_commit_in_git_history`（要 PR 号 → 任务卡 mergeCommit
# 自查）。legacy gh 路径在 `check_gh_pr_state_legacy` 单独保留。
def check_gh_pr_state(
    pr_number: int, repo_root: Path | None = None
) -> tuple[str, str]:
    """DOC-063: 默认 `check_merge_commit_in_git_history` 路径（fast）。

    保留 `pr_number` 形参仅为向后兼容；实际查的是任务卡对应 PR 的
    mergeCommit 字段（由 `task_card_claims` 提取）。如启用
    `METAEDU_CHECK_VERIFY_PR_STATE=1`，则走 `check_gh_pr_state_legacy`
    （慢速但查 GitHub 端真实状态）。
    """
    if is_pr_state_via_gh_enabled():
        return check_gh_pr_state_legacy(pr_number, repo_root=repo_root)
    # fast path：pr_number 形参不直接使用（mergeCommit 在调用方传进来）。
    # 保留 `pr_number` 形参仅为不破坏现有测试与外部调用方。
    return (
        "UNAVAILABLE",
        f"未运行: pr_number={pr_number} 的 merge_commit 需在调用方传入，"
        f"本函数 fast path 不查 gh",
    )


def check_ripgrep_count(
    pattern: str, target_files: list[Path], repo_root: Path | None = None
) -> tuple[str, int | None]:
    """对 pattern + target_files 跑 `rg -c <pattern> <files...>` 计数。

    返回 `(status, count)`：
    - `status = "OK"` 时 `count` 是命中行数（0 也算 OK）；
    - `status = "UNAVAILABLE"` 时 `count = None`（`rg` 不可用 / 超时），
      调 `quality-gates.md#验证表述规范` 的 `未运行` 分支处理。
    - `target_files` 为空时直接返回 `("UNAVAILABLE", None)` 并写明
      `未运行: target_files 为空`，避免 `rg` 收到 0 个 glob 时行为不确定。

    沙箱回退：当 `rg` 二进制不可用（`shutil.which` 返回 None，或
    `subprocess.run` 抛 `FileNotFoundError`）时，自动用纯 Python 字符串
    匹配回退（按行扫 `target_files` 内容，统计"含 pattern 子串"的行数），
    以便本机沙箱 / 容器环境仍能跑出真实结果。CI 上仍优先用 `rg`（快）。
    """
    if not target_files:
        return ("UNAVAILABLE", "未运行: target_files 为空")
    # 先尝试 rg
    use_python_fallback = False
    rg_binary = None
    import shutil

    rg_binary = shutil.which("rg")
    if rg_binary is None:
        use_python_fallback = True
    if not use_python_fallback:
        try:
            proc = subprocess.run(
                [rg_binary, "-c", "--", pattern, *[str(p) for p in target_files]],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=GH_PR_VIEW_TIMEOUT_S,
                check=False,
            )
        except (FileNotFoundError, OSError):
            use_python_fallback = True
        except subprocess.TimeoutExpired:
            return ("UNAVAILABLE", f"rg 超时 ({GH_PR_VIEW_TIMEOUT_S}s)")
    if use_python_fallback:
        return _python_pattern_count(pattern, target_files, repo_root=repo_root)
    # rg -c 的退出码：0=有命中；1=0 命中；2=错误。
    if proc.returncode not in {0, 1}:
        stderr = (proc.stderr or "").strip().splitlines()
        hint = stderr[-1] if stderr else f"exit={proc.returncode}"
        return ("UNAVAILABLE", f"rg 失败 ({hint})")
    # rg -c 输出格式：`<file>:<count>`（多文件）或直接 `<count>`（单文件）。
    total = 0
    for line in (proc.stdout or "").splitlines():
        if not line.strip():
            continue
        _, _, tail = line.rpartition(":")
        try:
            total += int(tail.strip())
        except ValueError:
            try:
                total += int(line.strip())
            except ValueError:
                return (
                    "UNAVAILABLE",
                    f"rg 输出解析失败: {line!r}",
                )
    return ("OK", total)


def _python_pattern_count(
    pattern: str, target_files: list[Path], repo_root: Path | None = None
) -> tuple[str, int | None]:
    """DOC-060 沙箱兜底：纯 Python 字符串匹配替代 `rg -c`。

    行为对齐 `rg -c`（按文件按行计数，pattern 作 substring 匹配；与
    `rg --fixed-strings` 等价），便于在 `rg` 不可用的环境（沙箱、容器）
    仍能跑出真实命中数。"""
    total = 0
    for path in target_files:
        full_path = (repo_root / path) if repo_root else path
        if not full_path.exists() or not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ("UNAVAILABLE", f"python fallback 读 {path} 失败")
        for line in text.splitlines():
            if pattern in line:
                total += 1
    return ("OK", total)


def check_task_card_claim_vs_code(
    task_id: str,
    claim_kind: str,
    declared_value: str,
    target_files: list[Path] | None = None,
    pr_number: int | None = None,
    claim_pattern: str | None = None,
    merge_commit: str | None = None,
    *,
    repo_root: Path,
) -> list[Issue]:
    """DOC-060 通用工具：校验任务卡的"声明值"是否与代码 / PR 实际一致。

    `claim_kind` 决定走哪条子校验：
    - `"pr_state"`：DOC-063 改为要求 `merge_commit` 必填；用 git plumbing
      (`git rev-parse --verify <commit>^{commit}`) 校验 merge commit 真实
      存在。`pr_number` 形参仅保留向后兼容（旧测试用），不再作为 fast 路径
      的输入。如启用 `METAEDU_CHECK_VERIFY_PR_STATE=1`，opt-in 走 gh 路径
      `check_gh_pr_state_legacy`。
    - `"residual_count"`：要求 `claim_pattern` 必填 + `target_files` 非空；
      `rg -c` 命中数与 `declared_value`（数字字符串）严格相等才通过。
      `target_files` 中如果某个相对路径在 repo_root 不存在，按
      `quality-gates.md#验证表述规范` 报 `未运行` 而不是 `0 命中` 误报。

    返回 `Issue` 列表；空列表表示声明值与实测一致。调用方按
    `Issue.code` 决定是否归到 `task-card-stale-completion` /
    `task-card-stale-residual` 通道，或归到 `UNAVAILABLE` 通道。
    """
    issues: list[Issue] = []
    if claim_kind == "pr_state":
        if merge_commit is None:
            # DOC-063: pr_state fast path 要求任务卡写 mergeCommit。
            # 任务卡没写 mergeCommit 字段时按"未运行"语义放过，让人类补字段
            # 后再跑（不强行报 stale-completion 误报）。
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-completion-unavailable",
                    f"{task_id}: 任务卡 PR #{pr_number} 缺 Merge Commit 字段，{_merge_commit_unavailable_detail(pr_number, repo_root)}",
                    "在任务卡『交付 PR』段下补 `| Merge Commit | `<sha>` |` 字段；或 opt-in 启用 gh 路径（`METAEDU_CHECK_VERIFY_PR_STATE=1`）。",
                )
            )
            return issues
        if is_pr_state_via_gh_enabled() and pr_number is not None:
            state, detail = check_gh_pr_state_legacy(pr_number, repo_root=repo_root)
        else:
            state, detail = check_merge_commit_in_git_history(
                merge_commit, repo_root=repo_root
            )
        if state == "UNAVAILABLE":
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-completion-unavailable",
                    f"{task_id}: 任务卡声明 PR #{pr_number}（merge_commit={merge_commit[:10]}…）状态，{detail}",
                    f"复核 PR #{pr_number} 状态后重跑；或在本 check 维护 KNOWN_ISSUES 临时跳过。",
                )
            )
        elif state != "MERGED":
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-completion",
                    f"{task_id}: 任务卡声明完成（PR #{pr_number}），但 git rev-parse 校验 merge commit={merge_commit} 状态={state!r}（期望 MERGED）",
                    f"复核 PR #{pr_number} 是否真的已合 main；若已合并但 `git` 缓存过期，重跑一次。",
                )
            )
        return issues

    if claim_kind == "residual_count":
        if not claim_pattern or target_files is None:
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-residual",
                    f"{task_id}: claim_kind=residual_count 但 claim_pattern / target_files 缺失",
                    "在任务卡『事实源』或『证据』段补 `target_files` 与 `claim_pattern`。",
                )
            )
            return issues
        try:
            declared_count = int(declared_value.strip())
        except ValueError:
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-residual",
                    f"{task_id}: 残留量声明值 {declared_value!r} 不是数字",
                    "在任务卡里写明精确数字（如『23 处』），避免使用『约』『若干』。",
                )
            )
            return issues
        # 过滤掉 repo_root 中不存在的 target_files，避免 `rg` 误报 0 命中。
        existing: list[Path] = []
        missing: list[Path] = []
        for p in target_files:
            (existing if (repo_root / p).exists() else missing).append(p)
        if missing and not existing:
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-residual-unavailable",
                    f"{task_id}: 残留量声明 target_files 全部不存在: {missing}",
                    "在任务卡『事实源』段补 `target_files` 实际路径，或在 KNOWN_ISSUES 跳过本任务。",
                )
            )
            return issues
        status, count_or_err = check_ripgrep_count(
            claim_pattern, existing, repo_root=repo_root
        )
        if status != "OK" or count_or_err is None:
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-residual-unavailable",
                    f"{task_id}: 残留量实测 {count_or_err}，{status}",
                    "复核 rg 是否可执行；如确为网络/环境限制，在 KNOWN_ISSUES 跳过本任务。",
                )
            )
            return issues
        if missing:
            # 部分 target_files 缺失：按未运行处理，不强行下结论。
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-residual-unavailable",
                    f"{task_id}: 部分 target_files 缺失，{missing}，仅对存在的 {existing} 跑 rg 命中数={count_or_err}",
                    "补齐缺失的 target_files 后重跑。",
                )
            )
            return issues
        if count_or_err != declared_count:
            issues.append(
                Issue(
                    Path("<DOC-060>"),
                    0,
                    "task-card-stale-residual",
                    f"{task_id}: 残留量声明 {declared_count} 处，但 `rg` 实测命中 {count_or_err} 处（pattern={claim_pattern!r}）",
                    f"复核 `rg -c {claim_pattern!r} {[str(p) for p in existing]}`，把任务卡的数字修正为实测值。",
                )
            )
        return issues

    issues.append(
        Issue(
            Path("<DOC-060>"),
            0,
            "task-card-stale-unknown-claim-kind",
            f"{task_id}: 未知 claim_kind={claim_kind!r}",
            "claim_kind 仅接受 'pr_state' 或 'residual_count'。",
        )
    )
    return issues
