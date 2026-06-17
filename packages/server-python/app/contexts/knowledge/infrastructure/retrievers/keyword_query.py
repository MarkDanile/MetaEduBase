"""Shared keyword query helpers for PostgreSQL chunk retrievers."""

from __future__ import annotations

import re

_LATIN_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_+#.\-]{1,}", re.IGNORECASE)
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

_QUESTION_STOP_PHRASES = (
    "有哪些",
    "是什么",
    "什么是",
    "为什么",
    "怎么",
    "如何",
    "哪些",
    "需要",
    "请问",
    "请",
    "一下",
    "介绍",
    "说明",
    "列出",
    "包括",
    "的",
)

_IMPORTANT_CJK_TERMS = (
    "基本数据类型",
    "数据类型",
    "能力图谱",
    "知识图谱",
    "全文检索",
    "向量检索",
    "融合排序",
    "预习规划",
    "资源推荐",
    "复习规划",
    "智能制造",
)


def tokenize_query(query: str, *, limit: int = 12) -> list[str]:
    """Extract stable keyword terms from short Chinese / mixed queries.

    The production fallback uses these terms with OR-style ILIKE matching, so
    query particles such as "有哪些" should not dominate retrieval.
    """
    normalized = query[:120].strip().lower()
    candidates: list[str] = []

    candidates.extend(_LATIN_TOKEN_RE.findall(normalized))

    cleaned = normalized
    for phrase in _QUESTION_STOP_PHRASES:
        cleaned = cleaned.replace(phrase, " ")

    for run in _CJK_RUN_RE.findall(cleaned):
        if 2 <= len(run) <= 10:
            candidates.append(run)
        for term in _IMPORTANT_CJK_TERMS:
            if term in run:
                candidates.append(term)
        if len(run) > 8:
            candidates.extend([run[:4], run[-4:]])

    deduped: list[str] = []
    seen: set[str] = set()
    for term in candidates:
        term = term.strip()
        if len(term) < 2 or term in seen:
            continue
        seen.add(term)
        deduped.append(term)
        if len(deduped) >= limit:
            break
    return deduped


def bind_keyword_params(
    keywords: list[str],
    params: dict,
    *,
    prefix: str = "kw",
) -> list[str]:
    """Bind ILIKE params and return parameter names."""
    names: list[str] = []
    for i, kw in enumerate(keywords):
        name = f"{prefix}{i}"
        params[name] = f"%{kw}%"
        names.append(name)
    return names


def ilike_conditions(param_names: list[str], *, alias: str = "c") -> list[str]:
    return [
        (
            f"({alias}.content ILIKE :{name} "
            f"OR COALESCE({alias}.section_title, '') ILIKE :{name} "
            f"OR COALESCE({alias}.section_path, '') ILIKE :{name})"
        )
        for name in param_names
    ]


def lexical_score_sql(param_names: list[str], *, alias: str = "c") -> str:
    if not param_names:
        return "0.0"
    parts: list[str] = []
    for name in param_names:
        parts.extend(
            [
                (
                    f"CASE WHEN COALESCE({alias}.section_title, '') "
                    f"ILIKE :{name} THEN 12 ELSE 0 END"
                ),
                (
                    f"CASE WHEN {alias}.content ILIKE :{name} "
                    "THEN 4 ELSE 0 END"
                ),
                (
                    f"CASE WHEN COALESCE({alias}.section_path, '') "
                    f"ILIKE :{name} THEN 2 ELSE 0 END"
                ),
            ]
        )
    return "(" + " + ".join(parts) + ")"


def toc_penalty_sql(*, alias: str = "c") -> str:
    return (
        "CASE WHEN COALESCE("
        f"{alias}.section_title, '') ILIKE '%目录%' "
        f"OR COALESCE({alias}.section_title, '') ILIKE '%简介%' "
        f"OR ({alias}.content ILIKE '%目录%' AND {alias}.content LIKE '%...%') "
        "THEN 1 ELSE 0 END"
    )


def merge_ranked_rows(
    primary_rows: list[dict],
    lexical_rows: list[dict],
    *,
    limit: int,
) -> list[dict]:
    """Merge tsvector and lexical rows and keep a stable relevance order."""
    by_id: dict[object, dict] = {}

    def add(row: dict, mode: str) -> None:
        rid = row["id"]
        incoming = dict(row)
        incoming["_search_mode"] = mode
        existing = by_id.get(rid)
        if existing is None:
            by_id[rid] = incoming
            return

        existing["keyword_rank"] = max(
            float(existing.get("keyword_rank") or 0.0),
            float(incoming.get("keyword_rank") or 0.0),
        )
        existing["lexical_score"] = max(
            float(existing.get("lexical_score") or 0.0),
            float(incoming.get("lexical_score") or 0.0),
        )
        existing["toc_penalty"] = min(
            int(existing.get("toc_penalty") or 0),
            int(incoming.get("toc_penalty") or 0),
        )
        if existing.get("_search_mode") != mode:
            existing["_search_mode"] = "hybrid"

    for row in primary_rows:
        add(row, "tsvector")
    for row in lexical_rows:
        add(row, "lexical")

    def sort_key(row: dict) -> tuple[int, float, float, int]:
        return (
            int(row.get("toc_penalty") or 0),
            -float(row.get("lexical_score") or 0.0),
            -float(row.get("keyword_rank") or 0.0),
            int(row.get("chunk_index") or 0),
        )

    return sorted(by_id.values(), key=sort_key)[:limit]
