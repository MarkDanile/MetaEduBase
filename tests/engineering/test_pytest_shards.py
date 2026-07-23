from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ci" / "select-pytest-files"


def _run(root: Path, index: int, count: int, weights: Path | None = None) -> list[str]:
    command = ["bash", str(SCRIPT), str(index), str(count), str(root)]
    if weights is not None:
        command.append(str(weights))
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.splitlines()


def test_shards_are_complete_disjoint_and_deterministic(tmp_path: Path) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()
    expected: set[str] = set()
    for index, lines in enumerate((120, 90, 60, 30, 15, 5)):
        path = test_root / f"test_{index}.py"
        path.write_text("pass\n" * lines, encoding="utf-8")
        expected.add(str(path))

    shard_zero = _run(test_root, 0, 2)
    shard_one = _run(test_root, 1, 2)

    assert set(shard_zero).isdisjoint(shard_one)
    assert set(shard_zero).union(shard_one) == expected
    assert _run(test_root, 0, 2) == shard_zero


def test_collected_node_counts_override_source_line_weights(tmp_path: Path) -> None:
    test_root = tmp_path / "tests"
    test_root.mkdir()
    paths = [test_root / f"test_{index}.py" for index in range(4)]
    for path in paths:
        path.write_text("pass\n", encoding="utf-8")

    weights = tmp_path / "nodes.txt"
    weights.write_text(
        "".join(
            f"{path}::test_case_{case}\n"
            for path, count in zip(paths, (10, 9, 2, 1), strict=True)
            for case in range(count)
        ),
        encoding="utf-8",
    )

    shard_zero = _run(test_root, 0, 2, weights)
    shard_one = _run(test_root, 1, 2, weights)
    assert str(paths[0]) in shard_zero
    assert str(paths[1]) in shard_one
    assert set(shard_zero).union(shard_one) == {str(path) for path in paths}


def test_invalid_shard_is_rejected(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "2", "2", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "less than" in result.stderr
