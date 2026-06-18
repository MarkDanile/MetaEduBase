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

from app.contexts.knowledge.application.ner_service import RuleBasedNER
from app.contexts.knowledge.application.query_understanding import (
    QUERY_UNDERSTANDING_PROMPT,
    HybridQueryUnderstandingResult,
    QueryUnderstandingResult,
)
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
        llm_provider: Callable[[str, str], str] | None = None,
    ) -> None:
        self._rule_ner = RuleBasedNER()
        # LLM provider: (system_prompt, user_content) -> str response (sync or async)
        # When None, the service calls ai_router._call_llm lazily at runtime.
        self._llm_provider = llm_provider

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
        """Call LLM for Query Understanding on a rule-missed query."""
        if self._llm_provider is None:
            # Lazy import to avoid circular dependency at module load time
            from app.contexts.knowledge.interfaces.api.ai_router import (
                _call_llm as _sync_llm,
            )

            async def _async_llm(sys: str, user: str) -> str:
                return await _sync_llm(sys, user)  # pragma: no cover — async path

            llm_response = await _async_llm(
                QUERY_UNDERSTANDING_PROMPT,
                f"用户查询：{query}",
            )
        else:
            try:
                llm_response = self._llm_provider(
                    QUERY_UNDERSTANDING_PROMPT,
                    f"用户查询：{query}",
                )
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
