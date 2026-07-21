"""park_investment_dd.yaml template contract (REQ-046 PR-5 / Slice 4).

The park-investment due-diligence SKILL integrates three step channels in one
SOP — external QCC facts, internal customer 360 (Internal Customer MCP), and
internal data query (REQ-052 semantic layer). These tests pin the on-disk
template to spec §4.4 / §4.5 / §4.6 so a drift in the YAML fails loudly:
- three step types present (mcp external / mcp internal_customer / internal_query).
- internal_query steps cover >= 3 due-diligence questions (AC-4) and interpolate
  only ``{company_name}`` (matches the confirmed_subject shape §4.2).
- report_contract declares the §4.6 seven keys with runner-bound evidence_refs.
- mcp_dependencies cover every mcp step server (reference closure).
Real file, parse-only — no DB, no network.
"""
from __future__ import annotations

from pathlib import Path

from app.contexts.skill_registry.domain.skill import SopTemplate

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "contexts"
    / "skill_registry"
    / "templates"
    / "park_investment_dd.yaml"
)

_SEVEN_KEYS = {
    "summary",
    "external_facts",
    "internal_facts",
    "risk_watch_items",
    "human_review_items",
    "evidence_refs",
    "report_sections",
}


def _template() -> SopTemplate:
    assert TEMPLATE_PATH.exists(), f"template not found: {TEMPLATE_PATH}"
    return SopTemplate.parse(TEMPLATE_PATH.read_text(encoding="utf-8"))


def test_template_loads_and_names():
    tpl = _template()
    assert tpl.name == "park-investment-dd"
    assert tpl.description.strip()


def test_three_step_channels_present():
    tpl = _template()
    by_id = {s.id: s for s in tpl.steps}
    # external QCC + internal customer are mcp steps
    mcp = [s for s in tpl.steps if s.type == "mcp"]
    servers = {s.server for s in mcp}
    assert "qcc" in servers
    assert "internal_customer" in servers
    # internal data query channel present
    queries = [s for s in tpl.steps if s.type == "internal_query"]
    assert queries, "expected at least one internal_query step"
    assert by_id["internal_customer"].tool == "get_customer_360"


def test_internal_query_covers_three_dd_questions():
    """AC-4: >= 3 due-diligence questions routed to the semantic layer."""
    tpl = _template()
    queries = [s for s in tpl.steps if s.type == "internal_query"]
    assert len(queries) >= 3
    entity_types = {q.entity_type for q in queries}
    # 欠费 / 租约到期 / 工单满意度 three canonical DD angles
    assert {"bill", "lease_term", "ticket"} <= entity_types


def test_internal_query_templates_interpolate_only_company_name():
    """question_template placeholders must match the confirmed_subject shape
    (§4.2 ``{company_name, credit_code}``); an unknown placeholder would fail
    formatting at run time."""
    import string

    tpl = _template()
    for q in (s for s in tpl.steps if s.type == "internal_query"):
        fields = [
            fname
            for _, fname, _, _ in string.Formatter().parse(q.question_template)
            if fname
        ]
        assert fields, f"{q.id} question_template has no placeholder"
        for fname in fields:
            assert fname == "company_name", (
                f"{q.id} uses unexpected placeholder {fname!r}"
            )


def test_report_contract_declares_seven_keys():
    tpl = _template()
    assert tpl.report_contract is not None
    schema = tpl.report_contract["schema"]
    assert set(schema["required"]) == _SEVEN_KEYS


def test_report_contract_evidence_refs_runner_bound():
    """evidence_refs items only carry source_step from the LLM; ref_id /
    evidence_type are injected by the runner and must be uuid-typed refs."""
    tpl = _template()
    props = tpl.report_contract["schema"]["properties"]
    item = props["evidence_refs"]["items"]
    assert set(item["required"]) == {"source_step", "evidence_type", "ref_id"}
    assert item["properties"]["evidence_type"]["enum"] == [
        "mcp_invocation",
        "data_query",
    ]
    assert item["properties"]["ref_id"]["format"] == "uuid"


def test_mcp_dependencies_cover_step_servers():
    tpl = _template()
    declared = set(tpl.mcp_dependencies)
    used = {s.server for s in tpl.steps if s.type == "mcp"}
    assert used <= declared
    assert {"qcc", "internal_customer"} <= declared
