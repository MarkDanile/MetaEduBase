"""TD-073: persistent cache for keypoint embeddings.

Lives in `docs/.cache/rag_validation_keypoint_embeddings/<key>.json` (under
repo root by default, overridable via `--cache-dir`). Eliminates redundant
HTTP calls for fixture-static keypoint (term + synonyms) text across
validation runs.

Cache key: `sha256(fixture_paths + mtimes + "keypoint_v1")[:16]` — see
`compute_cache_key` for the algorithm.

File schema (JSON):
    {
      "cache_key": "abc123def456",
      "schema_version": "keypoint_v1",
      "fixture_hashes": {<path>: <mtime_ns>, ...},
      "created_at": "2026-06-30T12:00:00Z",
      "embedding_dim": 4096,
      "texts": {"装饰器": [0.1, ...], "decorator": [0.4, ...]}
    }

Failure modes (graceful degradation, not raise):
- `load()` missing file / corrupt JSON / schema mismatch → return None
- `save()` target dir missing → mkdir -p
- Caller is responsible for save-failure warning + non-blocking (spec §5.5).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Question


# Schema version: bump on cache format change to invalidate all existing
# caches. Test `test_changes_when_schema_version_bumped` locks this.
_SCHEMA_VERSION = "keypoint_v1"


def compute_cache_key(fixture_paths: Iterable[Path]) -> str:
    """Stable cache key derived from fixture paths + mtimes + schema version.

    Bumping the schema version (or any fixture mtime, or adding/removing a
    fixture) changes the key, invalidating all existing caches.
    """
    parts: list[str] = [_SCHEMA_VERSION]
    for p in sorted(fixture_paths):
        if not p.exists():
            continue
        parts.append(str(p.resolve()))
        parts.append(str(p.stat().st_mtime_ns))
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def collect_unique_texts(questions: Iterable["Question"]) -> list[str]:
    """Collect unique (term + synonyms) texts across all questions.

    Dedup is case-insensitive; output preserves insertion order of first
    occurrence and is normalized to **lowercase** for cache key stability
    (model behavior typically expects lowercase). Empty / falsy entries
    are skipped.
    """
    seen: set[str] = set()
    out: list[str] = []
    for q in questions:
        for kp in q.expected_keypoints:
            candidates: list[str] = []
            if kp.term:
                candidates.append(kp.term)
            candidates.extend(syn for syn in (kp.synonyms or []) if syn)
            for t in candidates:
                key = t.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append(key)
    return out


def load(cache_key: str, source_dir: Path) -> dict[str, list[float]] | None:
    """Load cached embeddings for `cache_key` from `source_dir`.

    Returns None (graceful miss) when:
    - Cache file does not exist
    - Cache file is corrupt (JSON parse error)
    - Cache file's schema_version doesn't match the current `_SCHEMA_VERSION`
      (forces a fresh build)

    On any other structural issue (missing `texts` key, non-dict), also
    returns None — caller treats as miss and rebuilds.
    """
    if not source_dir.exists():
        return None
    cache_file = source_dir / f"{cache_key}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != _SCHEMA_VERSION:
        return None
    texts = data.get("texts")
    if not isinstance(texts, dict):
        return None
    # Defensive: ensure each value is a list[float].
    out: dict[str, list[float]] = {}
    for t, emb in texts.items():
        if isinstance(emb, list):
            out[t] = [float(x) for x in emb]
    return out


def save(
    texts_to_embeddings: dict[str, list[float]],
    cache_key: str,
    target_dir: Path,
) -> None:
    """Persist `texts_to_embeddings` to `target_dir/<cache_key>.json`.

    Creates `target_dir` (with parents) if it does not exist. Overwrites
    existing file. Embedding dim is inferred from the first non-empty list.

    Raises on I/O / JSON errors — caller is responsible for catching and
    degrading gracefully (log warning, continue main flow).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    cache_file = target_dir / f"{cache_key}.json"

    embedding_dim = 0
    for emb in texts_to_embeddings.values():
        if emb:
            embedding_dim = len(emb)
            break

    payload = {
        "cache_key": cache_key,
        "schema_version": _SCHEMA_VERSION,
        "fixture_hashes": {},  # populated by caller if desired
        "created_at": _now_iso(),
        "embedding_dim": embedding_dim,
        "texts": texts_to_embeddings,
    }
    cache_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _now_iso() -> str:
    """ISO 8601 timestamp in UTC. Local import to keep module import-cost low."""
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()