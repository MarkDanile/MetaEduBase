"""SkillRunner — SOP execution engine for REQ-045 Task 3 (spec §4.4).

The single orchestration entry point for executing a registered skill:

    resolve skill (tenant, code, version)
      -> check enabled                (else audit ok=False error_code=disabled)
      -> check caller role            (else audit ok=False error_code=forbidden)
      -> SopTemplate.parse            (else audit ok=False error_code=template_error)
      -> for step in steps:           (sequential, spec §4.4)
           MCPInvocationService.invoke(server_code=step.server,
                                       tool_name=step.tool, params=subject)
           # any MCPInvocationError -> whole run fails error_code=tool_error
           # (V1: all steps treated as required — never fabricate facts)
      -> llm.chat(report_template + facts)   (else audit ok=False error_code=llm_error)
      -> write execution audit (subject/steps/report digests, ok, duration_ms)
      -> return SkillResult (report + execution_audit_id + per-step digests)

An unregistered / soft-deleted skill is the ONLY failure branch with no
audit row — there is no ``skill_id`` to associate, so it raises
:class:`SkillExecutionNotFoundError` before any audit write (mirrors
:class:`MCPInvocationServerNotFoundError`, spec §4.4 first line).

Digest convention (spec §4.2, same as REQ-044): ``sha256(canonical_json)``
with sorted keys and compact separators, via
:func:`canonical_digest`. Raw subject / facts / report bodies are NEVER
persisted — the audit row only proves reproducibility ("which version ran
against which subject produced which artifact"). ``report_digest`` is the
plain ``sha256`` of the report text (UTF-8); ``steps_digest`` is the
canonical digest of ``{step_id: result_digest}`` — each step's MCP call is
itself audited in ``mcp_invocation_audit`` by REQ-044, and the per-step
``params_digest``/``response_digest`` there link the two audit trails.

``error_message`` is truncated to 500 chars and scrubbed of any subject
string values (a malicious or verbose MCP error must not echo raw
enterprise identifiers into the audit table).

Assembly boundary (spec §4.1): this is the ONLY place an
:class:`MCPInvocationService` and the LLM entry
(:func:`app.shared.llm.chat.chat`) are wired together — business code
receives the runner, never the underlying services.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.mcp_registry.application.mcp_invocation_service import (
    InvocationCaller,
    MCPInvocationError,
    MCPInvocationService,
    canonical_digest,
)
from app.contexts.skill_registry.domain.skill import Skill, SopTemplate, SopTemplateError
from app.contexts.skill_registry.infrastructure.skill_execution_audit_repository import (
    SkillExecutionAuditRepository,
)
from app.contexts.skill_registry.infrastructure.skill_models import (
    SkillExecutionAuditModel,
)
from app.contexts.skill_registry.infrastructure.skill_repository import (
    SkillRepository,
)
from app.shared.llm.chat import chat

_ERROR_MESSAGE_MAX = 500


def _iter_subject_values(subject: Any) -> list[str]:
    """Yield every scalar value in ``subject`` as a string for scrubbing.

    Recurses into nested dict / list and stringifies non-string scalars so a
    numeric credit code or an id nested under a key is not missed when
    scrubbing error messages.
    """
    values: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)
        elif isinstance(node, str):
            values.append(node)
        elif node is not None:
            values.append(str(node))

    _walk(subject)
    return values


class SkillExecutionError(Exception):
    """Typed execution failure — always paired with an audit row.

    ``error_code`` is one of ``disabled`` / ``forbidden`` /
    ``template_error`` / ``tool_error`` / ``llm_error``
    (``not_registered`` only via the NotFound subclass, which is NOT
    audited — see spec §4.4).
    """

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class SkillExecutionNotFoundError(SkillExecutionError, LookupError):
    """Skill code+version not registered for this tenant — no audit row."""

    def __init__(self, skill_code: str, version: str) -> None:
        super().__init__(
            "not_registered", f"skill '{skill_code}' version '{version}' 未注册"
        )


@dataclass(frozen=True)
class SkillStepResult:
    """Per-step summary in a :class:`SkillResult` — digest only, no facts."""

    id: str
    ok: bool
    digest: str | None = None


@dataclass(frozen=True)
class SkillResult:
    """Successful execution artifact returned to the caller.

    ``report`` is the LLM-synthesized structured artifact (fill-in of the
    SOP ``report_template``, carrying the 事实 / AI 分析 / 待人工确认
    partitions per spec §4.4); it is returned to the privileged caller
    only and never written to the audit table or logs. Raw per-step facts
    are intentionally NOT surfaced here - the caller gets the synthesized
    report, not the underlying tool payloads.

    """

    report: str
    execution_audit_id: uuid.UUID
    duration_ms: int
    steps: tuple[SkillStepResult, ...] = field(default_factory=tuple)


class SkillRunner:
    """SOP execution orchestration + audit for registered skills."""

    def __init__(
        self,
        session: AsyncSession,
        invocation_service: MCPInvocationService | None = None,
    ) -> None:
        self._session = session
        self._skills = SkillRepository(session)
        self._audit = SkillExecutionAuditRepository(session)
        # Assembly boundary: MCPInvocationService is constructed here and
        # only here (injectable for tests).
        self._invocation = invocation_service or MCPInvocationService(session)

    async def run(
        self,
        *,
        tenant_id: uuid.UUID,
        skill_code: str,
        version: str,
        subject: dict,
        caller: InvocationCaller,
    ) -> SkillResult:
        """Execute ``skill_code@version`` against ``subject``.

        Raises :class:`SkillExecutionNotFoundError` (unregistered, no
        audit) or :class:`SkillExecutionError` (audited failure).
        """
        started = time.monotonic()
        skill = await self._skills.get_by_code_version(tenant_id, skill_code, version)
        if skill is None:
            raise SkillExecutionNotFoundError(skill_code, version)

        # Computed up front so every audited failure branch carries it.
        subject_digest = canonical_digest(subject)

        def _duration() -> int:
            return int((time.monotonic() - started) * 1000)

        async def _fail(error_code: str, message: str) -> SkillExecutionError:
            await self._write_audit(
                tenant_id=tenant_id,
                skill=skill,
                caller=caller,
                subject_digest=subject_digest,
                steps_digest=None,
                report_digest=None,
                ok=False,
                error_code=error_code,
                error_message=self._sanitize(message, subject)[:_ERROR_MESSAGE_MAX],
                duration_ms=_duration(),
            )
            return SkillExecutionError(error_code, message)

        # ---- enabled gate ----
        if not skill.enabled:
            raise await _fail(
                "disabled", f"skill '{skill.code}' version '{skill.version}' 已停用"
            )

        # ---- role gate (empty allowed_roles = super_admin only) ----
        if not skill.allows_role(caller.role):
            raise await _fail(
                "forbidden",
                f"角色 '{caller.role}' 无权执行 skill '{skill.code}'",
            )

        # ---- template parse (DB 正文损坏时显式失败，不静默降级) ----
        try:
            template = SopTemplate.parse(skill.sop_template)
        except SopTemplateError as e:
            raise await _fail("template_error", f"SOP 模板解析失败: {e}") from e

        # ---- sequential steps via REQ-044 (V1: all required) ----
        facts: dict[str, Any] = {}
        step_results: list[SkillStepResult] = []
        for step in template.steps:
            try:
                result = await self._invocation.invoke(
                    tenant_id=tenant_id,
                    server_code=step.server,
                    tool_name=step.tool,
                    params=subject,
                    caller=caller,
                )
            except MCPInvocationError as e:
                # 任一步失败即整体失败 — 不编造事实（spec §4.4）。MCP 侧已
                # 在 mcp_invocation_audit 留痕（未注册 server 除外）。
                raise await _fail(
                    "tool_error",
                    f"step '{step.id}' 调用失败 ({e.error_code}): {e}",
                ) from e
            facts[step.id] = result
            step_results.append(
                SkillStepResult(id=step.id, ok=True, digest=canonical_digest(result))
            )

        # ---- LLM synthesis (fill-in report_template, no fabrication) ----
        messages = self._build_messages(template, subject_digest, facts)
        try:
            report = await chat(messages)
        except Exception as e:
            raise await _fail("llm_error", f"LLM 合成失败: {e}") from e

        report_digest = hashlib.sha256(report.encode("utf-8")).hexdigest()
        steps_digest = canonical_digest(
            {sr.id: sr.digest for sr in step_results}
        )
        duration_ms = _duration()
        audit_row = await self._write_audit(
            tenant_id=tenant_id,
            skill=skill,
            caller=caller,
            subject_digest=subject_digest,
            steps_digest=steps_digest,
            report_digest=report_digest,
            ok=True,
            error_code=None,
            error_message=None,
            duration_ms=duration_ms,
        )
        return SkillResult(
            report=report,
            execution_audit_id=audit_row.id,
            duration_ms=duration_ms,
            steps=tuple(step_results),
        )

    async def _write_audit(
        self,
        *,
        tenant_id: uuid.UUID,
        skill: Skill,
        caller: InvocationCaller,
        subject_digest: str | None,
        steps_digest: str | None,
        report_digest: str | None,
        ok: bool,
        error_code: str | None,
        error_message: str | None,
        duration_ms: int,
    ) -> SkillExecutionAuditModel:
        return await self._audit.write(
            tenant_id=tenant_id,
            skill_id=skill.id,
            skill_code=skill.code,
            skill_version=skill.version,
            caller_type=caller.caller_type,
            caller_user_id=caller.user_id,
            subject_digest=subject_digest,
            steps_digest=steps_digest,
            report_digest=report_digest,
            ok=ok,
            error_code=error_code,
            error_message=error_message,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _build_messages(
        template: SopTemplate, subject_digest: str, facts: dict[str, Any]
    ) -> list[dict]:
        """Build the LLM prompt: fill-in skeleton + collected facts.

        The raw subject never enters the prompt by reference here — facts
        are the tool outputs; the subject digest is included so the model
        context is bound to this execution without exposing identifiers
        beyond what the tools themselves returned.
        """
        principles = "\n".join(f"- {p}" for p in template.principles) or "- 无"
        report_skeleton = template.report_template or "## 事实数据\n## AI 分析"
        system = (
            "你是企业尽调报告助手。严格按给定报告骨架填空：只填值、不更改结构；"
            "缺失数据显式标注，不得编造。\n\n"
            f"执行纪律:\n{principles}\n\n"
            f"报告骨架:\n{report_skeleton}"
        )
        user = (
            f"执行标识: {subject_digest}\n"
            "各步骤事实数据 (JSON, 键为步骤 id):\n"
            + json.dumps(facts, ensure_ascii=False, default=str)
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def _sanitize(message: str, subject: dict) -> str:
        """Guarantee raw subject values never appear in stored text.

        Pure, non-raising: replaces every scalar subject value (recursing
        into nested dict / list, and stringifying non-string scalars so a
        numeric credit code is not missed) with ``***`` so a chatty MCP /
        LLM error cannot echo enterprise identifiers into the audit row.
        """
        for needle in _iter_subject_values(subject):
            if needle:
                message = message.replace(needle, "***")
        return message
