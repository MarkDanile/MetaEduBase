"""Skill domain entity + SOP template value object for REQ-045.

A skill is a tenant-scoped registration of a *declarative SOP template*:
the YAML body defines metadata (A layer, aligned with the agentskills.io
open standard) plus the SOP body (B layer: MCP dependencies, workflow
steps bound to ``server_code.tool_name``, and a fill-in report skeleton).
This dataclass is the pure-Python domain representation — persistence is
handled by :class:`SkillModel` (ORM) and the repository (Task 2).

``SopTemplate`` parses and structurally validates the YAML body
(``yaml.safe_load`` only — never ``load``). Structural violations raise
:class:`SopTemplateError`. Whether a step's referenced server is actually
registered in the tenant's ``mcp_servers`` is a *service-layer* concern
(it needs the DB) and is intentionally not checked here.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import yaml

_KEBAB_CASE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_MAX_NAME_LENGTH = 64
_MAX_DESCRIPTION_LENGTH = 1024
# Abuse guard: reject oversized templates before parsing (~100KB).
MAX_TEMPLATE_BYTES = 100 * 1024


class SopTemplateError(Exception):
    """Raised when a SOP template fails parsing or structural validation."""


@dataclass(frozen=True)
class SopStep:
    """One workflow step: an analysis dimension bound to an MCP tool."""

    id: str
    server: str
    tool: str
    title: str | None = None
    analysis_rules: tuple[str, ...] = ()
    output: str | None = None


@dataclass(frozen=True)
class SopTemplate:
    """Parsed + structurally validated SOP template (spec section 4.3)."""

    name: str
    description: str
    steps: tuple[SopStep, ...]
    mcp_dependencies: tuple[str, ...] = ()
    principles: tuple[str, ...] = ()
    report_template: str | None = None

    @classmethod
    def parse(cls, yaml_text: str) -> SopTemplate:
        """Parse YAML text into a validated SopTemplate.

        Rejects oversized templates before parsing (abuse guard), uses
        ``yaml.safe_load`` exclusively, and raises :class:`SopTemplateError`
        with a message naming the specific missing / invalid item on any
        structural violation.
        """
        if len(yaml_text.encode("utf-8")) > MAX_TEMPLATE_BYTES:
            raise SopTemplateError(
                f"sop_template exceeds size limit of {MAX_TEMPLATE_BYTES} bytes"
            )
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as exc:
            raise SopTemplateError(f"sop_template is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise SopTemplateError("sop_template must be a YAML mapping")
        cls.validate(data)
        return cls._build(data)

    @staticmethod
    def validate(data: dict[str, Any]) -> None:
        """Structural validation per spec section 4.3 (A layer + B layer).

        Raises :class:`SopTemplateError` on the first violation found.
        """
        # A layer: name / description.
        name = data.get("name")
        if not isinstance(name, str) or not name:
            raise SopTemplateError("sop_template missing required field: name")
        if len(name) > _MAX_NAME_LENGTH or not _KEBAB_CASE_PATTERN.match(name):
            raise SopTemplateError(
                "sop_template name must be kebab-case "
                "(^[a-z0-9]+(-[a-z0-9]+)*$) and <= 64 chars"
            )
        description = data.get("description")
        if not isinstance(description, str) or not description.strip():
            raise SopTemplateError("sop_template missing required field: description")
        if len(description) > _MAX_DESCRIPTION_LENGTH:
            raise SopTemplateError(
                f"sop_template description must be <= {_MAX_DESCRIPTION_LENGTH} chars"
            )

        # B layer: steps.
        steps = data.get("steps")
        if not isinstance(steps, list) or not steps:
            raise SopTemplateError("sop_template steps must be a non-empty list")
        seen_ids: set[str] = set()
        used_servers: set[str] = set()
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise SopTemplateError(f"sop_template steps[{index}] must be a mapping")
            step_id = step.get("id")
            if not isinstance(step_id, str) or not step_id:
                raise SopTemplateError(
                    f"sop_template steps[{index}] missing required field: id"
                )
            if step_id in seen_ids:
                raise SopTemplateError(
                    f"sop_template duplicate step id: {step_id}"
                )
            seen_ids.add(step_id)
            server = step.get("server")
            if not isinstance(server, str) or not server:
                raise SopTemplateError(
                    f"sop_template step {step_id!r} missing required field: server"
                )
            tool = step.get("tool")
            if not isinstance(tool, str) or not tool:
                raise SopTemplateError(
                    f"sop_template step {step_id!r} missing required field: tool"
                )
            used_servers.add(server)
            # List-typed step fields must actually be lists — a scalar like
            # `analysis_rules: abc` must be rejected, not silently iterated
            # into single-character strings downstream (Important #2).
            analysis_rules = step.get("analysis_rules")
            if analysis_rules is not None and not isinstance(analysis_rules, list):
                raise SopTemplateError(
                    f"sop_template step {step_id!r} analysis_rules must be a list"
                )

        # B layer: mcp_dependencies — required in effect: when steps reference
        # servers, an absent mcp_dependencies is treated as an empty declaration
        # and still goes through coverage validation, so it always fails for a
        # non-empty steps list (Important #1). Coverage semantics (declared
        # superset of used) — over-declaring an unused server is benign.
        declared_servers: set[str] = set()
        dependencies = data.get("mcp_dependencies") or []
        if not isinstance(dependencies, list):
            raise SopTemplateError(
                "sop_template mcp_dependencies must be a list"
            )
        for index, dep in enumerate(dependencies):
            if not isinstance(dep, dict) or not dep.get("server"):
                raise SopTemplateError(
                    "sop_template mcp_dependencies"
                    f"[{index}] missing required field: server"
                )
            declared_servers.add(dep["server"])
        uncovered = used_servers - declared_servers
        if uncovered:
            raise SopTemplateError(
                "sop_template mcp_dependencies does not cover step "
                f"server(s): {sorted(uncovered)}"
            )

        # principles must be a list when present (Important #2).
        principles = data.get("principles")
        if principles is not None and not isinstance(principles, list):
            raise SopTemplateError("sop_template principles must be a list")

    @staticmethod
    def _build(data: dict[str, Any]) -> SopTemplate:
        steps = tuple(
            SopStep(
                id=step["id"],
                server=step["server"],
                tool=step["tool"],
                title=step.get("title"),
                analysis_rules=tuple(step.get("analysis_rules") or ()),
                output=step.get("output"),
            )
            for step in data["steps"]
        )
        dependencies = tuple(
            dep["server"] for dep in data.get("mcp_dependencies") or ()
        )
        principles = tuple(data.get("principles") or ())
        return SopTemplate(
            name=data["name"],
            description=data["description"],
            steps=steps,
            mcp_dependencies=dependencies,
            principles=principles,
            report_template=data.get("report_template"),
        )


@dataclass
class Skill:
    """Domain entity for a tenant-scoped skill registration."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    code: str
    version: str
    name: str
    sop_template: str
    description: str | None = None
    source_ref: str | None = None
    allowed_roles: list[str] = field(default_factory=list)
    enabled: bool = False
    is_active: bool = True
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def allows_role(self, role: str) -> bool:
        """白名单校验：role 是否被允许执行该 skill（空列表 = 仅 super_admin）。"""
        return role == "super_admin" or role in self.allowed_roles
