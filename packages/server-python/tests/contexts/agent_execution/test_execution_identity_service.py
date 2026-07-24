from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contexts.agent_execution.application.execution_identity_service import (
    DIRECT_RAG_CAPABILITIES,
    DIRECT_RAG_PROFILE_KEY,
    ExecutionIdentityService,
)
from app.contexts.agent_execution.domain import (
    CatalogConflictError,
    RuntimeBindingNotFoundError,
    RuntimeBindingStatus,
    RuntimeCapabilitySnapshot,
    RuntimeEpochMismatchError,
    RuntimeSessionBinding,
    RuntimeStreamLeaseConflictError,
    snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentDefinitionVersionModel,
    RuntimeProfileModel,
    RuntimeSessionBindingModel,
)
from app.contexts.agent_execution.infrastructure.repository import (
    AgentExecutionIdentityRepository,
)
from tests.conftest import TEST_DB_URL

TENANT_A = uuid.UUID("40000000-0000-0000-0000-000000000001")
TENANT_B = uuid.UUID("50000000-0000-0000-0000-000000000001")
ACTOR = uuid.UUID("40000000-0000-0000-0000-000000000002")


async def _native_profile(service: ExecutionIdentityService, tenant_id: uuid.UUID):
    capabilities = RuntimeCapabilitySnapshot(
        runtime_kind="pi",
        adapter_key="pi-sdk",
        resume=True,
        steer=True,
        native_tools=True,
        tool_calls=True,
        input_requests=True,
        approvals=True,
        event_ack=True,
    )
    return await service.publish_runtime_profile(
        tenant_id=tenant_id,
        profile_key="runtime.pi.readonly.v1",
        runtime_kind="pi",
        adapter_key="pi-sdk",
        config_digest=snapshot_digest(
            {"profile_key": "runtime.pi.readonly.v1", "schema_version": 1}
        ),
        capability_snapshot=capabilities,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_direct_rag_bootstrap_is_tenant_scoped_and_idempotent(db_session):
    service = ExecutionIdentityService(db_session)
    first = await service.bootstrap_direct_rag(tenant_id=TENANT_A, actor_id=ACTOR)
    replay = await service.bootstrap_direct_rag(tenant_id=TENANT_A, actor_id=ACTOR)
    other = await service.bootstrap_direct_rag(tenant_id=TENANT_B, actor_id=ACTOR)

    assert first.agent_definition_version.id == replay.agent_definition_version.id
    assert first.agent_definition_version.versioned_key == "system.direct_rag.v1"
    assert first.runtime_profile.id == replay.runtime_profile.id
    assert first.runtime_profile.profile_key == DIRECT_RAG_PROFILE_KEY
    assert first.runtime_profile.capability_digest == snapshot_digest(
        DIRECT_RAG_CAPABILITIES
    )
    assert other.agent_definition_version.id != first.agent_definition_version.id
    assert other.runtime_profile.id != first.runtime_profile.id


@pytest.mark.asyncio
async def test_catalog_replay_with_different_digest_fails_closed(db_session):
    service = ExecutionIdentityService(db_session)
    await service.bootstrap_direct_rag(tenant_id=TENANT_A, actor_id=ACTOR)
    with pytest.raises(CatalogConflictError):
        await service._repository.publish_runtime_profile(
            tenant_id=TENANT_A,
            profile_key=DIRECT_RAG_PROFILE_KEY,
            runtime_kind="compatibility",
            adapter_key="direct_rag",
            config_digest="f" * 64,
            capability_digest=snapshot_digest(DIRECT_RAG_CAPABILITIES),
            enabled=True,
        )


@pytest.mark.asyncio
async def test_database_guards_published_catalog_digests(db_session):
    service = ExecutionIdentityService(db_session)
    identity = await service.bootstrap_direct_rag(tenant_id=TENANT_A, actor_id=ACTOR)

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(AgentDefinitionVersionModel)
                .where(
                    AgentDefinitionVersionModel.tenant_id == TENANT_A,
                    AgentDefinitionVersionModel.id
                    == identity.agent_definition_version.id,
                )
                .values(definition_digest="f" * 64)
            )
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                update(RuntimeProfileModel)
                .where(
                    RuntimeProfileModel.tenant_id == TENANT_A,
                    RuntimeProfileModel.id == identity.runtime_profile.id,
                )
                .values(capability_digest="f" * 64)
            )


@pytest.mark.asyncio
async def test_compatibility_profile_never_creates_runtime_binding(db_session):
    service = ExecutionIdentityService(db_session)
    identity = await service.bootstrap_direct_rag(tenant_id=TENANT_A, actor_id=ACTOR)
    with pytest.raises(CatalogConflictError, match="do not create"):
        await service.create_runtime_binding(
            tenant_id=TENANT_A,
            conversation_id=uuid.uuid4(),
            runtime_profile_id=identity.runtime_profile.id,
        )
    now = datetime.now(UTC)
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await AgentExecutionIdentityRepository(db_session).create_runtime_binding(
                RuntimeSessionBinding(
                    id=uuid.uuid4(),
                    tenant_id=TENANT_A,
                    conversation_id=uuid.uuid4(),
                    runtime_profile_id=identity.runtime_profile.id,
                    runtime_session_ref="must-not-persist",
                    status=RuntimeBindingStatus.ACTIVE,
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


@pytest.mark.asyncio
async def test_binding_stream_lease_and_cursor_are_fenced(db_session):
    service = ExecutionIdentityService(db_session)
    profile = await _native_profile(service, TENANT_A)
    binding = await service.create_runtime_binding(
        tenant_id=TENANT_A,
        conversation_id=uuid.uuid4(),
        runtime_profile_id=profile.id,
    )
    assert binding.status is RuntimeBindingStatus.CREATING
    binding = await service.activate_runtime_binding(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_session_ref="pi-session-1",
        expected_revision=1,
    )
    assert binding.status is RuntimeBindingStatus.ACTIVE
    assert binding.current_epoch == 1

    stream_a = uuid.uuid4()
    claimed = await service.claim_ingest_stream(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_profile_id=profile.id,
        runtime_epoch=1,
        stream_id=stream_a,
        lease_seconds=30,
    )
    with pytest.raises(RuntimeStreamLeaseConflictError):
        await service.claim_ingest_stream(
            tenant_id=TENANT_A,
            binding_id=binding.id,
            runtime_profile_id=profile.id,
            runtime_epoch=1,
            stream_id=uuid.uuid4(),
            lease_seconds=30,
        )
    assert claimed.next_expected_runtime_seq == 1
    assert claimed.acked_through_runtime_seq == 0
    with pytest.raises(RuntimeEpochMismatchError):
        await service.claim_ingest_stream(
            tenant_id=TENANT_A,
            binding_id=binding.id,
            runtime_profile_id=profile.id,
            runtime_epoch=2,
            stream_id=uuid.uuid4(),
            lease_seconds=30,
        )


@pytest.mark.asyncio
async def test_expired_stream_lease_can_be_taken_over_and_tenant_is_required(db_session):
    service = ExecutionIdentityService(db_session)
    profile = await _native_profile(service, TENANT_A)
    binding = await service.create_runtime_binding(
        tenant_id=TENANT_A,
        conversation_id=uuid.uuid4(),
        runtime_profile_id=profile.id,
    )
    binding = await service.activate_runtime_binding(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_session_ref="pi-session-2",
        expected_revision=1,
    )
    await service.claim_ingest_stream(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_profile_id=profile.id,
        runtime_epoch=1,
        stream_id=uuid.uuid4(),
        lease_seconds=5,
    )
    await db_session.execute(
        update(RuntimeSessionBindingModel)
        .where(
            RuntimeSessionBindingModel.tenant_id == TENANT_A,
            RuntimeSessionBindingModel.id == binding.id,
        )
        .values(stream_lease_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    await db_session.flush()
    takeover = await service.claim_ingest_stream(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_profile_id=profile.id,
        runtime_epoch=1,
        stream_id=uuid.uuid4(),
        lease_seconds=30,
    )
    assert takeover.active_stream_id is not None

    with pytest.raises(RuntimeBindingNotFoundError):
        await service.claim_ingest_stream(
            tenant_id=TENANT_B,
            binding_id=binding.id,
            runtime_profile_id=profile.id,
            runtime_epoch=1,
            stream_id=uuid.uuid4(),
            lease_seconds=30,
        )


@pytest.mark.asyncio
async def test_two_database_sessions_allow_only_one_live_ingest_stream(db_session):
    service = ExecutionIdentityService(db_session)
    profile = await _native_profile(service, TENANT_A)
    binding = await service.create_runtime_binding(
        tenant_id=TENANT_A,
        conversation_id=uuid.uuid4(),
        runtime_profile_id=profile.id,
    )
    binding = await service.activate_runtime_binding(
        tenant_id=TENANT_A,
        binding_id=binding.id,
        runtime_session_ref="pi-session-concurrent",
        expected_revision=1,
    )
    await db_session.commit()

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async def claim(stream_id: uuid.UUID):
        async with factory() as session:
            try:
                claimed = await ExecutionIdentityService(session).claim_ingest_stream(
                    tenant_id=TENANT_A,
                    binding_id=binding.id,
                    runtime_profile_id=profile.id,
                    runtime_epoch=1,
                    stream_id=stream_id,
                    lease_seconds=30,
                )
                await session.commit()
                return claimed
            except Exception as exc:
                await session.rollback()
                return exc

    try:
        results = await asyncio.gather(claim(uuid.uuid4()), claim(uuid.uuid4()))
    finally:
        await engine.dispose()
    assert sum(isinstance(result, RuntimeSessionBinding) for result in results) == 1
    assert sum(
        isinstance(result, RuntimeStreamLeaseConflictError) for result in results
    ) == 1


def test_binding_resume_lifecycle_is_not_exposed_without_run_owner():
    assert not hasattr(ExecutionIdentityService, "mark_runtime_binding_resume_required")
    assert not hasattr(ExecutionIdentityService, "start_new_runtime_epoch")
