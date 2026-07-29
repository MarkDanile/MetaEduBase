"""R1-S2 S2-D/E：workspace.core.v1 participant 正文清除 + final body scan + ACK。

Spec §5.2/§6.1/§7.1（plan §R1-S2「S2-D/E 契约注记」2026-07-29）：

- 清除锁序与 writer/backfill 一致（Conversation row -> owner lock -> fence），
  防 AB-BA；fence 缺失在 owner lock 下创建（不把缺行解释为安全）。
- participant 在同一事务清除 Conversation title（tombstone）、Message 正文
  （物理删除 MessagePart 行 + Message 转 redacted tombstone）、actor 不可逆
  匿名化（存 tenant-scoped digest，不留真实 UUID）、ConversationUserState
  （物理删除），可重入幂等。
- 清除后必须 final body scan：present 正文行/残留 Part/残留 UserState/未匿名
  actor 全为 0 才允许 ACK；扫描非零 -> 记 blocked + 稳定 reason code，不把
  「受影响行数」当完成（没有查到正文不是隐式 ACK 的反面）。
- 仅 body scan 为零才提交 ACK：fence erasing->erased（ack_digest）、owner
  checkpoint -> acked。本 Slice 只接 workspace.core.v1 单 owner；多 owner 的
  operation completed 判定属 S3/S4，不伪造。

本模块组合既有 ``AgentErasureRepository``（锁序/fence CAS/operation/owner
checkpoint），只新增正文清除与 body scan，不复制 fence/锁逻辑，也不撑大
``erasure_repository.py``（td-032）。redacted_reason 走受控
``suppression_reason_code``，自由文本（可能含正文/prompt/secret）不落库。
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import require_owner
from app.contexts.agent_workspace.domain import (
    ConversationTitleSource,
    ErasureFence,
    ErasureFenceState,
    PurgeOwnerState,
    WorkspaceBodyScanNonZeroError,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ConversationUserStateModel,
    MessageModel,
    MessagePartModel,
    PurgeOperationModel,
    PurgeOwnerCheckpointModel,
)
from app.shared.schemas.canonical_json import canonical_digest

# workspace.core.v1 owner key（Spec §4，唯一受管 workspace 正文 owner）。
WORKSPACE_CORE_OWNER = "workspace.core.v1"

# body scan 非零时的稳定 reason code（Spec §5.2 owner checkpoint reason_code，
# 受控枚举、不含正文）。与 suppression_reason_code 同受控原则：不反射自由文本。
REASON_WORKSPACE_BODY_SCAN_NONZERO = "workspace_body_scan_nonzero"

# Message 转 redacted tombstone 时落的受控 reason（Spec §7.1 purge 到期清除）。
# 用 suppression_reason_code 白名单里的 retention_expired，自由文本不落库。
_ERASURE_REDACTED_REASON = "retention_expired"


def _actor_audit_digest(*, tenant_id: uuid.UUID, actor_id: uuid.UUID) -> str:
    """tenant-scoped 不可逆 actor audit digest（Spec §7.1）。

    只存 digest、不留可还原明文；不同 tenant 同一 actor 产生不同 digest
    （tenant-scoped），digest 不含 actor UUID 明文。CHECK 要求 64-hex。
    """
    return hashlib.sha256(
        b"actor-audit\x00" + tenant_id.bytes + b"\x00" + actor_id.bytes
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkspaceBodyScan:
    """final workspace body scan 结果（Spec §7.1 完成门禁输入）。"""

    present_body_messages: int
    message_parts: int
    user_states: int
    unanonymized_actors: int

    @property
    def total(self) -> int:
        return (
            self.present_body_messages
            + self.message_parts
            + self.user_states
            + self.unanonymized_actors
        )


@dataclass(frozen=True, slots=True)
class WorkspaceErasureSummary:
    """单 owner 清除 + ACK 摘要（ACK digest 的 canonical 输入，不含正文）。"""

    owner_key: str
    owner_version: int
    purge_revision: int
    titles_cleared: int
    conversations_anonymized: int
    messages_redacted: int
    message_parts_deleted: int
    user_states_deleted: int
    body_scan: WorkspaceBodyScan

    def ack_digest(self) -> str:
        """ACK digest = 排序清除摘要 + body scan 的 canonical digest（无正文）。"""
        return canonical_digest(
            {
                "schema_version": 1,
                "owner_key": self.owner_key,
                "owner_version": self.owner_version,
                "purge_revision": self.purge_revision,
                "titles_cleared": self.titles_cleared,
                "conversations_anonymized": self.conversations_anonymized,
                "messages_redacted": self.messages_redacted,
                "message_parts_deleted": self.message_parts_deleted,
                "user_states_deleted": self.user_states_deleted,
                "body_scan": {
                    "present_body_messages": self.body_scan.present_body_messages,
                    "message_parts": self.body_scan.message_parts,
                    "user_states": self.body_scan.user_states,
                    "unanonymized_actors": self.body_scan.unanonymized_actors,
                },
            }
        )


class WorkspaceErasureParticipant:
    """workspace.core.v1 participant：清除正文 + body scan + ACK（S2-D/E）。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)

    async def scan_body(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> WorkspaceBodyScan:
        """final workspace body scan：统计该 Conversation 下残留正文/未匿名 actor。"""
        present_body = await self._session.scalar(
            select(func.count())
            .select_from(MessageModel)
            .where(
                MessageModel.tenant_id == tenant_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.body_state == "present",
            )
        )
        parts = await self._session.scalar(
            select(func.count())
            .select_from(MessagePartModel)
            .join(MessageModel, MessagePartModel.message_id == MessageModel.id)
            .where(
                MessagePartModel.tenant_id == tenant_id,
                MessageModel.conversation_id == conversation_id,
            )
        )
        user_states = await self._session.scalar(
            select(func.count())
            .select_from(ConversationUserStateModel)
            .where(
                ConversationUserStateModel.tenant_id == tenant_id,
                ConversationUserStateModel.conversation_id == conversation_id,
            )
        )
        unanonymized = await self._session.scalar(
            select(func.count())
            .select_from(MessageModel)
            .where(
                MessageModel.tenant_id == tenant_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.author_id.is_not(None),
            )
        )
        conversation = await self._session.get(ConversationModel, conversation_id)
        conversation_actor = (
            1
            if conversation is not None and conversation.actor_state == "present"
            else 0
        )
        return WorkspaceBodyScan(
            present_body_messages=int(present_body or 0),
            message_parts=int(parts or 0),
            user_states=int(user_states or 0),
            unanonymized_actors=int(unanonymized or 0) + conversation_actor,
        )

    async def erase_conversation_body(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        now: datetime | None = None,
    ) -> ErasureFence:
        """清除 workspace.core.v1 正文并 ACK（S2-D/E 主入口，同一事务）。

        锁序（Spec §6.1）：Conversation row FOR UPDATE -> owner lock -> fence
        FOR UPDATE -> owner aggregate rows。active legal hold 阻止进入 erasing。
        fence 已 erased -> 幂等返回。body scan 非零 -> 记 blocked + 稳定
        reason code 并 fail closed（不 ACK）。
        """
        require_owner(WORKSPACE_CORE_OWNER)
        effective_now = now or datetime.now(UTC)

        # 锁序第一步：Conversation 行锁（与 writer/backfill 一致，防 AB-BA）。
        conversation = (
            await self._session.execute(
                select(ConversationModel)
                .where(
                    ConversationModel.tenant_id == tenant_id,
                    ConversationModel.id == conversation_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ValueError(
                f"conversation {conversation_id} not found for workspace erasure"
            )
        # 锁序第二步：owner advisory lock。
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
        )
        # 锁内探测 fence：已 erased -> 幂等返回（重放不二次清除、不改 ack）；
        # 缺失 -> owner lock 下建；active/erasing/blocked -> 继续清除流程。
        fence = await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
        )
        if fence is not None and fence.state is ErasureFenceState.ERASED:
            return fence
        if fence is None:
            fence, _ = await self._erasure.ensure_fence_under_owner_lock(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=WORKSPACE_CORE_OWNER,
            )

        # active legal hold 阻止 active -> erasing（Spec §5.3），不清除任何正文。
        if await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            raise WorkspaceBodyScanNonZeroError(
                "active legal hold blocks workspace erasure; body retained"
            )

        # 推进 fence active -> erasing（fencing token 单调；重试复用同 token）。
        fence = await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
            expected_state=ErasureFenceState.ACTIVE,
            expected_revision=fence.revision,
            new_state=ErasureFenceState.ERASING,
            purge_revision=purge_revision,
            hold_revision=conversation.hold_revision,
            now=effective_now,
        )

        # 锁序第四步：owner aggregate rows（Conversation -> Message -> Part ->
        # UserState）清除正文。
        titles_cleared = self._erase_conversation_title(conversation, now=effective_now)
        conversations_anonymized = self._anonymize_conversation_actor(
            conversation, tenant_id=tenant_id
        )
        messages_redacted = await self._redact_messages(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            now=effective_now,
        )
        message_parts_deleted = await self._delete_message_parts(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        user_states_deleted = await self._delete_user_states(
            tenant_id=tenant_id, conversation_id=conversation_id
        )

        # final body scan（完成门禁）：非零 -> blocked + 稳定 reason code，不 ACK。
        scan = await self.scan_body(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        if scan.total != 0:
            await self._record_blocked(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                now=effective_now,
            )
            raise WorkspaceBodyScanNonZeroError(
                f"workspace body scan non-zero after erasure: {scan!r}"
            )

        # body scan 为零 -> ACK：fence erasing -> erased（ack_digest），owner
        # checkpoint -> acked。ack_digest 只含排序清除摘要 + scan digest，无正文。
        summary = WorkspaceErasureSummary(
            owner_key=WORKSPACE_CORE_OWNER,
            owner_version=fence.owner_version,
            purge_revision=purge_revision,
            titles_cleared=titles_cleared,
            conversations_anonymized=conversations_anonymized,
            messages_redacted=messages_redacted,
            message_parts_deleted=message_parts_deleted,
            user_states_deleted=user_states_deleted,
            body_scan=scan,
        )
        fence = await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
            expected_state=ErasureFenceState.ERASING,
            expected_revision=fence.revision,
            new_state=ErasureFenceState.ERASED,
            purge_revision=purge_revision,
            hold_revision=conversation.hold_revision,
            ack_digest=summary.ack_digest(),
            now=effective_now,
        )
        await self._ack_owner_checkpoint(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            ack_digest=summary.ack_digest(),
            checkpoint_digest=summary.ack_digest(),
            now=effective_now,
        )
        return fence

    # --- 清除动作（owner aggregate rows，幂等）---------------------------

    def _erase_conversation_title(
        self, conversation: ConversationModel, *, now: datetime
    ) -> int:
        """清 Conversation title（tombstone），保留 envelope；幂等。"""
        if conversation.title is None and (
            conversation.title_source == ConversationTitleSource.NONE.value
        ):
            return 0
        conversation.title = None
        conversation.title_source = ConversationTitleSource.NONE.value
        conversation.updated_at = now
        return 1

    def _anonymize_conversation_actor(
        self, conversation: ConversationModel, *, tenant_id: uuid.UUID
    ) -> int:
        """Conversation actor 不可逆匿名化（created_by->NULL + digest）；幂等。"""
        if conversation.actor_state == "redacted":
            return 0
        created_by = conversation.created_by
        if created_by is None:
            return 0
        conversation.actor_state = "redacted"
        conversation.created_by = None
        conversation.creator_identity_digest = _actor_audit_digest(
            tenant_id=tenant_id, actor_id=created_by
        )
        return 1

    async def _redact_messages(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
    ) -> int:
        """Message 转 redacted tombstone + author 匿名化（per-row 取旧 author_id）。

        只对 body_state='present' 的 Message 生效（幂等：已 redacted 不动）。
        author_id 置 NULL 前用其值生成 tenant-scoped digest；assistant_output
        （agent author）只转 tombstone、不补 digest（非用户主体标识）。
        """
        rows = (
            (
                await self._session.execute(
                    select(MessageModel)
                    .where(
                        MessageModel.tenant_id == tenant_id,
                        MessageModel.conversation_id == conversation_id,
                        MessageModel.body_state == "present",
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for message in rows:
            author_id = message.author_id
            message.body_state = "redacted"
            message.content_state = "redacted"
            message.redacted_at = now
            message.redacted_reason = _ERASURE_REDACTED_REASON
            if author_id is not None and message.author_type == "user":
                message.actor_identity_digest = _actor_audit_digest(
                    tenant_id=tenant_id, actor_id=author_id
                )
            message.author_id = None
        if rows:
            await self._session.flush()
        return len(rows)

    async def _delete_message_parts(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        """物理删除该 Conversation 所有 MessagePart 正文行（V1 不保留 Part envelope）。"""
        result = await self._session.execute(
            delete(MessagePartModel).where(
                MessagePartModel.tenant_id == tenant_id,
                MessagePartModel.message_id.in_(
                    select(MessageModel.id).where(
                        MessageModel.tenant_id == tenant_id,
                        MessageModel.conversation_id == conversation_id,
                    )
                ),
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def _delete_user_states(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> int:
        """物理删除 ConversationUserState（pin/read 非审计必需 envelope，Spec §7.1）。"""
        result = await self._session.execute(
            delete(ConversationUserStateModel).where(
                ConversationUserStateModel.tenant_id == tenant_id,
                ConversationUserStateModel.conversation_id == conversation_id,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    # --- purge operation/owner checkpoint 推进 ---------------------------

    async def _record_blocked(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        now: datetime,
    ) -> None:
        """body scan 非零：把该 (conversation, purge_revision) 的 workspace owner
        checkpoint 记 blocked + 稳定 reason code（operation 一并 blocked）。

        只更新仍处 pending/erasing 的 workspace owner 行；无对应 operation
        （直接调用执行器、未经 scheduler 建 operation）时为空操作，不阻塞
        「fence 保持 erasing、不 ACK」的 fail-closed 语义。
        """
        reason = REASON_WORKSPACE_BODY_SCAN_NONZERO
        owner_rows = (
            (
                await self._session.execute(
                    select(PurgeOwnerCheckpointModel)
                    .join(
                        PurgeOperationModel,
                        PurgeOwnerCheckpointModel.purge_operation_id
                        == PurgeOperationModel.id,
                    )
                    .where(
                        PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                        PurgeOperationModel.conversation_id == conversation_id,
                        PurgeOperationModel.purge_revision == purge_revision,
                        PurgeOwnerCheckpointModel.owner_key == WORKSPACE_CORE_OWNER,
                        PurgeOwnerCheckpointModel.state.in_(
                            (PurgeOwnerState.PENDING.value, PurgeOwnerState.ERASING.value)
                        ),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for owner in owner_rows:
            owner.state = PurgeOwnerState.BLOCKED.value
            owner.reason_code = reason
            owner.updated_at = now
        if owner_rows:
            await self._session.execute(
                update(PurgeOperationModel)
                .where(
                    PurgeOperationModel.tenant_id == tenant_id,
                    PurgeOperationModel.conversation_id == conversation_id,
                    PurgeOperationModel.purge_revision == purge_revision,
                )
                .values(state="blocked", updated_at=now)
                .execution_options(synchronize_session=False)
            )
        await self._session.flush()

    async def _ack_owner_checkpoint(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        ack_digest: str,
        checkpoint_digest: str,
        now: datetime,
    ) -> None:
        """把该 (conversation, purge_revision) 的 workspace owner checkpoint 推进
        acked（带 ack_digest/checkpoint_digest）。无对应 operation 时为空操作
        （执行器可独立调用，不强制经 scheduler 建 operation）。"""
        await self._session.execute(
            update(PurgeOwnerCheckpointModel)
            .where(
                PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                PurgeOwnerCheckpointModel.owner_key == WORKSPACE_CORE_OWNER,
                PurgeOwnerCheckpointModel.state != PurgeOwnerState.ACKED.value,
                PurgeOwnerCheckpointModel.purge_operation_id.in_(
                    select(PurgeOperationModel.id).where(
                        PurgeOperationModel.tenant_id == tenant_id,
                        PurgeOperationModel.conversation_id == conversation_id,
                        PurgeOperationModel.purge_revision == purge_revision,
                    )
                ),
            )
            .values(
                state=PurgeOwnerState.ACKED.value,
                ack_digest=ack_digest,
                checkpoint_digest=checkpoint_digest,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        await self._session.flush()


__all__ = [
    "REASON_WORKSPACE_BODY_SCAN_NONZERO",
    "WORKSPACE_CORE_OWNER",
    "WorkspaceBodyScan",
    "WorkspaceErasureParticipant",
    "WorkspaceErasureSummary",
]
