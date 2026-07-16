"""`check_unique_task_ids` 门禁回归锁 (DOC-077)。

锁住：canonical 任务卡（`docs/01-product-planning/05-requirements/{ID}-*.md`）
同 ID 不得映射到多个不同核心 H1 标题；这是历史 BUG-011 / BUG-013 复用的
检测场景。

测试用例：
- RED: 在临时目录建 2 份同 ID canonical 文件 + 不同 H1 → 门禁失败。
- GREEN: 2 份同 ID canonical 文件 + 同一 H1（alias 归并）→ 门禁通过。
"""
from __future__ import annotations

from pathlib import Path

from tests.engineering.test_check_engineering_docs import (
    make_minimal_docs,
    run_checker,
)


def _write_requirement(
    root: Path,
    task_id: str,
    slug: str,
    h1: str,
) -> Path:
    """Create a canonical requirement file under docs/01-product-planning/05-requirements/."""
    path = root / f"docs/01-product-planning/05-requirements/{task_id}-{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# {h1}\n\n> Status: 🟢 Done\n",
        encoding="utf-8",
    )
    return path


def test_fails_when_two_canonical_files_share_id_with_different_titles(
    tmp_path: Path,
) -> None:
    """RED: 两份同 ID canonical 文件 + 不同 H1 核心标题 → 门禁失败（unique-task-id-mismatch）。"""
    make_minimal_docs(tmp_path)
    _write_requirement(
        tmp_path,
        "BUG-099",
        "ai-chat-timeout",
        "BUG-099: AI Chat 超时误报网络错误",
    )
    _write_requirement(
        tmp_path,
        "BUG-099",
        "template-init-500",
        "BUG-099: 模板 AI 生成 500",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "BUG-099" in result.stderr
    assert "映射到多个不同核心 H1 标题" in result.stderr
    assert "AI Chat 超时误报网络错误" in result.stderr
    assert "模板 AI 生成 500" in result.stderr


def test_passes_when_two_canonical_files_share_id_with_same_title(
    tmp_path: Path,
) -> None:
    """GREEN: 两份同 ID canonical 文件 + 同一 H1 核心标题（alias 归并）→ 门禁通过。

    alias 语义允许同一 ID 多份 canonical，只要它们的核心标题一致（DOC-077
    收口后通常通过重命名 + alias 链接实现；本测试锁住该语义）。
    """
    make_minimal_docs(tmp_path)
    _write_requirement(
        tmp_path,
        "BUG-099",
        "first-slug",
        "BUG-099: 同一任务的两个交付物",
    )
    _write_requirement(
        tmp_path,
        "BUG-099",
        "second-slug",
        "BUG-099: 同一任务的两个交付物",
    )

    result = run_checker(tmp_path)

    # 应当通过 unique-task-id-mismatch 检查（无 violation）。
    assert "映射到多个不同核心 H1 标题" not in result.stderr, result.stderr