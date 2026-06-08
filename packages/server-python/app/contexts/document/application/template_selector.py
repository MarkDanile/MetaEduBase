"""Three-layer template selection extracted from extract_template Celery task.

Selection priority (kept identical to the original inline implementation):

  L1  exact doc_type match (doc_type in t.doc_types)
  L2  filename substring match (any non-empty doc_type in t.doc_types appears in filename)
  L3  AI confidence match via injected ai_chat coroutine (threshold 0.7)

The function is intentionally pure (no DB, no Celery, no logger): callers translate
``SelectionResult`` into log lines or persistence as they see fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

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
    """

    # --- L1: exact doc_type match -----------------------------------------
    if doc_type:
        for t in templates:
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
        for t in templates:
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
    if not templates:
        return SelectionResult(
            template=None, layer="none", matched_type="",
            confidence=None, reason="no templates registered",
        )

    all_doc_types = sorted({dt for t in templates for dt in (t.doc_types or []) if dt})
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

    template_obj = next(
        (t for t in templates if matched_type in (t.doc_types or [])),
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
