"""Result Explainer — Python-computed metrics + LLM-generated summary + caveats.

REQ-052 Task 5: the last stage of the data-activation pipeline. The
explainer takes the rows that survived :class:`SqlGuard` and produces
the JSON object the API returns to the caller.

Three responsibilities:

1. **Metric aggregation (Python, not LLM)** — for every metric named in
   ``query_plan.metrics``, look up its :class:`MetricDefinition` and
   aggregate the rows using the configured ``aggregation`` (sum / count
   / avg). Numbers MUST be auditable and reproducible; LLM must not be
   trusted for arithmetic.

2. **Natural-language summary (LLM)** — when there is at least one row,
   ask the project's LLM client (``app.shared.llm.chat.chat``) for a
   one-paragraph Chinese summary. When ``result_rows`` is empty the
   summary is the empty string AND the LLM is NOT called (saves tokens
   and prevents hallucinated answers).

3. **Caveats (rule-based, Python)** — surfaces that the caller MUST be
   told about:

   - empty result set (data missing or no matches),
   - ``company_name`` filter applied (exact match may miss synonyms /
     abbreviations).

Brief deviations (recorded in commit message):

- **LLM client** — the brief sketch passed an ``llm.generate(...)``
  callable to the constructor. The project's LLM client is
  :func:`app.shared.llm.chat.chat` (Task 4 already standardised on it),
  so the explainer imports ``chat`` directly and patches it the same
  way :class:`QueryPlanner` does. This keeps a single LLM abstraction
  in the codebase and lets the explainer share test fixtures with the
  planner.

- **avg aggregation** — the brief sketched only sum/count/avg with no
  error handling. We defensively guard against division by zero
  (empty ``values`` list) and against unknown aggregations (returns
  ``None`` for ``value`` so the consumer knows it wasn't computed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.shared.llm.chat import chat


def _as_number(value: Any) -> float | int | None:
    """Coerce a JSONB cell to a number for metric aggregation; else ``None``.

    Imported XLSX datasets store amount / cost columns as strings (the cell
    text is preserved verbatim), so a metric over ``未付金额(元)`` sees values
    like ``"100.0"``. ``int`` / ``float`` pass through; numeric strings are
    parsed; anything else (``None``, ``"N/A"``, free text) is dropped so a
    single dirty cell never crashes or skews the aggregate.
    """
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


@dataclass
class ExplainerResult:
    """Output of :meth:`ResultExplainer.explain`.

    Attributes:
        summary: natural-language answer from the LLM (Chinese). Empty
            string when ``result_rows`` was empty.
        metric_values: ``{metric_name: {value, label, aggregation}}``.
            ``value`` may be ``0`` (sum/count over empty rows) or
            ``None`` (unknown aggregation).
        filters_applied: verbatim ``query_plan.filters`` so the router
            can echo it back to the caller.
        caveats: free-form strings the UI must surface as a warning.
        confidence: ``"high"`` when rows is non-empty, ``"low"``
            otherwise. Drives UI display (e.g. badge colour).
    """

    summary: str
    metric_values: dict  # {metric_name: {value, label, aggregation}}
    filters_applied: dict
    caveats: list[str] = field(default_factory=list)
    confidence: str = "high"


class ResultExplainer:
    """Produce :class:`ExplainerResult` from rows + query_plan + question.

    No instance state — the LLM client is module-level (``chat``), so
    the same instance can serve concurrent requests safely. Tests patch
    ``app.contexts.structured_data.application.result_explainer.chat``
    so no real LLM is invoked.
    """

    async def explain(
        self,
        result_rows: list[dict],
        semantic_model: Any,
        query_plan: dict,
        question: str,
    ) -> ExplainerResult:
        """Compute metrics + summary + caveats and return them."""
        metric_values = self._compute_metrics(result_rows, semantic_model, query_plan)
        summary = (
            await self._generate_summary(question, result_rows, metric_values)
            if result_rows
            else ""
        )
        caveats = self._detect_caveats(result_rows, query_plan)
        return ExplainerResult(
            summary=summary,
            metric_values=metric_values,
            filters_applied=query_plan.get("filters", {}),
            caveats=caveats,
            confidence="high" if result_rows else "low",
        )

    # ------------------------------------------------------------------
    # metric aggregation (Python — never LLM)
    # ------------------------------------------------------------------

    def _compute_metrics(
        self,
        result_rows: list[dict],
        semantic_model: Any,
        query_plan: dict,
    ) -> dict:
        """Aggregate rows per metric in ``query_plan.metrics``.

        Unknown metric names are silently skipped (defence-in-depth — the
        validator should have caught them but the explainer must be
        tolerant). Unknown aggregations set ``value`` to ``None`` so
        consumers see a clear "not computed" signal.
        """
        out: dict = {}
        for metric_name in query_plan.get("metrics", []) or []:
            metric_def = semantic_model.metric_definitions.get(metric_name)
            if metric_def is None:
                continue
            col = metric_def.column
            agg = metric_def.aggregation
            if agg == "count":
                # count = non-null row presence; no numeric coercion needed.
                value = sum(1 for r in result_rows if r.get(col) is not None)
            elif agg in ("sum", "avg"):
                values = [
                    v
                    for r in result_rows
                    if (v := _as_number(r.get(col))) is not None
                ]
                if agg == "sum":
                    value: Any = sum(values)
                else:
                    value = sum(values) / len(values) if values else 0
            else:
                # Unknown aggregation — mark as not computed.
                value = None
            out[metric_name] = {
                "value": value,
                "label": metric_def.label,
                "aggregation": agg,
            }
        return out

    # ------------------------------------------------------------------
    # LLM summary
    # ------------------------------------------------------------------

    async def _generate_summary(
        self,
        question: str,
        result_rows: list[dict],
        metric_values: dict,
    ) -> str:
        """One-shot LLM call for a Chinese summary.

        The metric values are passed to the LLM so it can quote the
        numbers, but the LLM is NEVER trusted for arithmetic — the
        Python aggregation above is what the API returns under
        ``metric_values``. The summary is purely narrative.
        """
        system_prompt = (
            "你是问数结果解释助手。基于 metric 结果生成简洁的中文摘要，"
            "引用 metric label 和数值；如有异常明确指出。"
        )
        user_prompt = (
            f"问题: {question}\n"
            f"metric 结果: {metric_values}\n"
            f"返回行数: {len(result_rows)}\n"
        )
        return await chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )

    # ------------------------------------------------------------------
    # caveats (rule-based, Python)
    # ------------------------------------------------------------------

    def _detect_caveats(self, result_rows: list[dict], query_plan: dict) -> list[str]:
        """Rule-based caveats surfaced to the user.

        Two rules today:

        1. Empty result → "数据未录入或无匹配记录".
        2. ``company_name`` filter applied → "按企业全称匹配；如有简称
           不匹配，可能需补充同义词". Even though the
           ``confirmed_company_name`` path uses the ground-truth name
           from REQ-046, the upstream user may still see an empty result
           if the dataset has a different spelling; the caveat reminds
           them to broaden the search.
        """
        caveats: list[str] = []
        if not result_rows:
            caveats.append(
                "查询结果为空，可能该企业无相关记录或数据未录入"
            )
        if query_plan.get("filters", {}).get("company_name"):
            caveats.append(
                "按企业全称匹配；如有简称不匹配，可能需补充同义词"
            )
        return caveats
