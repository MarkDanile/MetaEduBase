"""DOC-060: 任务卡 vs 代码 / 声明语义校验。

按 [technical-debt.md#doc-060](../../../../docs/03-engineering-governance/technical-debt.md#doc-060)
任务卡约束：

- `check_task_card_stale_completion` 扫技术债总账中状态为 ``🟢 完成`` 的任务 ID
  + 交付记录段 PR 链接，与 ``gh pr view <PR> --json state`` 校验 state=MERGED。
  与 DOC-059 互补：DOC-059 扫"PR 不存在"，本 check 扫"PR 不在 MERGED 状态"。
- `check_task_card_stale_residual` 扫技术债总账"残留量声明"模式
  （``(?:命中|残留|约|共)?\\s*\\d+\\s*处``），定位声明所在任务卡 → 在该任务卡
  ``事实源`` 字段 / ``证据`` 段提取 ``target_files`` 与 ``claim_pattern`` → 跑
  ``rg -c <claim_pattern> <target_files>`` 实测命中数 → 命中数与声明数偏差 > 0
  则报 ``task-card-stale-residual`` issue。允许白名单
  （``_common.KNOWN_ISSUES`` 拓展）。

实际校验逻辑收敛在 ``_common.check_task_card_claim_vs_code`` 通用函数，
本模块只做"任务卡 → 声明"的解析与分发。
"""

from __future__ import annotations

import re
from pathlib import Path

from ._common import (
    Issue,
    TASK_CARD_MERGE_COMMIT_INLINE_RE,
    TASK_CARD_MERGE_COMMIT_RE,
    TASK_CARD_PR_REF_RE,
    check_task_card_claim_vs_code,
    iter_doc_files,
    read_lines,
)


TECHNICAL_DEBT_PATH_PARTS = (
    "docs/03-engineering-governance/technical-debt.md",
)
TASK_CARD_HEADER_RE = re.compile(r"^###\s+((?:TD|DOC|REQ|BUG|APP)-\d{3}(?:-\d+)?)\s*[:：]")
DONE_STATUS_RE = re.compile(r"状态[:：]\s*🟢\s*完成")
RESIDUAL_CLAIM_RE = re.compile(
    r"((?:命中|残留|约|共)?\s*)(\d+)\s*处\b"
)
TARGET_FILES_RE = re.compile(r"`([^`]*\.[a-zA-Z0-9]{1,8})`")
FACT_SOURCE_BLOCK_HEADER_RE = re.compile(
    r"^\*\*事实源\*\*\s*$|^\*\*证据\*\*\s*$"
)
CARD_END_RE = re.compile(r"^###\s+(?!$)|\Z")


def _find_pr_number_in_card(card_body: list[str]) -> int | None:
    """DOC-063: 从任务卡正文提取"任务卡自己的"PR 编号。

    严格匹配 `| 交付 PR |` 表格行（DOC-057 / DOC-058 / DOC-060 收口时统一
    字段格式），不再匹全文。理由：DOC-023 等任务卡"事实源"段引用了
    别人的 PR #46，匹全文会把别人的 PR 当成"自己的 PR"，让 check 误把
    别人的 merge commit 当成自己的事实源。

    表格行格式：`| 交付 PR | [PR #NNN](https://...pull/NNN) |`
    """
    for line in card_body:
        # 仅匹"交付 PR"段（表格列头）
        if not re.search(r"\|\s*交付 PR\s*\|", line):
            continue
        m = TASK_CARD_PR_REF_RE.search(line)
        if m:
            for group in m.groups():
                if group and group.isdigit():
                    return int(group)
    return None


def _find_merge_commit_in_card(card_body: list[str]) -> str | None:
    """DOC-063: 从任务卡正文提取 merge commit sha。

    优先级（DOC-063 兼容性）：
    1. 显式 `| Merge Commit | `<sha>` |` 字段（DOC-057 / DOC-060 收口时回填的格式）
    2. `事实源` 字段里嵌的 `merge commit `<sha>`` 短 hash（历史债，许多
       历史任务卡用这种格式写 PR 链接 + 短 hash）
    3. 交付记录段叙述里出现的 `merge commit `<sha>`` 模式

    按 task-modes.md#任务入口解析门禁 + DOC-058 翻完成硬条件约定，任务卡
    写明 PR 编号 + mergeCommit 是事实源；本函数扫 body 内 Markdown 表格行
    + 叙述行提取 sha，返回 6-40 字符 hex。"""
    # 1. 显式 `| Merge Commit |` 字段
    for line in card_body:
        m = TASK_CARD_MERGE_COMMIT_RE.search(line)
        if m:
            return m.group(1)
    # 2. 事实源 / 交付记录 / 任何位置里的 `merge commit <sha>`
    for line in card_body:
        m = TASK_CARD_MERGE_COMMIT_INLINE_RE.search(line)
        if m:
            return m.group(1)
    return None


def _parse_done_task_cards(
    technical_debt_path: Path,
) -> list[tuple[str, int, list[str]]]:
    """扫 technical-debt.md，返回所有 `状态：🟢 完成` 任务卡的
    `(task_id, card_start_line, card_body_lines)` 三元组列表。
    """
    if not technical_debt_path.exists():
        return []
    lines = read_lines(technical_debt_path)
    cards: list[tuple[str, int, list[str]]] = []
    i = 0
    n = len(lines)
    while i < n:
        header_match = TASK_CARD_HEADER_RE.match(lines[i])
        if not header_match:
            i += 1
            continue
        task_id = header_match.group(1)
        start = i
        body: list[str] = []
        # 状态行通常紧跟 `### XXX: ...` 头 1-2 行内；为保险扫 5 行窗口。
        status_match = None
        for offset in range(1, 6):
            if i + offset >= n:
                break
            if TASK_CARD_HEADER_RE.match(lines[i + offset]):
                break
            if "### " in lines[i + offset] and "### " != lines[i + offset][:4]:
                break
            if DONE_STATUS_RE.search(lines[i + offset]):
                status_match = lines[i + offset]
                break
        # 找下一个 `### ` 起头或文件末
        j = i + 1
        while j < n:
            if TASK_CARD_HEADER_RE.match(lines[j]):
                break
            body.append(lines[j])
            j += 1
        if status_match is not None:
            cards.append((task_id, start + 1, body))
        i = j
    return cards


def _extract_fact_source_block(
    card_body: list[str],
) -> list[str]:
    """从任务卡 body 中截取 `**事实源**` 段（或 fallback `**证据**` 段），
    返回该段内全部行；找不到则返回空列表。"""
    for idx, line in enumerate(card_body):
        if FACT_SOURCE_BLOCK_HEADER_RE.match(line):
            end = len(card_body)
            for k in range(idx + 1, len(card_body)):
                stripped = card_body[k].strip()
                if stripped.startswith("**") and stripped.endswith("**"):
                    end = k
                    break
                if stripped.startswith("### "):
                    end = k
                    break
            return card_body[idx + 1 : end]
    return []


def _extract_target_files(
    block_lines: list[str], repo_root: Path
) -> list[Path]:
    """从事实源段所有 `` `path/to/file.ext` `` 形式的 inline code 中
    提取相对路径，过滤掉明显不是文件路径的（如 `pytest -q`）。"""
    files: list[Path] = []
    for line in block_lines:
        for m in TARGET_FILES_RE.finditer(line):
            raw = m.group(1)
            # 启发式过滤：必须有 `.` 且不是命令（不含空格）
            if "/" not in raw and " " in raw:
                continue
            if " " in raw:
                continue
            if "." not in raw:
                continue
            files.append(Path(raw))
    # 去重
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in files:
        if p in seen:
            continue
        seen.add(p)
        unique.append(p)
    return unique


def _parse_residual_claim(
    card_body: list[str],
) -> list[tuple[int, str, int, str]]:
    """扫描任务卡正文里所有 `(命中|残留|约|共)? N 处` 形式声明，
    返回 `(line_no_in_card_body, modifier, declared_count, claim_pattern_guess)` 列表。

    `claim_pattern_guess` 用同句（含 `处` 的整行）作为 rg 关键字，方便人工
    复核（避免脚本从模糊中文里反推 pattern）。"""
    claims: list[tuple[int, str, int, str]] = []
    for idx, line in enumerate(card_body):
        m = RESIDUAL_CLAIM_RE.search(line)
        if not m:
            continue
        modifier = m.group(1) or ""
        count = int(m.group(2))
        # 取 claim 整句作为 pattern 候选（去掉 backtick 与前后空白）
        claim_pattern_guess = line.strip()
        claims.append((idx, modifier, count, claim_pattern_guess))
    return claims


def check_task_card_stale_completion(root: Path) -> list[Issue]:
    """DOC-063: 扫 technical-debt.md 中所有 `状态：🟢 完成` 任务卡，提取 PR
    编号 + Merge Commit 字段，调
    `_common.check_task_card_claim_vs_code(claim_kind='pr_state')` 校验。

    优先用 git plumbing（`git rev-parse --verify <commit>^{commit}`，< 5ms/次）
    校验任务卡写的 mergeCommit 哈希是否真实存在；opt-in `--verify-pr-state`
    走 `check_gh_pr_state_legacy` 慢速但查 GitHub 端真实状态。
    """
    issues: list[Issue] = []
    debt_path = root / TECHNICAL_DEBT_PATH_PARTS[0]
    for task_id, start_line, body in _parse_done_task_cards(debt_path):
        pr_number = _find_pr_number_in_card(body)
        if pr_number is None:
            # DOC-059 负责"PR 不存在"；本 check 跳过，等 DOC-059 报。
            continue
        merge_commit = _find_merge_commit_in_card(body)
        sub_issues = check_task_card_claim_vs_code(
            task_id=task_id,
            claim_kind="pr_state",
            declared_value="MERGED",
            pr_number=pr_number,
            merge_commit=merge_commit,
            repo_root=root,
        )
        for issue in sub_issues:
            # 把 `Path("<DOC-060>")` 占位替换为 task_card 起始行 + 1
            # (起始行是 `### XXX: ...`，紧跟的 1-2 行内是状态行)
            issues.append(
                Issue(
                    debt_path,
                    start_line,
                    issue.code,
                    issue.message,
                    issue.suggestion,
                )
            )
    return issues


def check_task_card_stale_residual(root: Path) -> list[Issue]:
    """扫 technical-debt.md 所有任务卡的"残留量声明"段，提取 target_files
    + claim_pattern，调 `_common.check_task_card_claim_vs_code(
    claim_kind='residual_count')` 校验。
    """
    issues: list[Issue] = []
    debt_path = root / TECHNICAL_DEBT_PATH_PARTS[0]
    if not debt_path.exists():
        return issues
    lines = read_lines(debt_path)
    for i, line in enumerate(lines):
        header_match = TASK_CARD_HEADER_RE.match(line)
        if not header_match:
            continue
        task_id = header_match.group(1)
        # 取该卡到下一个 `### ` 之间的 body
        j = i + 1
        body: list[str] = []
        while j < len(lines):
            if TASK_CARD_HEADER_RE.match(lines[j]):
                break
            body.append(lines[j])
            j += 1
        fact_block = _extract_fact_source_block(body)
        if not fact_block:
            fact_block = body  # 退而求其次
        target_files = _extract_target_files(fact_block, root)
        claims = _parse_residual_claim(body)
        if not claims:
            continue
        if not target_files:
            # 没提取到 target_files，事实源段确实没列；跳过而非误报。
            continue
        for _offset, modifier, declared_count, claim_pattern in claims:
            if modifier.strip() in {"约", "共"}:
                # 约 / 共是模糊量词，按"未运行"语义放过不报（任务卡明确
                # 写"约 5 处"不算假残留量，是定量描述前置的礼貌表达）。
                continue
            sub_issues = check_task_card_claim_vs_code(
                task_id=task_id,
                claim_kind="residual_count",
                declared_value=str(declared_count),
                target_files=target_files,
                claim_pattern=claim_pattern,
                repo_root=root,
            )
            for issue in sub_issues:
                issues.append(
                    Issue(
                        debt_path,
                        i + 1,
                        issue.code,
                        issue.message,
                        issue.suggestion,
                    )
                )
    return issues
