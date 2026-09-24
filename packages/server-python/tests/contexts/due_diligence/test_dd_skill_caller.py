"""DD skill port adapter — assembly + boundary discriminating tests (TD-085 Slice C).

Pins the post-decoupling contract (spec ADR-085-3 / plan §1.4):

1. ``dd_mcp_step_params`` keeps the migrated QCC param shaping byte-parity
   (moved verbatim from the old ``skill_runner._mcp_step_params``).
2. ``build_dd_skill_runner`` wires the generic SkillRunner with the DD
   query channel + DD param mapper + DD persona (single DD assembly point).
3. The generic runner stays business-neutral: ``skill_runner.py`` carries no
   qcc / 背调 / 尽调 / enterprise_diligence / due_diligence references.
4. Dependency direction is one-way: nothing under ``app/contexts/skill_registry/``
   imports ``app.contexts.due_diligence`` (both ``import`` and ``from`` forms
   scanned — the plain-``import`` blind spot was a Slice B P3 lesson).

All tests are DB-free (pure unit / source scans) so they run without PG.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

from app.contexts.due_diligence.application.skill_caller import (
    DD_REPORT_PERSONA,
    build_dd_skill_runner,
    dd_mcp_step_params,
)
from app.contexts.skill_registry.application.skill_runner import SkillRunner

_SERVER_PYTHON_ROOT = Path(__file__).resolve().parents[3]
_SKILL_RUNNER_PATH = (
    _SERVER_PYTHON_ROOT
    / "app"
    / "contexts"
    / "skill_registry"
    / "application"
    / "skill_runner.py"
)
_SKILL_REGISTRY_DIR = _SERVER_PYTHON_ROOT / "app" / "contexts" / "skill_registry"

_FORBIDDEN_RUNNER_TOKENS = ("qcc", "背调", "enterprise_diligence", "尽调", "due_diligence")


# ---------- 1. dd_mcp_step_params byte-parity (migrated QCC shaping) ----------


def test_qcc_server_maps_company_name_to_searchkey() -> None:
    subject = {"company_name": "ACME", "credit_code": "91X"}
    assert dd_mcp_step_params("qcc", subject) == {"searchKey": "ACME"}
    assert dd_mcp_step_params("qcc_company", subject) == {"searchKey": "ACME"}


def test_qcc_server_falls_back_to_searchkey_subject_key() -> None:
    assert dd_mcp_step_params("qcc", {"searchKey": "ACME"}) == {"searchKey": "ACME"}


def test_qcc_server_without_any_name_yields_empty_searchkey() -> None:
    assert dd_mcp_step_params("qcc", {"credit_code": "91X"}) == {"searchKey": ""}


def test_qcc_server_with_non_dict_subject_yields_empty_params() -> None:
    assert dd_mcp_step_params("qcc", "ACME") == {}
    assert dd_mcp_step_params("qcc", None) == {}


def test_non_qcc_server_gets_subject_as_is() -> None:
    subject = {"company_name": "ACME", "credit_code": "91X"}
    assert dd_mcp_step_params("internal_customer", subject) is subject


def test_non_qcc_server_with_non_dict_subject_yields_empty_params() -> None:
    assert dd_mcp_step_params("internal_customer", "ACME") == {}
    assert dd_mcp_step_params("internal_customer", None) == {}


# ---------- 2. build_dd_skill_runner assembly ----------


def test_dd_report_persona_is_the_dd_business_persona() -> None:
    assert DD_REPORT_PERSONA == "你是企业尽调报告助手。"


def test_build_dd_skill_runner_binds_dd_query_channel_mapper_and_persona() -> None:
    query_service = MagicMock()
    query_service.with_session.return_value = query_service
    session = MagicMock()

    runner = build_dd_skill_runner(query_service, session)

    assert isinstance(runner, SkillRunner)
    assert callable(runner._query_runner)
    assert runner._step_params_mapper is dd_mcp_step_params
    assert runner._report_persona == DD_REPORT_PERSONA
    # The request-scoped QueryService is re-bound to the given session so the
    # query audit row commits in the same transaction as the execution audit.
    query_service.with_session.assert_called_once_with(session)


def test_generic_runner_defaults_are_business_neutral() -> None:
    runner = SkillRunner(MagicMock(), invocation_service=MagicMock())

    assert runner._query_runner is None
    assert runner._report_persona == "你是报告生成助手。"
    # Default mapper is pass-through for any server (no provider key shaping).
    subject = {"company_name": "ACME", "credit_code": "91X"}
    assert runner._step_params_mapper("qcc", subject) is subject
    assert runner._step_params_mapper("internal_customer", subject) is subject
    assert runner._step_params_mapper("qcc", None) == {}


# ---------- 3. generic runner business-neutrality scan ----------


def test_skill_runner_source_carries_no_business_tokens() -> None:
    source = _SKILL_RUNNER_PATH.read_text(encoding="utf-8").lower()
    offenders = [token for token in _FORBIDDEN_RUNNER_TOKENS if token.lower() in source]
    assert offenders == [], f"skill_runner.py 仍含业务专属引用: {offenders}"


# ---------- 4. one-way dependency scan (skill_registry -/-> due_diligence) ----------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_skill_registry_never_imports_due_diligence() -> None:
    offenders: list[str] = []
    for path in sorted(_SKILL_REGISTRY_DIR.rglob("*.py")):
        for module in _imported_modules(path):
            if module.startswith("app.contexts.due_diligence"):
                offenders.append(f"{path.relative_to(_SERVER_PYTHON_ROOT)} -> {module}")
    assert offenders == [], "skill_registry → due_diligence 反向依赖: " + "; ".join(
        offenders
    )
