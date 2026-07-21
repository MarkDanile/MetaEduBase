"""Three-layer template selection extracted from extract_template Celery task.

Selection priority (kept identical to the original inline implementation):

  L1  exact doc_type match (doc_type in t.doc_types)
  L2  filename substring match (any non-empty doc_type in t.doc_types appears in filename)
  L3  AI confidence match via injected ai_chat coroutine (threshold 0.7)

The function is intentionally pure (no DB, no Celery, no logger): callers translate
``SelectionResult`` into log lines or persistence as they see fit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from app.contexts.template.domain.entity import Template

Layer = Literal["L1", "L2", "L3", "none"]


@dataclass
class SelectionResult:
    template: Template | None
    layer: Layer
    matched_type: str
    confidence: float | None
    reason: str


AIChat = Callable[[str], Awaitable[str]]


async def select_template(
    chunks_text: str,
    doc_type: str | None,
    filename: str,
    templates: list[Template],
    ai_chat: AIChat,
    *,
    confidence_threshold: float = 0.7,
) -> SelectionResult:
    """Return a (template, layer, ...) tuple per the priority above.

    ``ai_chat(prompt)`` is expected to return a string of the form
    ``"<doc_type>\\n<confidence 0..1>"``. Any deviation is folded into
    a ``"none"`` result with a descriptive ``reason`` — the caller logs it.

    REQ-002-4: deprecated templates (is_deprecated=True) are filtered out
    of L1/L2/L3 candidates. If all matching templates are deprecated, the
    selection falls through to ``"none"`` (or ``"L3"`` with low confidence)
    so callers don't fail when a doc_type has only deprecated coverage.
    """

    # REQ-002-4: filter out deprecated templates from selection
    active_templates = [t for t in templates if not getattr(t, "is_deprecated", False)]

    # --- L1: exact doc_type match -----------------------------------------
    if doc_type:
        for t in active_templates:
            if doc_type in (t.doc_types or []):
                return SelectionResult(
                    template=t,
                    layer="L1",
                    matched_type=doc_type,
                    confidence=None,
                    reason="exact doc_type match",
                )

    # --- L2: filename substring match -------------------------------------
    if filename:
        for t in active_templates:
            for dt in t.doc_types or []:
                if dt and dt in filename:
                    return SelectionResult(
                        template=t,
                        layer="L2",
                        matched_type=dt,
                        confidence=None,
                        reason="filename substring match",
                    )

    # --- L3: AI confidence match ------------------------------------------
    if not active_templates:
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason="no templates registered",
        )

    all_doc_types = sorted({dt for t in active_templates for dt in (t.doc_types or []) if dt})
    if not all_doc_types:
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason="no doc_types registered",
        )

    match_prompt = (
        f"文档内容摘要：{chunks_text[:500]}\n"
        f"可选文档类型：{all_doc_types}\n"
        "请判断这份文档最适合哪种文档类型，"
        '返回格式：类型名称\\n置信度分数（0.0~1.0，如"教案\\n0.85"）'
    )

    try:
        response = (await ai_chat(match_prompt)).strip()
    except Exception as e:  # noqa: BLE001 — keep parity with original
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason=f"AI call raised: {e!r}",
        )

    # AI 有时把 prompt 里的 `\n` 格式说明当成字面量回显
    # （如 "教案\n1.0"，其中 \n 是反斜杠+n 两个字符），而非真正的换行。
    # splitlines() 不会切分字面 \n，导致 matched_type 残留置信度后缀而匹配失败。
    # 先把字面 \n / \r 转义归一化为真实换行再切分。
    response = response.replace("\\n", "\n").replace("\\r", "")
    lines = [line.strip() for line in response.splitlines() if line.strip()]
    if not lines:
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason="AI returned empty response",
        )

    matched_type = lines[0]
    if len(lines) >= 2:
        try:
            confidence = float(lines[1])
        except ValueError:
            confidence = 0.0
    else:
        confidence = 0.5  # single line: default mid confidence

    # REQ-002-4: L3 only picks from active (non-deprecated) templates
    template_obj = next(
        (t for t in active_templates if matched_type in (t.doc_types or [])),
        None,
    )

    if template_obj is None:
        return SelectionResult(
            template=None, layer="none", matched_type=matched_type,
            confidence=confidence,
            reason="AI matched type not in tenant templates",
        )

    if confidence < confidence_threshold:
        return SelectionResult(
            template=None, layer="L3", matched_type=matched_type,
            confidence=confidence, reason="AI confidence below threshold",
        )

    return SelectionResult(
        template=template_obj, layer="L3", matched_type=matched_type,
        confidence=confidence, reason="AI confidence match",
    )
