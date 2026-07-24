from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.domain import (
    AgentDefinitionVersion,
    CatalogConflictError,
    RuntimeBindingStatus,
    RuntimeCapabilitySnapshot,
    RuntimeProfile,
    RuntimeSessionBinding,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.repository import (
    AgentExecutionIdentityRepository,
)

DIRECT_RAG_DEFINITION_KEY = "system.direct_rag"
DIRECT_RAG_DEFINITION_VERSION = 1
DIRECT_RAG_PROFILE_KEY = "compat.direct_rag.v1"

DIRECT_RAG_CAPABILITIES = RuntimeCapabilitySnapshot(
    runtime_kind="compatibility",
    adapter_key="direct_rag",
    resume=False,
    steer=False,
    native_tools=False,
    tool_calls=False,
    input_requests=False,
    approvals=False,
    event_ack=False,
)


@dataclass(frozen=True, slots=True)
class CompatibilityIdentity:
    agent_definition_version: AgentDefinitionVersion
    runtime_profile: RuntimeProfile
    capability_snapshot: RuntimeCapabilitySnapshot


class ExecutionIdentityService:
    def __init__(self, session: AsyncSession):
        self._repository = AgentExecutionIdentityRepository(session)

    async def bootstrap_direct_rag(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> CompatibilityIdentity:
        definition_digest = snapshot_digest(
            {
                "definition_key": DIRECT_RAG_DEFINITION_KEY,
                "execution_mode": "compatibility",
                "schema_version": 1,
                "version": DIRECT_RAG_DEFINITION_VERSION,
            }
        )
        definition = await self._repository.publish_agent_definition_version(
            tenant_id=tenant_id,
            definition_key=DIRECT_RAG_DEFINITION_KEY,
            version=DIRECT_RAG_DEFINITION_VERSION,
            definition_digest=definition_digest,
            created_by=actor_id,
        )
        profile_config = {
            "adapter_key": "direct_rag",
            "profile_key": DIRECT_RAG_PROFILE_KEY,
            "runtime_kind": "compatibility",
            "schema_version": 1,
        }
        profile = await self._repository.publish_runtime_profile(
            tenant_id=tenant_id,
            profile_key=DIRECT_RAG_PROFILE_KEY,
            runtime_kind="compatibility",
            adapter_key="direct_rag",
            config_digest=snapshot_digest(profile_config),
            capability_digest=snapshot_digest(DIRECT_RAG_CAPABILITIES),
            enabled=True,
        )
        return CompatibilityIdentity(
            agent_definition_version=definition,
            runtime_profile=profile,
            capability_snapshot=DIRECT_RAG_CAPABILITIES,
        )

    async def publish_runtime_profile(
        self,
        *,
        tenant_id: uuid.UUID,
        profile_key: str,
        runtime_kind: str,
        adapter_key: str,
        config_digest: str,
        capability_snapshot: RuntimeCapabilitySnapshot,
        enabled: bool = False,
    ) -> RuntimeProfile:
        if (
            capability_snapshot.runtime_kind != runtime_kind
            or capability_snapshot.adapter_key != adapter_key
        ):
            raise CatalogConflictError(
                "capability snapshot does not match Runtime profile identity"
            )
        return await self._repository.publish_runtime_profile(
            tenant_id=tenant_id,
            profile_key=profile_key,
            runtime_kind=runtime_kind,
            adapter_key=adapter_key,
            config_digest=config_digest,
            capability_digest=snapshot_digest(capability_snapshot),
            enabled=enabled,
        )

    async def create_runtime_binding(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        runtime_profile_id: uuid.UUID,
    ) -> RuntimeSessionBinding:
        profile = await self._repository.require_enabled_runtime_profile(
            tenant_id=tenant_id,
            profile_id=runtime_profile_id,
        )
        if profile.runtime_kind == "compatibility":
            raise CatalogConflictError(
                "compatibility profiles do not create Runtime session bindings"
            )
        now = datetime.now(UTC)
        return await self._repository.create_runtime_binding(
            RuntimeSessionBinding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                runtime_profile_id=runtime_profile_id,
                runtime_session_ref=None,
                status=RuntimeBindingStatus.CREATING,
                current_epoch=1,
                next_expected_runtime_seq=1,
                acked_through_runtime_seq=0,
                active_stream_id=None,
                stream_lease_expires_at=None,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )

    async def activate_runtime_binding(
        self,
        *,
        tenant_id: uuid.UUID,
        binding_id: uuid.UUID,
        runtime_session_ref: str,
        expected_revision: int,
    ) -> RuntimeSessionBinding:
        return await self._repository.activate_runtime_binding(
            tenant_id=tenant_id,
            binding_id=binding_id,
            runtime_session_ref=runtime_session_ref,
            expected_revision=expected_revision,
            now=datetime.now(UTC),
        )

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
        if not 1 <= lease_seconds <= 300:
            raise ValueError("ingest stream lease must be between 1 and 300 seconds")
        return await self._repository.claim_ingest_stream(
            tenant_id=tenant_id,
            binding_id=binding_id,
            runtime_profile_id=runtime_profile_id,
            runtime_epoch=runtime_epoch,
            stream_id=stream_id,
            lease_seconds=lease_seconds,
        )
