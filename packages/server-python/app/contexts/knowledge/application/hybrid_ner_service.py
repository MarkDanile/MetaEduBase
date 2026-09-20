"""REQ-016 Slice 1 — Hybrid Query Understanding Service.

Layers LLM Query Understanding on top of RuleBasedNER:
- RuleBasedNER runs first (zero cost, always runs)
- LLM is triggered only when rules miss AND query is long enough
- Result is a HybridQueryUnderstandingResult (subclass of NERResult) satisfying
  NERPipeline protocol, with extra fields for LLM QU output and trigger reason.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.query_understanding import (
    QUERY_UNDERSTANDING_PROMPT,
    HybridQueryUnderstandingResult,
    QueryUnderstandingResult,
)
from app.runtime.application.llm_provider import LlmProvider
from app.shared.domain.ner_pipeline import NERResult

logger = logging.getLogger(__name__)

# Threshold: only call LLM when rule misses AND query is long enough.
_QUERY_LENGTH_THRESHOLD = 15


class HybridQueryUnderstandingService:
    """Hybrid NER + LLM Query Understanding.

    Satisfies NERPipeline protocol so it can replace RuleBasedNER in
    AIChatService.ner_pipeline.  The returned HybridQueryUnderstandingResult
    is a subclass of NERResult, so structural subtype checks pass.

    AIChatService.chat() uses only the NER fields (domains / levels /
    raw_entities) for retrieval.  The LLM Query Understanding result is
    available in .query_understanding for diagnostics / expanded terms.
    """

    def __init__(
        self,
        # Production wiring (TD-085 Slice A): an ``LlmProvider`` port
        # implementation. Composition root injects the same instance
        # into ``AIChatService`` and ``HybridQueryUnderstandingService``.
        llm_provider: LlmProvider | None = None,
        # Legacy test seam: pre-Slice A tests inject a raw
        # ``Callable[[str, str], str]`` directly. Production must inject
        # the port (``llm_provider``) instead. If both are supplied,
        # the port wins; if neither, this service refuses to call LLM.
        # Duck-typing: any callable passed positionally as the first
        # argument is treated as a legacy callable, not an LlmProvider.
        # This preserves pre-Slice A test compatibility without
        # requiring changes to existing test sites.
        legacy_llm_callable: Callable[[str, str], Any] | None = None,
    ) -> None:
        self._rule_ner = RuleBasedNER()
        # Duck-typed resolution: ``_llm_provider`` may be either a real
        # ``LlmProvider`` instance (production wiring via composition
        # root) or a raw ``Callable[[str, str], str]`` (pre-Slice A
        # legacy test seam). We keep both accessible via the same
        # field so existing tests that read ``service._llm_provider``
        # directly keep working unchanged.
        if llm_provider is not None:
            self._llm_provider = llm_provider
        elif legacy_llm_callable is not None:
            self._llm_provider = legacy_llm_callable
        else:
            self._llm_provider = None

    async def extract(self, query: str) -> HybridQueryUnderstandingResult:
        """Extract NER + optionally call LLM QU based on trigger strategy."""
        ner_result = await self._rule_ner.extract(query)

        # Rule hit: don't call LLM, return immediately
        if ner_result.domains or ner_result.levels:
            return HybridQueryUnderstandingResult(
                domains=ner_result.domains,
                levels=ner_result.levels,
                raw_entities=ner_result.raw_entities,
                query_understanding=QueryUnderstandingResult(
                    method="rule",
                    confidence=1.0,
                    normalized_query=query,
                    core_terms=ner_result.raw_entities,
                ),
                trigger_reason="rule_hit",
            )

        # Rule miss: check query length
        if len(query) <= _QUERY_LENGTH_THRESHOLD:
            return HybridQueryUnderstandingResult(
                domains=[],
                levels=[],
                raw_entities=[],
                query_understanding=QueryUnderstandingResult(
                    method="rule",
                    confidence=0.0,
                    normalized_query=query,
                ),
                trigger_reason="rule_miss_short_query",
            )

        # Rule miss + long query: call LLM
        return await self._call_llm_qu(query, ner_result)

    async def _call_llm_qu(
        self, query: str, ner_result: NERResult
    ) -> HybridQueryUnderstandingResult:
        """Call LLM for Query Understanding on a rule-missed query.

        TD-085 Slice A: production path uses the ``LlmProvider`` port
        injected by composition root (or a callable seam preserved
        from pre-Slice A tests). The application layer never imports
        concrete adapters or ``ai_router`` symbols — Slice A removes
        the application -> interfaces/api reverse import entirely.
        """
        if self._llm_provider is None:
            raise RuntimeError(
                "HybridQueryUnderstandingService has no LLM provider "
                "configured; composition root must inject an "
                "LlmProvider before _call_llm_qu runs."
            )

        if isinstance(self._llm_provider, LlmProvider):
            llm_response = await self._llm_provider.chat_text(
                QUERY_UNDERSTANDING_PROMPT,
                f"用户查询：{query}",
            )
            return self._parse_llm_response(query, llm_response)

        # Legacy callable seam: pre-Slice A tests pass a raw
        # ``Callable[[str, str], str]`` directly. The callable may be
        # sync or async; we await it directly so async LlmProvider
        # ports work transparently.
        try:
            result = self._llm_provider(
                QUERY_UNDERSTANDING_PROMPT,
                f"用户查询：{query}",
            )
            if hasattr(result, "__await__"):
                llm_response = await result  # type: ignore[func-returns-value]
            else:
                llm_response = result  # type: ignore[assignment]
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM QU provider raised: %s", e)
            return self._llm_fallback(query, f"llm_provider_error:{e}")
        return self._parse_llm_response(query, llm_response)

    def _parse_llm_response(
        self, query: str, llm_response: str
    ) -> HybridQueryUnderstandingResult:
        """Parse LLM JSON output into HybridQueryUnderstandingResult."""
        try:
            data = json.loads(llm_response)
            expanded_terms = data.get("expanded_terms", [])
            qu = QueryUnderstandingResult(
                method="llm",
                confidence=data.get("confidence", 0.5),
                normalized_query=data.get("normalized_query", query),
                core_terms=data.get("core_terms", []),
                expanded_terms=expanded_terms,
                entities=data.get("entities", []),
                filters=data.get("filters", {}),
                raw_llm_output=llm_response,
            )
            # REQ-016 Slice 3: feed expanded_terms back as expanded_query for retrieval
            expanded_query = " ".join(expanded_terms) if expanded_terms else ""
            return HybridQueryUnderstandingResult(
                domains=[],
                levels=[],
                raw_entities=[],
                expanded_query=expanded_query,
                query_understanding=qu,
                trigger_reason="rule_miss_and_long_query",
            )
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning("LLM QU JSON parse failed: %s", e)
            return self._llm_fallback(query, f"json_parse_error:{e}")

    def _llm_fallback(
        self, query: str, error_context: str
    ) -> HybridQueryUnderstandingResult:
        """Return fallback when LLM call or parse fails."""
        return HybridQueryUnderstandingResult(
            domains=[],
            levels=[],
            raw_entities=[],
            query_understanding=QueryUnderstandingResult(
                method="rule",
                confidence=0.0,
                normalized_query=query,
                raw_llm_output=f"fallback:{error_context}",
            ),
            trigger_reason=f"llm_failure:{error_context}",
        )
