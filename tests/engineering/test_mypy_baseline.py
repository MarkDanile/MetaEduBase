from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "packages/server-python/scripts/check_mypy_baseline.py"
SPEC = importlib.util.spec_from_file_location("check_mypy_baseline", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_parse_errors_uses_path_and_error_code_without_line_number() -> None:
    output = "\n".join(
        [
            "app/service.py:10: error: First issue  [arg-type]",
            "app/service.py:99:5: error: Moved issue  [arg-type]",
            "app/service.py:20: note: Supporting detail",
        ]
    )

    counts, fatal_lines = MODULE.parse_errors(output)

    assert counts == Counter({"app/service.py::arg-type": 2})
    assert fatal_lines == []


def test_parse_errors_rejects_startup_or_unstructured_errors() -> None:
    counts, fatal_lines = MODULE.parse_errors(
        'app/service.py: error: Source file found twice under different module names'
    )

    assert counts == Counter()
    assert fatal_lines == [
        'app/service.py: error: Source file found twice under different module names'
    ]


def test_find_regressions_rejects_new_and_increased_errors() -> None:
    current = Counter(
        {
            "app/a.py::arg-type": 3,
            "app/b.py::union-attr": 1,
        }
    )

    regressions = MODULE.find_regressions(
        current,
        {"app/a.py::arg-type": 2},
    )

    assert regressions == {
        "app/a.py::arg-type": (2, 3),
        "app/b.py::union-attr": (0, 1),
    }


def test_find_regressions_allows_reductions() -> None:
    current = Counter({"app/a.py::arg-type": 1})

    assert MODULE.find_regressions(current, {"app/a.py::arg-type": 2}) == {}
