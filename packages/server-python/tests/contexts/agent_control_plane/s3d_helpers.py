"""R1-S3-D ``ExecutionErasureParticipant`` 测试 seed/helpers。

真实 PostgreSQL（``db_session`` fixture）seed ``AgentRun``/``RunEvent``/
``CompatibilityOutput``/``TurnInput`` 正文 + ``PurgeOperation``/
``PurgeOwnerCheckpoint``，覆盖 Spec §7.2 execution 正文清除全部清除动作与反例。

与 ``test_s2de_workspace_erasure.py`` 同模式（同 ``db_session``/TRUNCATE fixture），
但 seed execution 正文 owner 表（``execution.core.v1``）。直接 ORM 落库以满足
CHECK 约束，不经 ``RunCoordinator`` 生产路径--被测对象是 participant 的 SQL
UPDATE/scan，不是 run 创建链。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import null, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_execution.application.execution_identity_service import (
    CompatibilityIdentity,
    ExecutionIdentityService,
)
from app.contexts.agent_execution.domain import RuntimeCapabilitySnapshot
from app.contexts.agent_execution.domain.snapshots import snapshot_digest
from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
    EXECUTION_CORE_OWNER,
    ExecutionErasureParticipant,
)
from app.contexts.agent_execution.infrastructure.models import (
    AgentRunModel,
    CompatibilityOutputModel,
    RunEventModel,
    TurnInputModel,
)
from app.contexts.agent_workspace.application.conversation_service import (
    AgentWorkspaceService,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.contexts.agent_workspace.infrastructure.repository import (
    AgentWorkspaceRepository,
)
from tests.contexts.agent_control_plane.helpers import ACTOR_ID, TENANT_ID

AUDIT_SECRET = "test-audit-secret"
AUDIT_SECRET_VERSION = 1
_DIGEST = "a" * 64  # 64-hex placeholder digest（满足 char_length=64 CHECK）
_MIME = "text/markdown"  # 满足 ck_agent_run_event_media_type / terminal_output_media_type


# ---------------------------------------------------------------------------
# conversation / identity / purge operation seed
# ---------------------------------------------------------------------------


async def seed_deleted_expired_with_identity(
    db_session: AsyncSession, *, title: str = "sensitive execution body"
) -> tuple[uuid.UUID, CompatibilityIdentity]:
    """建 active 会话 + bootstrap direct-rag identity（agent_definition_version +
    runtime_profile FK 目标），再 soft_delete + purge_after 过期。

    返回 (conversation_id, identity)。delete 推进 purge_revision 0->1。
    """
    service = AgentWorkspaceService(db_session, cursor_secret="test-secret")
    view, _ = await service.create_conversation(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID, title=title
    )
    conversation_id = view.conversation.id
    identity = await ExecutionIdentityService(db_session).bootstrap_direct_rag(
        tenant_id=TENANT_ID, actor_id=ACTOR_ID
    )
    conv = await db_session.get(ConversationModel, conversation_id)
    assert conv is not None
    expired = datetime.now(UTC) - timedelta(days=1)
    deleted_at = datetime.now(UTC) - timedelta(days=31)
    await AgentWorkspaceRepository(db_session).soft_delete_after_guard(
        tenant_id=TENANT_ID,
        actor_id=ACTOR_ID,
        conversation_id=conversation_id,
        expected_revision=conv.revision,
        purge_after=expired,
        deleted_at=deleted_at,
    )
    await db_session.commit()
    return conversation_id, identity


async def make_purge_operation(
    db_session: AsyncSession,
    conversation_id: uuid.UUID,
    purge_revision: int,
    *,
    hold_revision_snapshot: int = 0,
) -> tuple[uuid.UUID, int]:
    """建 scheduled purge operation + pending execution.core.v1 owner checkpoint。

    返回 (operation_id, operation_revision=1)。
    """
    repo = AgentErasureRepository(db_session)
    operation = await repo.create_purge_operation(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        purge_revision=purge_revision,
        retention_policy_snapshot={"conversation_recovery_days": 30},
        hold_revision_snapshot=hold_revision_snapshot,
    )
    await repo.create_owner_checkpoint(
        tenant_id=TENANT_ID,
        purge_operation_id=operation.id,
        owner_key=EXECUTION_CORE_OWNER,
    )
    await db_session.commit()
    return operation.id, operation.revision


async def seed_purgeable(
    db_session: AsyncSession, *, title: str = "sensitive execution body"
) -> tuple[uuid.UUID, CompatibilityIdentity, int]:
    """标准基线：deleted+expired 会话 + identity（无 operation/run）。

    返回 (conversation_id, identity, purge_revision=1)。各测试按需 seed run +
    operation。
    """
    conversation_id, identity = await seed_deleted_expired_with_identity(
        db_session, title=title
    )
    return conversation_id, identity, 1


# ---------------------------------------------------------------------------
# execution body seed（AgentRun / RunEvent / CompatibilityOutput / TurnInput）
# ---------------------------------------------------------------------------


def _capability_dict(identity: CompatibilityIdentity) -> dict:
    return identity.capability_snapshot.model_dump(mode="json")


async def seed_completed_run(
    db_session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    identity: CompatibilityIdentity,
    queue_seq: int = 1,
    runtime_binding_id: uuid.UUID | None = None,
    runtime_profile_id: uuid.UUID | None = None,
    with_context_snapshot: bool = True,
    terminal_code: str = "completed",
    terminal_reason: str = "run finished successfully",
    output_publish_state: str = "published",
    created_by: uuid.UUID = ACTOR_ID,
) -> AgentRunModel:
    """建一个 completed AgentRun（带 terminal output envelope + context snapshot +
    present actor），满足全部 CHECK 约束。

    ``terminal_code/reason`` 默认非受控白名单值（清除时被裁剪为受控 code）。
    """
    now = datetime.now(UTC)
    profile_id = runtime_profile_id or identity.runtime_profile.id
    if with_context_snapshot:
        context_kwargs = dict(
            context_snapshot_ref="obj://context/snapshot",
            context_snapshot_digest=_DIGEST,
            context_snapshot_classification="internal",
        )
    else:
        context_kwargs = dict(
            context_snapshot_ref=None,
            context_snapshot_digest=None,
            context_snapshot_classification=None,
        )
    run = AgentRunModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        queue_seq=queue_seq,
        root_input_message_id=uuid.uuid4(),
        parent_run_id=None,
        agent_definition_version_id=identity.agent_definition_version.id,
        runtime_profile_id=profile_id,
        runtime_binding_id=runtime_binding_id,
        creation_digest=_DIGEST,
        status="completed",
        status_revision=1,
        cancel_requested_revision=None,
        next_event_seq=1,
        first_available_event_seq=1,
        last_event_seq=0,
        event_log_complete=True,
        queued_at=now,
        started_at=now,
        ended_at=now,
        terminal_code=terminal_code,
        terminal_reason=terminal_reason,
        terminal_result_digest=_DIGEST,
        terminal_output_ref="obj://terminal/output",
        terminal_output_digest=_DIGEST,
        terminal_output_size=42,
        terminal_output_media_type=_MIME,
        terminal_output_classification="internal",
        terminal_message_id=uuid.uuid4(),
        output_publish_state=output_publish_state,
        created_by=created_by,
        actor_state="present",
        actor_identity_digest=None,
        correlation_id=uuid.uuid4(),
        runtime_capability_snapshot=_capability_dict(identity),
        run_config_snapshot={
            "agent_definition_version_id": str(identity.agent_definition_version.id),
            "runtime_profile_id": str(profile_id),
        },
        budget_snapshot={},
        usage_summary={},
        **context_kwargs,
    )
    db_session.add(run)
    await db_session.flush()
    return run


async def seed_nonterminal_run(
    db_session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    identity: CompatibilityIdentity,
    queue_seq: int = 1,
    status: str = "running",
) -> AgentRunModel:
    """建一个非终态 AgentRun（running），满足非终态 CHECK 分支（无 terminal 字段，
    output_publish_state=not_required）。"""
    now = datetime.now(UTC)
    run = AgentRunModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        queue_seq=queue_seq,
        root_input_message_id=uuid.uuid4(),
        parent_run_id=None,
        agent_definition_version_id=identity.agent_definition_version.id,
        runtime_profile_id=identity.runtime_profile.id,
        runtime_binding_id=None,
        creation_digest=_DIGEST,
        status=status,
        status_revision=1,
        cancel_requested_revision=None,
        next_event_seq=1,
        first_available_event_seq=1,
        last_event_seq=0,
        event_log_complete=True,
        queued_at=now,
        started_at=now,
        ended_at=None,
        terminal_code=None,
        terminal_reason=None,
        terminal_result_digest=None,
        terminal_output_ref=None,
        terminal_output_digest=None,
        terminal_output_size=None,
        terminal_output_media_type=None,
        terminal_output_classification=None,
        terminal_message_id=None,
        output_publish_state="not_required",
        created_by=ACTOR_ID,
        actor_state="present",
        actor_identity_digest=None,
        correlation_id=uuid.uuid4(),
        runtime_capability_snapshot=_capability_dict(identity),
        run_config_snapshot={
            "agent_definition_version_id": str(identity.agent_definition_version.id),
            "runtime_profile_id": str(identity.runtime_profile.id),
        },
        budget_snapshot={},
        usage_summary={},
        context_snapshot_ref=None,
        context_snapshot_digest=None,
        context_snapshot_classification=None,
    )
    db_session.add(run)
    await db_session.flush()
    return run


async def seed_run_event(
    db_session: AsyncSession,
    *,
    run: AgentRunModel,
    seq: int = 1,
    payload_inline: dict | None = None,
    payload_ref: str | None = None,
    payload_state: str = "inline",
    classification: str = "internal",
    visibility: str = "user",
) -> RunEventModel:
    """建一个 RunEvent（默认 inline payload + body summary）。

    inline 分支：payload_inline 非空 + payload_ref NULL + classification <> restricted
    + payload_size <= 32768。external 分支：payload_inline NULL + payload_ref 非空。
    """
    now = datetime.now(UTC)
    if payload_inline is None and payload_state == "inline":
        payload_inline = {"summary": "sensitive event body to erase"}
    # external/redacted 分支 payload_inline 必须 SQL NULL（非 JSON null）。JSONB
    # ``None`` 会被 SQLAlchemy 序列化为 JSON 'null'，违反 ck_agent_run_event_payload
    # 的 ``payload_inline IS NULL`` 谓词。
    inline_for_insert = payload_inline if payload_inline is not None else null()
    event = RunEventModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=run.conversation_id,
        run_id=run.id,
        seq=seq,
        event_type="run.plan_summary",
        schema_version=1,
        occurred_at=now,
        persisted_at=now,
        visibility=visibility,
        classification=classification,
        payload_inline=inline_for_insert,
        payload_ref=payload_ref,
        payload_state=payload_state,
        payload_digest=_DIGEST,
        payload_size=len(str(payload_inline).encode()) if payload_inline else 0,
        media_type=_MIME,
        expires_at=None,
        runtime_profile_id=None,
        runtime_binding_id=None,
        runtime_epoch=None,
        runtime_seq=None,
        runtime_event_id=None,
        runtime_event_digest=None,
        correlation_id=run.correlation_id,
        causation_id=None,
    )
    db_session.add(event)
    await db_session.flush()
    return event


async def seed_compatibility_output(
    db_session: AsyncSession,
    *,
    run: AgentRunModel,
    reply_text: str = "sensitive compatibility reply body",
    output_ref: str | None = None,
) -> CompatibilityOutputModel:
    """建一个 present CompatibilityOutput（reply_text + response_envelope 非空）。

    CHECK 要求 media_type='text/markdown' + classification='internal'。
    """
    output = CompatibilityOutputModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        conversation_id=run.conversation_id,
        run_id=run.id,
        output_ref=output_ref or f"obj://compat/{uuid.uuid4()}",
        output_digest=_DIGEST,
        response_digest=_DIGEST,
        reply_text=reply_text,
        response_envelope={"role": "assistant", "model": "compat.v1"},
        payload_state="present",
        media_type=_MIME,
        classification="internal",
    )
    db_session.add(output)
    await db_session.flush()
    return output


async def seed_turn_input(
    db_session: AsyncSession,
    *,
    run: AgentRunModel,
    created_by: uuid.UUID = ACTOR_ID,
) -> TurnInputModel:
    """建一个 root TurnInput（ordinal=0 + present actor）。"""
    turn = TurnInputModel(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        run_id=run.id,
        ordinal=0,
        input_kind="root",
        message_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        expected_runtime_epoch=None,
        context_digest=_DIGEST,
        created_by=created_by,
        actor_state="present",
        actor_identity_digest=None,
    )
    db_session.add(turn)
    await db_session.flush()
    return turn


async def seed_native_binding(
    db_session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID]:
    """建一个 pi runtime profile + 激活 binding（runtime_session_ref 非空）。

    用于 runtime binding ref blocked 测试。返回 (profile_id, binding_id)。
    """
    service = ExecutionIdentityService(db_session)
    capabilities = RuntimeCapabilitySnapshot(
        runtime_kind="pi",
        adapter_key="pi-sdk",
        resume=True,
        steer=True,
        native_tools=False,
        tool_calls=False,
        input_requests=False,
        approvals=False,
        event_ack=True,
    )
    profile = await service.publish_runtime_profile(
        tenant_id=TENANT_ID,
        profile_key=f"runtime.pi.s3d.{uuid.uuid4().hex[:8]}",
        runtime_kind="pi",
        adapter_key="pi-sdk",
        config_digest=snapshot_digest(
            {"profile_key": "runtime.pi.s3d", "schema_version": 1}
        ),
        capability_snapshot=capabilities,
        enabled=True,
    )
    binding = await service.create_runtime_binding(
        tenant_id=TENANT_ID,
        conversation_id=conversation_id,
        runtime_profile_id=profile.id,
    )
    binding = await service.activate_runtime_binding(
        tenant_id=TENANT_ID,
        binding_id=binding.id,
        runtime_session_ref=f"pi-s3d-{conversation_id}",
        expected_revision=binding.revision,
    )
    await db_session.commit()
    return profile.id, binding.id


# ---------------------------------------------------------------------------
# 标准 purgeable-with-run 基线（completed run + 全正文 + operation + checkpoint）
# ---------------------------------------------------------------------------


async def seed_purgeable_with_run(
    db_session: AsyncSession, *, title: str = "sensitive execution body"
) -> dict:
    """标准基线：deleted+expired 会话 + identity + completed Run（terminal output +
    context snapshot + present actor）+ RunEvent(inline) + CompatibilityOutput +
    TurnInput + scheduled operation + pending checkpoint。

    返回 dict（conversation_id/identity/purge_revision/operation_id/op_revision/run_id）。
    """
    conversation_id, identity, purge_revision = await seed_purgeable(
        db_session, title=title
    )
    run = await seed_completed_run(
        db_session, conversation_id=conversation_id, identity=identity
    )
    await seed_run_event(db_session, run=run)
    await seed_compatibility_output(db_session, run=run)
    await seed_turn_input(db_session, run=run)
    operation_id, op_revision = await make_purge_operation(
        db_session, conversation_id, purge_revision
    )
    return {
        "conversation_id": conversation_id,
        "identity": identity,
        "purge_revision": purge_revision,
        "operation_id": operation_id,
        "op_revision": op_revision,
        "run_id": run.id,
    }


# ---------------------------------------------------------------------------
# participant + 读回 helpers
# ---------------------------------------------------------------------------


def participant(db_session: AsyncSession) -> ExecutionErasureParticipant:
    return ExecutionErasureParticipant(
        db_session,
        audit_secret=AUDIT_SECRET,
        audit_secret_version=AUDIT_SECRET_VERSION,
    )


async def fence_model(db_session: AsyncSession, conversation_id: uuid.UUID):
    from app.contexts.agent_workspace.infrastructure.models import ErasureFenceModel

    return (
        await db_session.execute(
            select(ErasureFenceModel).where(
                ErasureFenceModel.tenant_id == TENANT_ID,
                ErasureFenceModel.conversation_id == conversation_id,
                ErasureFenceModel.owner_key == EXECUTION_CORE_OWNER,
            )
        )
    ).scalar_one()


async def fence_model_or_none(
    db_session: AsyncSession, conversation_id: uuid.UUID
):
    """I1 drift 零写断言用：失败 entry 先于惰性 fence 建立时返回 None。"""
    from app.contexts.agent_workspace.infrastructure.models import ErasureFenceModel

    return (
        await db_session.execute(
            select(ErasureFenceModel).where(
                ErasureFenceModel.tenant_id == TENANT_ID,
                ErasureFenceModel.conversation_id == conversation_id,
                ErasureFenceModel.owner_key == EXECUTION_CORE_OWNER,
            )
        )
    ).scalar_one_or_none()


async def checkpoint_model(
    db_session: AsyncSession, operation_id: uuid.UUID
) -> PurgeOwnerCheckpointModel:
    return (
        (
            await db_session.execute(
                select(PurgeOwnerCheckpointModel).where(
                    PurgeOwnerCheckpointModel.purge_operation_id == operation_id,
                    PurgeOwnerCheckpointModel.owner_key == EXECUTION_CORE_OWNER,
                )
            )
        )
        .scalars()
        .one()
    )


async def operation_model(
    db_session: AsyncSession, operation_id: uuid.UUID
) -> PurgeOperationModel:
    return (
        (
            await db_session.execute(
                select(PurgeOperationModel).where(
                    PurgeOperationModel.tenant_id == TENANT_ID,
                    PurgeOperationModel.id == operation_id,
                )
            )
        )
        .scalars()
        .one()
    )


async def op_revision(db_session: AsyncSession, operation_id: uuid.UUID) -> int:
    return (await operation_model(db_session, operation_id)).revision


async def run_model(db_session: AsyncSession, run_id: uuid.UUID) -> AgentRunModel:
    return (
        (
            await db_session.execute(
                select(AgentRunModel).where(
                    AgentRunModel.tenant_id == TENANT_ID,
                    AgentRunModel.id == run_id,
                )
            )
        )
        .scalars()
        .one()
    )
