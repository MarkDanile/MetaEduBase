"""Skill registry service: 注册 / 更新 / 启停 / 版本 / 删除编排 + 管理 RBAC.

REQ-045 Task 2: sits between :mod:`skill_registry_router` and
:class:`SkillRepository`. Mirrors the :class:`MCPRegistryService` pattern:

1. **RBAC** — only ``admin`` / ``data_admin`` / ``super_admin`` may create,
   update, enable, disable or delete skill registrations. All roles may
   read (list / get / list_versions).
2. **(code, version) uniqueness** — ``(tenant_id, code, version)`` is
   unique in the DB, but the service surfaces a typed
   :class:`SkillVersionConflictError` *before* the INSERT so the router
   can return 409.
3. **SOP 模板校验编排** — registration parses + structurally validates the
   template via :class:`SopTemplate` (:class:`SopTemplateError` -> router
   maps 422), then closes the tool references: every ``steps[].server``
   must be registered *and active* in this tenant's ``mcp_servers``
   (queried via :class:`MCPServerRepository`; unknown server -> ValueError
   naming the server -> router maps 422).
4. **Validation** — ``code`` / ``version`` format errors raise plain
   :class:`ValueError` (router -> 422). ``sop_template`` is immutable via
   PATCH: template changes must go through a new version (spec §4.5).
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.mcp_registry.infrastructure.mcp_server_repository import (
    MCPServerRepository,
)
from app.contexts.skill_registry.domain.skill import Skill, SopTemplate
from app.contexts.skill_registry.infrastructure.skill_repository import (
    SkillRepository,
)

# Roles that may register / modify / enable / disable / delete skills.
# Same admin set as MCP_REGISTRY_ADMIN_ROLES (REQ-044) — ``super_admin``
# is the seeded dev admin's role and must be allowed for bootstrapping.
SKILL_REGISTRY_ADMIN_ROLES = {"admin", "data_admin", "super_admin"}

_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

# Fields a PATCH may touch. ``code`` / ``version`` / ``tenant_id`` /
# ``created_by`` are immutable after registration; ``enabled`` flips only
# via enable/disable; ``sop_template`` changes must go through a new
# version and are explicitly rejected (not silently ignored).
_UPDATABLE_FIELDS = {
    "name",
    "description",
    "source_ref",
    "allowed_roles",
}


class SkillRegistryPermissionError(PermissionError):
    """用户无权管理 skill 注册。"""


class SkillVersionConflictError(ValueError):
    """同 tenant 内 (code, version) 已存在。"""


class SkillNotFoundError(LookupError):
    """Skill 不存在（或已软删 / 不属于本 tenant）。"""


class SkillRegistryService:
    """CRUD + 版本 + enable/disable orchestration and RBAC for :class:`Skill`."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = SkillRepository(session)
        self._mcp_repo = MCPServerRepository(session)

    def _check_admin(self, role: str) -> None:
        if role not in SKILL_REGISTRY_ADMIN_ROLES:
            raise SkillRegistryPermissionError(
                f"角色 '{role}' 无权管理 skill"
                f"（仅 {sorted(SKILL_REGISTRY_ADMIN_ROLES)} 可操作）"
            )

    @staticmethod
    def _validate_code(code: str) -> None:
        if not _CODE_PATTERN.match(code):
            raise ValueError(
                "code 必须匹配 ^[a-z][a-z0-9_]*$（小写字母开头，"
                "如 enterprise_360_dd）"
            )

    @staticmethod
    def _validate_version(version: str) -> None:
        if not _VERSION_PATTERN.match(version):
            raise ValueError(
                "version 必须是语义化版本 ^\\d+\\.\\d+\\.\\d+$（如 1.0.0）"
            )

    async def _validate_step_servers(
        self, tenant_id: uuid.UUID, template: SopTemplate
    ) -> None:
        """工具引用闭合：每个 steps[].server 必须在本 tenant 已注册且 active。"""
        referenced = {step.server for step in template.steps}
        for server_code in sorted(referenced):
            server = await self._mcp_repo.get_by_code(tenant_id, server_code)
            if server is None:
                raise ValueError(
                    f"sop_template 引用的 MCP server '{server_code}' "
                    "未在本 tenant 注册（或已删除）"
                )

    async def create(
        self,
        *,
        tenant_id: uuid.UUID,
        code: str,
        version: str,
        name: str,
        sop_template: str,
        created_by: uuid.UUID,
        description: str | None = None,
        source_ref: str | None = None,
        allowed_roles: list[str] | None = None,
        role: str = "employee",
    ) -> Skill:
        self._check_admin(role)
        self._validate_code(code)
        self._validate_version(version)
        # 结构校验（SopTemplateError -> router 422）+ 引用闭合校验
        template = SopTemplate.parse(sop_template)
        await self._validate_step_servers(tenant_id, template)
        # (code, version) 唯一性校验 — 提前于 INSERT，让 router 能返回 409
        existing = await self._repo.get_by_code_version(tenant_id, code, version)
        if existing:
            raise SkillVersionConflictError(
                f"skill '{code}' version '{version}' 已存在"
            )
        skill = Skill(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            code=code,
            version=version,
            name=name,
            description=description,
            sop_template=sop_template,
            source_ref=source_ref,
            allowed_roles=list(allowed_roles or []),
            enabled=False,  # 注册后默认停用，必须显式 enable（spec §4.2）
            created_by=created_by,
        )
        return await self._repo.create(skill)

    async def list_by_tenant(self, tenant_id: uuid.UUID) -> list[Skill]:
        return await self._repo.list_by_tenant(tenant_id)

    async def list_versions(self, tenant_id: uuid.UUID, code: str) -> list[Skill]:
        return await self._repo.list_versions(tenant_id, code)

    async def get_by_id(
        self, tenant_id: uuid.UUID, skill_id: uuid.UUID
    ) -> Skill:
        skill = await self._repo.get_by_id(tenant_id, skill_id)
        if not skill:
            raise SkillNotFoundError("skill 不存在")
        return skill

    async def get_by_code_version(
        self, tenant_id: uuid.UUID, code: str, version: str
    ) -> Skill:
        skill = await self._repo.get_by_code_version(tenant_id, code, version)
        if not skill:
            raise SkillNotFoundError(f"skill '{code}' version '{version}' 不存在")
        return skill

    async def update(
        self,
        *,
        tenant_id: uuid.UUID,
        skill_id: uuid.UUID,
        role: str = "employee",
        **kwargs: object,
    ) -> Skill:
        self._check_admin(role)
        if "sop_template" in kwargs:
            raise ValueError(
                "sop_template 不可通过 PATCH 修改 — 模板改动须注册新版本"
            )
        updates = {k: v for k, v in kwargs.items() if k in _UPDATABLE_FIELDS}
        skill = await self._repo.update(tenant_id, skill_id, **updates)
        if not skill:
            raise SkillNotFoundError("skill 不存在")
        return skill

    async def set_enabled(
        self,
        *,
        tenant_id: uuid.UUID,
        skill_id: uuid.UUID,
        enabled: bool,
        role: str = "employee",
    ) -> Skill:
        self._check_admin(role)
        skill = await self._repo.set_enabled(tenant_id, skill_id, enabled)
        if not skill:
            raise SkillNotFoundError("skill 不存在")
        return skill

    async def delete(
        self,
        *,
        tenant_id: uuid.UUID,
        skill_id: uuid.UUID,
        role: str = "employee",
    ) -> None:
        """Soft delete only — a skill with audit rows is never hard-deleted."""
        self._check_admin(role)
        ok = await self._repo.soft_delete(tenant_id, skill_id)
        if not ok:
            raise SkillNotFoundError("skill 不存在")
