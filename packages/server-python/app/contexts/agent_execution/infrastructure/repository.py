from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.domain import (
    AgentDefinitionStatus,
    AgentDefinitionVersion,
    CatalogConflictError,
    CatalogNotFoundError,
    RuntimeBindingConflictError,
    RuntimeBindingNotFoundError,
    RuntimeBindingStatus,
    RuntimeEpochMismatchError,
    RuntimeProfile,
    RuntimeProfileDisabledError,
    RuntimeSessionBinding,
    RuntimeStreamLeaseConflictError,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentDefinitionVersionModel,
    RuntimeProfileModel,
    RuntimeSessionBindingModel,
)


class AgentExecutionIdentityRepository:
    """Tenant-scoped adapter for immutable catalogs and Runtime bindings."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def publish_agent_definition_version(
        self,
        *,
        tenant_id: uuid.UUID,
        definition_key: str,
        version: int,
        definition_digest: str,
        created_by: uuid.UUID,
    ) -> AgentDefinitionVersion:
        self._validate_key(definition_key, "definition key")
        self._validate_digest(definition_digest, "definition digest")
        if version < 1:
            raise ValueError("definition version must be positive")
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "definition_key": definition_key,
            "version": version,
            "status": AgentDefinitionStatus.PUBLISHED.value,
            "definition_digest": definition_digest,
            "created_by": created_by,
        }
        await self._session.execute(
            insert(AgentDefinitionVersionModel)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    AgentDefinitionVersionModel.tenant_id,
                    AgentDefinitionVersionModel.definition_key,
                    AgentDefinitionVersionModel.version,
                ]
            )
        )
        row = (
            await self._session.execute(
                select(AgentDefinitionVersionModel).where(
                    AgentDefinitionVersionModel.tenant_id == tenant_id,
                    AgentDefinitionVersionModel.definition_key == definition_key,
                    AgentDefinitionVersionModel.version == version,
                )
            )
        ).scalar_one()
        if (
            row.status != AgentDefinitionStatus.PUBLISHED.value
            or row.definition_digest != definition_digest
        ):
            raise CatalogConflictError(
                "agent definition key/version already has different published content"
            )
        return self._to_definition(row)

    async def publish_runtime_profile(
        self,
        *,
        tenant_id: uuid.UUID,
        profile_key: str,
        runtime_kind: str,
        adapter_key: str,
        config_digest: str,
        capability_digest: str,
        enabled: bool,
    ) -> RuntimeProfile:
        self._validate_key(profile_key, "profile key")
        self._validate_key(runtime_kind, "runtime kind")
        self._validate_key(adapter_key, "adapter key")
        self._validate_digest(config_digest, "config digest")
        self._validate_digest(capability_digest, "capability digest")
        values = {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "profile_key": profile_key,
            "runtime_kind": runtime_kind,
            "adapter_key": adapter_key,
            "config_digest": config_digest,
            "capability_digest": capability_digest,
            "enabled": enabled,
            "revision": 1,
        }
        await self._session.execute(
            insert(RuntimeProfileModel)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    RuntimeProfileModel.tenant_id,
                    RuntimeProfileModel.profile_key,
                ]
            )
        )
        row = (
            await self._session.execute(
                select(RuntimeProfileModel).where(
                    RuntimeProfileModel.tenant_id == tenant_id,
                    RuntimeProfileModel.profile_key == profile_key,
                )
            )
        ).scalar_one()
        immutable_identity = (
            row.runtime_kind,
            row.adapter_key,
            row.config_digest,
            row.capability_digest,
        )
        requested_identity = (
            runtime_kind,
            adapter_key,
            config_digest,
            capability_digest,
        )
        if immutable_identity != requested_identity:
            raise CatalogConflictError(
                "Runtime profile key already has different immutable content"
            )
        return self._to_profile(row)

    async def get_runtime_profile(
        self,
        *,
        tenant_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> RuntimeProfile | None:
        row = (
            await self._session.execute(
                select(RuntimeProfileModel).where(
                    RuntimeProfileModel.tenant_id == tenant_id,
                    RuntimeProfileModel.id == profile_id,
                )
            )
        ).scalar_one_or_none()
        return self._to_profile(row) if row is not None else None

    async def require_enabled_runtime_profile(
        self,
        *,
        tenant_id: uuid.UUID,
        profile_id: uuid.UUID,
    ) -> RuntimeProfile:
        profile = await self.get_runtime_profile(
            tenant_id=tenant_id, profile_id=profile_id
        )
        if profile is None:
            raise CatalogNotFoundError("Runtime profile not found")
        if not profile.enabled:
            raise RuntimeProfileDisabledError("Runtime profile is disabled")
        return profile

    async def create_runtime_binding(
        self, binding: RuntimeSessionBinding
    ) -> RuntimeSessionBinding:
        row = RuntimeSessionBindingModel(
            id=binding.id,
            tenant_id=binding.tenant_id,
            conversation_id=binding.conversation_id,
            runtime_profile_id=binding.runtime_profile_id,
            runtime_session_ref=binding.runtime_session_ref,
            status=binding.status.value,
            current_epoch=binding.current_epoch,
            next_expected_runtime_seq=binding.next_expected_runtime_seq,
            acked_through_runtime_seq=binding.acked_through_runtime_seq,
            active_stream_id=binding.active_stream_id,
            stream_lease_expires_at=binding.stream_lease_expires_at,
            revision=binding.revision,
            created_at=binding.created_at,
            updated_at=binding.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return self._to_binding(row)

    async def get_runtime_binding(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
    ) -> RuntimeSessionBinding | None:
        row = await self._get_binding_row(
            tenant_id=tenant_id,
            binding_id=binding_id,
            for_update=False,
        )
        return self._to_binding(row) if row is not None else None

    async def activate_runtime_binding(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
        runtime_session_ref: str,
        expected_revision: int,
        now: datetime,
    ) -> RuntimeSessionBinding:
        if not runtime_session_ref or len(runtime_session_ref) > 500:
            raise ValueError("runtime session ref must contain 1 to 500 characters")
        row = await self._require_binding_for_update(
            tenant_id=tenant_id, binding_id=binding_id
        )
        if row.revision != expected_revision or row.status != "creating":
            raise RuntimeBindingConflictError(
                "binding activation revision or status precondition failed"
            )
        row.runtime_session_ref = runtime_session_ref
        row.status = RuntimeBindingStatus.ACTIVE.value
        row.revision += 1
        row.updated_at = now
        await self._session.flush()
        return self._to_binding(row)

    async def claim_ingest_stream(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
        runtime_profile_id: uuid.UUID,
        runtime_epoch: int,
        stream_id: uuid.UUID,
        lease_seconds: int,
    ) -> RuntimeSessionBinding:
        row = await self._require_binding_for_update(
            tenant_id=tenant_id, binding_id=binding_id
        )
        self._validate_binding_owner(
            row,
            runtime_profile_id=runtime_profile_id,
            runtime_epoch=runtime_epoch,
        )
        if row.status != RuntimeBindingStatus.ACTIVE.value:
            raise RuntimeBindingConflictError("only active bindings can ingest events")
        database_now = await self._database_now()
        if (
            row.active_stream_id is not None
            and row.active_stream_id != stream_id
            and row.stream_lease_expires_at is not None
            and row.stream_lease_expires_at > database_now
        ):
            raise RuntimeStreamLeaseConflictError(
                "another ingest stream owns an unexpired lease"
        )
        row.active_stream_id = stream_id
        row.stream_lease_expires_at = database_now + timedelta(seconds=lease_seconds)
        row.revision += 1
        row.updated_at = database_now
        await self._session.flush()
        return self._to_binding(row)

    async def start_new_runtime_epoch(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
        runtime_profile_id: uuid.UUID,
        expected_epoch: int,
        expected_revision: int,
        runtime_session_ref: str,
        now: datetime,
    ) -> RuntimeSessionBinding:
        if not runtime_session_ref or len(runtime_session_ref) > 500:
            raise ValueError("runtime session ref must contain 1 to 500 characters")
        row = await self._require_binding_for_update(
            tenant_id=tenant_id, binding_id=binding_id
        )
        self._validate_binding_owner(
            row,
            runtime_profile_id=runtime_profile_id,
            runtime_epoch=expected_epoch,
        )
        if row.revision != expected_revision:
            raise RuntimeBindingConflictError("binding revision precondition failed")
        if row.status != RuntimeBindingStatus.RESUME_REQUIRED.value:
            raise RuntimeBindingConflictError(
                "only resume_required bindings can start a new epoch"
            )
        row.runtime_session_ref = runtime_session_ref
        row.status = RuntimeBindingStatus.ACTIVE.value
        row.current_epoch += 1
        row.next_expected_runtime_seq = 1
        row.acked_through_runtime_seq = 0
        row.active_stream_id = None
        row.stream_lease_expires_at = None
        row.revision += 1
        row.updated_at = now
        await self._session.flush()
        return self._to_binding(row)

    async def mark_runtime_binding_resume_required(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
        runtime_profile_id: uuid.UUID,
        expected_epoch: int,
        expected_revision: int,
    ) -> RuntimeSessionBinding:
        row = await self._require_binding_for_update(
            tenant_id=tenant_id, binding_id=binding_id
        )
        self._validate_binding_owner(
            row,
            runtime_profile_id=runtime_profile_id,
            runtime_epoch=expected_epoch,
        )
        if row.revision != expected_revision:
            raise RuntimeBindingConflictError("binding revision precondition failed")
        if row.status != RuntimeBindingStatus.ACTIVE.value:
            raise RuntimeBindingConflictError(
                "only active bindings can require resume"
            )
        database_now = await self._database_now()
        if (
            row.active_stream_id is not None
            and row.stream_lease_expires_at is not None
            and row.stream_lease_expires_at > database_now
        ):
            raise RuntimeStreamLeaseConflictError(
                "a live ingest stream must expire before resume is required"
            )
        row.status = RuntimeBindingStatus.RESUME_REQUIRED.value
        row.active_stream_id = None
        row.stream_lease_expires_at = None
        row.revision += 1
        row.updated_at = database_now
        await self._session.flush()
        return self._to_binding(row)

    async def _get_binding_row(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
        for_update: bool,
    ) -> RuntimeSessionBindingModel | None:
        statement = select(RuntimeSessionBindingModel).where(
            RuntimeSessionBindingModel.tenant_id == tenant_id,
            RuntimeSessionBindingModel.id == binding_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def _database_now(self) -> datetime:
        return (
            await self._session.execute(select(func.clock_timestamp()))
        ).scalar_one()

    async def _require_binding_for_update(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
    ) -> RuntimeSessionBindingModel:
        row = await self._get_binding_row(
            tenant_id=tenant_id,
            binding_id=binding_id,
            for_update=True,
        )
        if row is None:
            raise RuntimeBindingNotFoundError("Runtime binding not found")
        return row

    @staticmethod
    def _validate_binding_owner(
        row: RuntimeSessionBindingModel,
        *,
        runtime_profile_id: uuid.UUID,
        runtime_epoch: int,
    ) -> None:
        if row.runtime_profile_id != runtime_profile_id:
            raise RuntimeBindingConflictError(
                "Runtime profile does not own this binding"
            )
        if row.current_epoch != runtime_epoch:
            raise RuntimeEpochMismatchError(
                f"expected epoch {row.current_epoch}, got {runtime_epoch}"
            )

    @staticmethod
    def _validate_key(value: str, label: str) -> None:
        if not value or len(value) > 150:
            raise ValueError(f"{label} must contain 1 to 150 characters")

    @staticmethod
    def _validate_digest(value: str, label: str) -> None:
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(f"{label} must be lowercase SHA-256")

    @staticmethod
    def _to_definition(row: AgentDefinitionVersionModel) -> AgentDefinitionVersion:
        return AgentDefinitionVersion(
            id=row.id,
            tenant_id=row.tenant_id,
            definition_key=row.definition_key,
            version=row.version,
            status=AgentDefinitionStatus(row.status),
            definition_digest=row.definition_digest,
            created_by=row.created_by,
            created_at=row.created_at,
        )

    @staticmethod
    def _to_profile(row: RuntimeProfileModel) -> RuntimeProfile:
        return RuntimeProfile(
            id=row.id,
            tenant_id=row.tenant_id,
            profile_key=row.profile_key,
            runtime_kind=row.runtime_kind,
            adapter_key=row.adapter_key,
            config_digest=row.config_digest,
            capability_digest=row.capability_digest,
            enabled=row.enabled,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _to_binding(row: RuntimeSessionBindingModel) -> RuntimeSessionBinding:
        return RuntimeSessionBinding(
            id=row.id,
            tenant_id=row.tenant_id,
            conversation_id=row.conversation_id,
            runtime_profile_id=row.runtime_profile_id,
            runtime_session_ref=row.runtime_session_ref,
            status=RuntimeBindingStatus(row.status),
            current_epoch=row.current_epoch,
            next_expected_runtime_seq=row.next_expected_runtime_seq,
            acked_through_runtime_seq=row.acked_through_runtime_seq,
            active_stream_id=row.active_stream_id,
            stream_lease_expires_at=row.stream_lease_expires_at,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
