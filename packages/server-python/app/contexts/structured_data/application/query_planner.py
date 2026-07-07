"""Query Planner: NL question → structured query_plan via LLM.

REQ-052 Task 4: takes a user's natural-language question, a registered
:class:`SemanticModel`, and (optionally) a ``confirmed_company_name`` from
REQ-046 entity confirmation, and asks the project's unified LLM client
(``app.shared.llm.chat.chat``) to produce a JSON ``query_plan``.

The ``query_plan`` shape is the brief-defined contract:

.. code-block:: json

    {
        "entity": "bill",
        "metrics": ["unpaid_amount"],
        "filters": {"company_name": {"op": "eq", "value": "..."}},
        "time_range": {"field": "billing_date", "start": "...", "end": "..."},
        "limit": 100
    }

Brief deviations (recorded in commit message):

1. **Real LLM client** — the brief defined a ``LLMClient(Protocol)`` with
   ``async generate(system, user)`` but the project already standardises on
   :func:`app.shared.llm.chat.chat` which takes a ``messages`` list and
   keyword args (``provider``, ``model``, ``temperature``, ``max_tokens``,
   ``timeout``). Rather than introduce a second abstraction, the planner
   imports ``chat`` directly. Tests patch ``app.contexts.structured_data
   .application.query_planner.chat`` so no real LLM is ever called.

2. **Brace-balanced JSON extraction** — the brief suggested a regex;
   ``re`` stops at the first inner ``}`` which truncates nested objects
   (``"filters": {"col": {...}}``). We use a brace-balance scanner that
   tracks depth AND respects string literals (so escaped quotes inside
   a string don't open / close the string state). This handles the
   actual LLM output shape correctly.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.shared.llm.chat import chat

logger = logging.getLogger(__name__)


class QueryPlanner:
    """NL → query_plan via LLM.

    The planner holds no instance state — every input is a method argument
    so the same instance can serve concurrent requests safely. Tests patch
    :data:`chat` (the module-level symbol imported at the top) to inject a
    deterministic ``AsyncMock``; the production code uses the real provider
    chain (minimax / deepseek / qwen per the env config).
    """

    # Brief-mandated defaults — the spec §5.5 says soft limit 100 / max 1000.
    # The planner emits 100; the JsonbQueryBuilder enforces the upper bound.
    DEFAULT_LIMIT: int = 100

    async def plan(
        self,
        question: str,
        semantic_model: Any,
        confirmed_company_name: str | None = None,
    ) -> dict:
        """Ask the LLM for a ``query_plan`` JSON and post-process it.

        Steps:

        1. Build system + user prompts from the semantic model schema.
        2. Call :func:`chat` with the messages list.
        3. Strip markdown fences / leading prose; ``json.loads`` the first
           ``{...}`` match.
        4. Force-inject the company_name filter from
           ``confirmed_company_name`` (REQ-052 §5.7 — entity confirmation
           is the ground truth, the LLM must not override it).
        5. Default ``limit`` to 100 when missing.
        """
        system_prompt = self._build_system_prompt(semantic_model)
        user_prompt = self._build_user_prompt(question, confirmed_company_name)

        raw = await chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,  # deterministic query_plan; higher temp invites hallucinations
        )
        plan = self._parse_llm_output(raw)

        # Force-inject the confirmed company_name — REQ-052 §5.7 contract.
        # This OVERWRITES whatever the LLM returned for company_name. The
        # LLM is a guesser; confirmed_company_name is ground truth from
        # the REQ-046 entity confirmation flow.
        if confirmed_company_name:
            filters = plan.setdefault("filters", {})
            filters["company_name"] = {
                "op": "eq",
                "value": confirmed_company_name,
            }

        plan.setdefault("limit", self.DEFAULT_LIMIT)
        return plan

    def _build_system_prompt(self, semantic_model: Any) -> str:
        """System prompt — instructs the LLM to emit ONLY the query_plan JSON.

        The schema is rendered from the semantic model so the LLM has
        ground-truth column names + metric definitions to choose from.

        REQ-054: the prompt now also names the ``catalog_id`` so the LLM
        knows which database's schema it's reading. V1 only surfaces the
        UUID (no human-readable catalog name) — that's enough for the
        LLM to disambiguate when a tenant has multiple catalogs, and it
        avoids an extra catalog-name query in the planner hot path.
        V2 can resolve ``catalog_name`` / ``catalog_code`` from the
        catalog service and inline them here.
        """
        column_mapping = list(semantic_model.column_mapping.keys())
        metric_definitions = list(semantic_model.metric_definitions.keys())
        # REQ-054: catalog_id is a UUID on the SemanticModel dataclass.
        # ``str(...)`` is safe for both uuid.UUID and the rare str fallback.
        catalog_id_str = str(getattr(semantic_model, "catalog_id", "") or "")
        return (
            "你是问数助手。基于语义层 schema 生成 query_plan (JSON)。\n\n"
            "语义层 schema:\n"
            f"- 当前数据库 ID (catalog_id): {catalog_id_str}\n"
            f"- entity_type: {semantic_model.entity_type}\n"
            f"- entity_name: {semantic_model.entity_name}\n"
            f"- column_mapping: {column_mapping}\n"
            f"- metric_definitions: {metric_definitions}\n\n"
            "规则:\n"
            "1. 只输出 query_plan JSON，不要解释\n"
            "2. entity 必须从 entity_type 选\n"
            "3. metrics 必须从 metric_definitions 选（如不需要聚合填空数组）\n"
            "4. filters 用 column_mapping 的 key\n"
            "5. time_range 字段必须是 date 类型\n"
            f"6. limit 默认 {self.DEFAULT_LIMIT}\n\n"
            '输出格式: {"entity": "...", "metrics": [...], "filters": '
            '{...}, "time_range": {...}, "limit": N}'
        )

    def _build_user_prompt(
        self, question: str, confirmed_company_name: str | None
    ) -> str:
        """User prompt — the question itself, optionally with company hint."""
        prompt = f"问题: {question}"
        if confirmed_company_name:
            prompt += f"\n企业全称（已确认）: {confirmed_company_name}"
        return prompt

    def _parse_llm_output(self, raw: str) -> dict:
        """Strip markdown fence / leading prose, then ``json.loads``.

        The brief suggested a single ``re.search(r"\\{.*\\}", raw, re.DOTALL)``
        but that pattern — and its non-greedy variant — fails on real
        LLM output: JSON contains nested ``{}`` (e.g. ``"filters": {"col":
        {"op": "eq", "value": "X"}}``), and a regex will stop at the
        first inner ``}``, truncating the document.

        We instead do a brace-balance scan: walk the string char by char,
        track nesting depth, and return the substring from the first
        outer ``{`` to its matching ``}``. This correctly handles nested
        objects. As a defensive fallback, if no balanced object is found
        we try ``json.loads(raw)`` directly — this catches the case where
        the LLM returns a bare JSON document with no surrounding prose.

        Both paths raise ``json.JSONDecodeError`` if the result is
        malformed — that's intentional. The QueryService wraps this call
        and surfaces the error to the user.
        """
        candidate = self._extract_first_json_object(raw)
        if candidate is not None:
            return json.loads(candidate)
        return json.loads(raw)

    @staticmethod
    def _extract_first_json_object(text: str) -> str | None:
        """Brace-balanced scan: return the first outer ``{...}`` substring.

        Skips over content before the first ``{`` (e.g. ``"Here is the
        JSON: "``). Counts nesting depth; only ``}`` at depth 0 ends the
        match. Returns ``None`` if no balanced object is found.
        """
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if in_string:
                if ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return None
