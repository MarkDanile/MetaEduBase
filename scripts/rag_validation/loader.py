"""Question sample loading + dotenv bootstrap for REQ-024 P2 real validation.

Split out of the original monolithic script (TD-032 slice 8).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .models import Keypoint, Question


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _mask_db_url(url: str) -> str:
    return "***@" + url.split("@", 1)[1] if "@" in url else url


def _parse_keypoint(kp: Any) -> Keypoint:
    """Parse a keypoint entry from JSON.

    Accepts:
    - string: ``"闭包"`` -> Keypoint(term="闭包")
    - dict: ``{"term": "闭包", "synonyms": [...], "weight": 1.0}``
    """
    if isinstance(kp, str):
        return Keypoint(term=kp)
    if isinstance(kp, dict):
        term = kp.get("term")
        if not term:
            raise ValueError(f"keypoint dict missing 'term': {kp!r}")
        synonyms = list(kp.get("synonyms", []) or [])
        weight = float(kp.get("weight", 1.0))
        return Keypoint(term=str(term), synonyms=[str(s) for s in synonyms if s], weight=weight)
    raise ValueError(f"unsupported keypoint type: {type(kp).__name__}")


def _load_questions(req016: Path, req018: Path, req026: Path, req028: Path) -> list[Question]:
    questions: list[Question] = []
    for group, path in [
        ("REQ-016", req016),
        ("REQ-018", req018),
        ("REQ-026", req026),
        ("REQ-028", req028),
    ]:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data.get("questions", []):
            expected = {
                k: v
                for k, v in item.items()
                if k not in {"id", "text", "expected_category", "expected_keypoints"}
            }
            raw_keypoints = item.get("expected_keypoints", []) or []
            keypoints: list[Keypoint] = []
            for kp in raw_keypoints:
                try:
                    keypoints.append(_parse_keypoint(kp))
                except ValueError as exc:
                    print(f"warn: skip keypoint in {group}/{item.get('id')}: {exc}", file=sys.stderr)
            questions.append(
                Question(
                    group=group,
                    question_id=item["id"],
                    text=item["text"],
                    expected=expected,
                    expected_keypoints=keypoints,
                )
            )
    return questions
