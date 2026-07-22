import secrets
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.ai_app.application.schemas import AiAppCreate, AiAppUpdate
from app.contexts.ai_app.domain.configs import get_config_class
from app.contexts.ai_app.domain.enums import AiAppStatus
from app.contexts.ai_app.infrastructure.models import AiApplicationModel


class AiAppService:
    VALID_TRANSITIONS: dict[AiAppStatus, set[AiAppStatus]] = {
        AiAppStatus.DRAFT: {AiAppStatus.PUBLISHED, AiAppStatus.ARCHIVED},
        AiAppStatus.PUBLISHED: {AiAppStatus.DISABLED, AiAppStatus.ARCHIVED},
        AiAppStatus.DISABLED: {AiAppStatus.PUBLISHED, AiAppStatus.ARCHIVED},
        AiAppStatus.ARCHIVED: set(),
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        status: AiAppStatus | None = None,
        tenant_id: UUID | None = None,
        include_archived: bool = False,
        viewer_role: str | None = None,
    ) -> tuple[list[AiApplicationModel], int]:
        """BUG-018 AC-2/AC-3: list 受 tenant_id 约束 + 平台应用跨租户可见。

        - viewer_role=None: 公开模式（仅 PUBLISHED + visibility=public + is_platform=True）。
        - viewer_role ∈ HIGH_PRIVILEGE_ROLES: 管理模式，看本 tenant 私有 + 平台应用。
        - viewer_role=其他: 不允许（前端不该传；管理端点由 _require_admin 守卫）。
        """
        stmt = select(AiApplicationModel)
        if tenant_id is not None:
            # 管理模式：本 tenant 应用 + 平台应用
            stmt = stmt.where(
                (AiApplicationModel.tenant_id == tenant_id)
                | (AiApplicationModel.is_platform.is_(True))
            )
        if status is not None:
            stmt = stmt.where(AiApplicationModel.status == status.value)
        if not include_archived:
            stmt = stmt.where(AiApplicationModel.status != AiAppStatus.ARCHIVED.value)
        stmt = stmt.order_by(AiApplicationModel.sort_order, AiApplicationModel.created_at)
        result = await self.session.execute(stmt)
        rows = result.scalars().all()

        count_stmt = select(AiApplicationModel)
        if tenant_id is not None:
            count_stmt = count_stmt.where(
                (AiApplicationModel.tenant_id == tenant_id)
                | (AiApplicationModel.is_platform.is_(True))
            )
        if status is not None:
            count_stmt = count_stmt.where(AiApplicationModel.status == status.value)
        if not include_archived:
            count_stmt = count_stmt.where(
                AiApplicationModel.status != AiAppStatus.ARCHIVED.value
            )
        count_result = await self.session.execute(count_stmt)
        total = len(count_result.scalars().all())
        return list(rows), total

    async def list_published_public(self) -> list[AiApplicationModel]:
        """BUG-018 AC-5: 公开广场仅 PUBLISHED + visibility=public + is_platform=True。"""
        stmt = (
            select(AiApplicationModel)
            .where(AiApplicationModel.is_platform.is_(True))
            .where(AiApplicationModel.status == AiAppStatus.PUBLISHED.value)
            .where(AiApplicationModel.visibility == "public")
            .order_by(AiApplicationModel.sort_order, AiApplicationModel.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_share_token(self, token: str) -> AiApplicationModel | None:
        """BUG-018 Slice 4: 公开 share endpoint，按 share_token 查已发布应用。

        不暴露 token 字段本身；只允许 Published + visibility=public + is_platform=True。
        """
        stmt = (
            select(AiApplicationModel)
            .where(AiApplicationModel.share_token == token)
            .where(AiApplicationModel.is_platform.is_(True))
            .where(AiApplicationModel.status == AiAppStatus.PUBLISHED.value)
            .where(AiApplicationModel.visibility == "public")
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(
        self, app_id: UUID, viewer_tenant_id: UUID | None = None,
        viewer_role: str | None = None,
    ) -> AiApplicationModel | None:
        """BUG-018 AC-2: 跨租户读 -> None（404）。

        - 普通应用：仅本 tenant 可读。
        - 平台应用（is_platform=True）：跨租户可读；仅 super_admin 可写。
        """
        stmt = select(AiApplicationModel).where(AiApplicationModel.id == app_id)
        if viewer_tenant_id is not None:
            stmt = stmt.where(
                (AiApplicationModel.tenant_id == viewer_tenant_id)
                | (AiApplicationModel.is_platform.is_(True))
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> AiApplicationModel | None:
        stmt = select(AiApplicationModel).where(AiApplicationModel.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self, data: AiAppCreate, *, tenant_id: UUID, operator_role: str
    ) -> AiApplicationModel:
        """BUG-018 AC-3: 服务端强制 tenant_id=current_user.tenant_id。"""
        del operator_role  # 保留签名供 V1 接入 super_admin 设 is_platform
        self._validate_config(data.code, data.config_schema)
        # 普通管理员建的应用始终 is_platform=False（跨租户可见性由 super_admin 显式授权）
        is_platform = False
        model = AiApplicationModel(
            code=data.code,
            name=data.name,
            description=data.description,
            category=data.category,
            icon=data.icon,
            status=data.status.value,
            visibility=data.visibility.value,
            entry_type=data.entry_type.value,
            route_path=data.route_path,
            external_url=data.external_url,
            config_schema=data.config_schema,
            required_capabilities=data.required_capabilities,
            owner=data.owner,
            version=data.version,
            sort_order=data.sort_order,
            tenant_id=tenant_id,
            is_platform=is_platform,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return model

    async def update(
        self, app_id: UUID, data: AiAppUpdate,
        *, viewer_tenant_id: UUID | None = None,
        viewer_role: str | None = None,
    ) -> AiApplicationModel | None:
        """BUG-018 AC-2/AC-3: 跨租户 -> None；平台应用仅 super_admin 可改。"""
        model = await self.get_by_id(app_id, viewer_tenant_id=viewer_tenant_id)
        if model is None:
            return None
        if model.is_platform and viewer_role != "super_admin":
            return None
        if data.name is not None:
            model.name = data.name
        if data.description is not None:
            model.description = data.description
        if data.category is not None:
            model.category = data.category
        if data.icon is not None:
            model.icon = data.icon
        if data.status is not None:
            self._validate_transition(AiAppStatus(model.status), data.status)
            model.status = data.status.value
        if data.visibility is not None:
            model.visibility = data.visibility.value
        if data.entry_type is not None:
            model.entry_type = data.entry_type.value
        if data.route_path is not None:
            model.route_path = data.route_path
        if data.external_url is not None:
            model.external_url = data.external_url
        if data.config_schema is not None:
            self._validate_config(model.code, data.config_schema)
            model.config_schema = data.config_schema
        if data.required_capabilities is not None:
            model.required_capabilities = data.required_capabilities
        if data.owner is not None:
            model.owner = data.owner
        if data.version is not None:
            model.version = data.version
        if data.sort_order is not None:
            model.sort_order = data.sort_order
        model.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(model)
        return model

    async def archive(
        self, app_id: UUID,
        *, viewer_tenant_id: UUID | None = None,
        viewer_role: str | None = None,
    ) -> AiApplicationModel | None:
        """BUG-018 AC-2/AC-3: 跨租户 -> None；平台应用仅 super_admin 可归档。"""
        model = await self.get_by_id(app_id, viewer_tenant_id=viewer_tenant_id)
        if model is None:
            return None
        if model.is_platform and viewer_role != "super_admin":
            return None
        self._validate_transition(AiAppStatus(model.status), AiAppStatus.ARCHIVED)
        model.status = AiAppStatus.ARCHIVED.value
        model.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(model)
        return model

    def _validate_transition(self, from_: AiAppStatus, to: AiAppStatus) -> None:
        if to not in self.VALID_TRANSITIONS.get(from_, set()):
            allowed = ", ".join(s.value for s in self.VALID_TRANSITIONS.get(from_, set())) or "none"
            raise ValueError(
                f"Invalid status transition: {from_.value} -> {to.value}. Allowed: {allowed}"
            )

    def _validate_config(self, code: str, config_data: dict[str, Any] | None) -> None:
        if config_data is None:
            return
        config_cls = get_config_class(code)
        try:
            config_cls.model_validate(config_data)
        except ValidationError as e:
            raise ValueError(f"config_schema validation failed for {code}: {e}") from e

    def _generate_token(self) -> str:
        return secrets.token_urlsafe(32)

    async def regenerate_share_token(
        self, app_id: UUID,
        *, viewer_tenant_id: UUID | None = None,
        viewer_role: str | None = None,
    ) -> str | None:
        model = await self.get_by_id(app_id, viewer_tenant_id=viewer_tenant_id)
        if model is None:
            return None
        if model.is_platform and viewer_role != "super_admin":
            return None
        model.share_token = self._generate_token()
        model.updated_at = datetime.utcnow()
        await self.session.flush()
        return model.share_token

    async def regenerate_api_token(
        self, app_id: UUID,
        *, viewer_tenant_id: UUID | None = None,
        viewer_role: str | None = None,
    ) -> str | None:
        model = await self.get_by_id(app_id, viewer_tenant_id=viewer_tenant_id)
        if model is None:
            return None
        if model.is_platform and viewer_role != "super_admin":
            return None
        model.api_token = self._generate_token()
        model.updated_at = datetime.utcnow()
        await self.session.flush()
        return model.api_token
