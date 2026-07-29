"""R1-S2 S2-D/E：workspace.core.v1 participant 正文清除 + final body scan + ACK。

Spec §3/§5.2/§6.1/§7.1（plan §R1-S2「S2-D/E 契约注记」2026-07-29）：

- purge 前置（Spec §3）：仅作用于已删除（state=deleted）、恢复窗口已过
  （now >= purge_after）、尚未 purged（purged_at IS NULL）的会话。执行器无
  条件强制，不依赖 scheduler 只 claim 到期行（P1-1）。
- 清除锁序与 writer/backfill 一致（Conversation row -> owner lock -> fence），
  防 AB-BA；fence 缺失在 owner lock 下创建（不把缺行解释为安全）。
- participant 在同一事务清除 Conversation title（tombstone）、Message 正文
  （物理删除 MessagePart 行 + Message 转 redacted tombstone）、所有直接主体
  标识（created_by/archived_by/deleted_by 与 Message.author_id）不可逆匿名化
  （HMAC-SHA256 tenant-scoped digest，不留真实 UUID，P1-2/P1-3）、
  ConversationUserState（物理删除），可重入幂等。
- final body scan 是完成门禁：present 正文行/残留 Part/残留 UserState/未匿名
  actor 全为 0 才允许 ACK；扫描非零 -> fence erasing->blocked + operation/
  checkpoint 记 blocked + 稳定 reason code，**作为正常返回**提交（不抛异常致
  回滚丢 blocked 状态，P1-5），不把受影响行数当完成。
- 重试（P1-5）：fence blocked -> erasing 重新进入，清除幂等（已 redacted/已
  删除 no-op），重新 scan；scan 归零即 ACK。
- 仅 body scan 为零才提交 ACK：fence erasing->erased（ack_digest）、owner
  checkpoint 经具体 operation CAS -> acked（绑定 purge_operation_id + registry
  drift 校验，P1-4）。本 Slice 只接 workspace.core.v1 单 owner；多 owner 的
  operation completed 判定属 S3/S4，不伪造 purge_state=completed。

本模块组合既有 ``AgentErasureRepository``（锁序/fence CAS/operation/owner
checkpoint），只新增正文清除与 body scan，不复制 fence/锁逻辑，也不撑大
``erasure_repository.py``（td-032）。redacted_reason 走受控白名单，自由文本
（可能含正文/prompt/secret）不落库。
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    registry_digest,
    require_owner,
)
from app.config import settings
from app.contexts.agent_workspace.domain import (
    ConversationNotPurgeableError,
    ConversationState,
    ConversationTitleSource,
    ErasureFence,
    ErasureFenceState,
    PurgeOperationState,
    PurgeOwnerState,
    PurgeState,
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
# active legal hold 阻止 purge 时的稳定 reason code（retryable--hold 释放后重试）。
REASON_LEGAL_HOLD_ACTIVE = "legal_hold_active"

# Message 转 redacted tombstone 时落的受控 reason（Spec §7.1 purge 到期清除）。
# 用 suppression_reason_code 白名单里的 retention_expired，自由文本不落库。
_ERASURE_REDACTED_REASON = "retention_expired"


def _actor_audit_digest(
    *, secret: str, tenant_id: uuid.UUID, actor_id: uuid.UUID
) -> str:
    """tenant-scoped 不可逆 actor audit digest（Spec §7.1，P1-2：HMAC）。

    用 HMAC-SHA256，不用普通 SHA-256：先从 master secret 派生 tenant-scoped
    key（``HMAC(secret, tenant_id)``），再 ``HMAC(tenant_key, actor_id)``。digest
    不含 actor UUID 明文、不可逆；不同 tenant 同一 actor 产生不同 digest
    （tenant-scoped）；同一 (secret, tenant, actor) 可复现。CHECK 要求 64-hex。
    """
    tenant_key = hmac.new(
        secret.encode("utf-8"), tenant_id.bytes, hashlib.sha256
    ).digest()
    return hmac.new(tenant_key, actor_id.bytes, hashlib.sha256).hexdigest()


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

    def digest(self) -> str:
        """body scan 的 canonical digest（owner checkpoint 的 checkpoint_digest，
        证明 ACK 时 scan 为零的具体度量，与 ack_digest 分离）。"""
        return canonical_digest(
            {
                "schema_version": 1,
                "present_body_messages": self.present_body_messages,
                "message_parts": self.message_parts,
                "user_states": self.user_states,
                "unanonymized_actors": self.unanonymized_actors,
            }
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


@dataclass(frozen=True, slots=True)
class WorkspaceErasureOutcome:
    """erase_conversation_body 的结果（P1-5：blocked 为正常返回，不抛异常）。

    - ``erased``：fence 已 erased、ACK 已提交（ack_digest 非空）。
    - ``blocked``：scan 非零或 active legal hold；fence 为 erasing/blocked/active，
      operation/checkpoint 记 blocked + 稳定 reason code，调用方正常 commit 后
      可重试（hold 释放或残留正文被处理）。
    """

    fence: ErasureFence
    body_scan: WorkspaceBodyScan
    blocked: bool
    block_reason: str | None
    ack_digest: str | None

    @property
    def erased(self) -> bool:
        return not self.blocked and self.fence.state is ErasureFenceState.ERASED


class WorkspaceErasureParticipant:
    """workspace.core.v1 participant：清除正文 + body scan + ACK（S2-D/E）。"""

    def __init__(
        self,
        session: AsyncSession,
        *,
        audit_secret: str | None = None,
    ) -> None:
        self._session = session
        self._erasure = AgentErasureRepository(session)
        # HMAC 密钥走 settings.jwt_secret 回退（与 cursor_secret 同模式）；可注入
        # 测试值。tenant-scoped 派生在 _actor_audit_digest 内完成。
        self._audit_secret = (
            audit_secret if audit_secret is not None else settings.jwt_secret
        )

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
        purge_operation_id: uuid.UUID | None = None,
    ) -> WorkspaceErasureOutcome:
        """清除 workspace.core.v1 正文并 ACK（S2-D/E 主入口，同一事务）。

        锁序（Spec §6.1）：Conversation row FOR UPDATE -> owner lock -> fence
        FOR UPDATE -> owner aggregate rows。purge 前置强制 state=deleted +
        now>=purge_after + purged_at IS NULL（P1-1）。active legal hold ->
        blocked 返回（不清除）。fence 已 erased -> 幂等返回。body scan 非零 ->
        fence erasing->blocked + operation/checkpoint 记 blocked（正常返回，不
        抛异常，P1-5）。scan 为零 -> fence erasing->erased + owner checkpoint
        CAS acked（绑定 purge_operation_id + registry drift 校验，P1-4）。
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
        # P1-1：purge 前置无条件强制。active/archived 或未到期会话不得擦除。
        self._require_purgeable(conversation, now=effective_now)

        # 锁序第二步：owner advisory lock。
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
        )
        # 锁内探测 fence：已 erased -> 幂等返回；缺失 -> owner lock 下建。
        fence = await self._erasure.get_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
        )
        if fence is None:
            fence, _ = await self._erasure.ensure_fence_under_owner_lock(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=WORKSPACE_CORE_OWNER,
            )
        if fence.state is ErasureFenceState.ERASED:
            scan = await self.scan_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            return WorkspaceErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=False,
                block_reason=None,
                ack_digest=fence.ack_digest,
            )

        # active legal hold 阻止 active -> erasing（Spec §5.3），不清除任何正文。
        # 作为 blocked 正常返回（retryable：hold 释放后重试），不抛异常。
        if await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                reason=REASON_LEGAL_HOLD_ACTIVE,
                now=effective_now,
            )
            scan = await self.scan_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            return WorkspaceErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_LEGAL_HOLD_ACTIVE,
                ack_digest=None,
            )

        # 推进 fence -> erasing（首写 active->erasing；重试 blocked->erasing；
        # crash 恢复 erasing 继续）。fencing token 单调；重试复用同 purge_revision。
        if fence.state is ErasureFenceState.ACTIVE:
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
        elif fence.state is ErasureFenceState.BLOCKED:
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=WORKSPACE_CORE_OWNER,
                expected_state=ErasureFenceState.BLOCKED,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.ERASING,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
                now=effective_now,
            )
        # purge_state 投影与 operation/owner 行同事务保持一致（Spec §5.2）。
        conversation.purge_state = PurgeState.RUNNING.value
        conversation.updated_at = effective_now

        # 锁序第四步：owner aggregate rows（Conversation -> Message -> Part ->
        # UserState）清除正文（幂等：已 redacted/已删除/已匿名 no-op）。
        titles_cleared = self._erase_conversation_title(conversation, now=effective_now)
        conversations_anonymized = self._anonymize_conversation_actors(
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

        # final body scan（完成门禁）。
        scan = await self.scan_body(
            tenant_id=tenant_id, conversation_id=conversation_id
        )
        if scan.total != 0:
            # 非零 -> fence erasing->blocked + operation/checkpoint 记 blocked。
            # 正常返回（不抛异常），调用方 commit 后可重试（P1-5）。
            fence = await self._erasure.transition_fence_state(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                owner_key=WORKSPACE_CORE_OWNER,
                expected_state=ErasureFenceState.ERASING,
                expected_revision=fence.revision,
                new_state=ErasureFenceState.BLOCKED,
                purge_revision=purge_revision,
                hold_revision=conversation.hold_revision,
                now=effective_now,
            )
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                reason=REASON_WORKSPACE_BODY_SCAN_NONZERO,
                now=effective_now,
            )
            conversation.purge_state = PurgeState.BLOCKED.value
            conversation.updated_at = effective_now
            return WorkspaceErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_WORKSPACE_BODY_SCAN_NONZERO,
                ack_digest=None,
            )

        # body scan 为零 -> ACK：fence erasing -> erased（ack_digest），owner
        # checkpoint 经具体 operation CAS -> acked（P1-4）。ack_digest 只含清除
        # 摘要 + scan digest，无正文/actor 明文。
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
        ack_digest = summary.ack_digest()
        fence = await self._erasure.transition_fence_state(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
            expected_state=ErasureFenceState.ERASING,
            expected_revision=fence.revision,
            new_state=ErasureFenceState.ERASED,
            purge_revision=purge_revision,
            hold_revision=conversation.hold_revision,
            ack_digest=ack_digest,
            now=effective_now,
        )
        if purge_operation_id is not None:
            await self._ack_owner_checkpoint(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                purge_revision=purge_revision,
                ack_digest=ack_digest,
                checkpoint_digest=scan.digest(),
                now=effective_now,
            )
        # 单 owner ACK 不写 purge_state=completed（多 owner 完成判定属 S3/S4，
        # 不伪造）；保持 running，由 operation/owner 行承载 saga 事实。
        return WorkspaceErasureOutcome(
            fence=fence,
            body_scan=scan,
            blocked=False,
            block_reason=None,
            ack_digest=ack_digest,
        )

    # --- 前置校验 --------------------------------------------------------

    @staticmethod
    def _require_purgeable(
        conversation: ConversationModel, *, now: datetime
    ) -> None:
        """P1-1：purge 前置--state=deleted + now>=purge_after + purged_at IS NULL。"""
        if conversation.state != ConversationState.DELETED.value:
            raise ConversationNotPurgeableError(
                f"conversation state is {conversation.state!r}; "
                "only deleted conversations can be purged"
            )
        if conversation.purged_at is not None:
            raise ConversationNotPurgeableError(
                "conversation is already purged; cannot re-purge"
            )
        if conversation.purge_after is None or now < conversation.purge_after:
            raise ConversationNotPurgeableError(
                "recovery window has not expired; cannot purge before purge_after"
            )

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

    def _anonymize_conversation_actors(
        self, conversation: ConversationModel, *, tenant_id: uuid.UUID
    ) -> int:
        """Conversation 所有直接主体标识不可逆匿名化（P1-3）。

        - created_by -> NULL + creator_identity_digest（HMAC tenant-scoped）。
        - archived_by / deleted_by -> NULL（直接主体标识，Spec §7.1；无独立
          digest 列，V1 仅清除，删除/归档审计在事件账本，非会话行）。
        幂等：已 redacted/已 NULL no-op。
        """
        cleared = 0
        if conversation.actor_state != "redacted":
            created_by = conversation.created_by
            if created_by is not None:
                conversation.actor_state = "redacted"
                conversation.created_by = None
                conversation.creator_identity_digest = _actor_audit_digest(
                    secret=self._audit_secret,
                    tenant_id=tenant_id,
                    actor_id=created_by,
                )
                cleared += 1
        # archived_by / deleted_by 是直接主体标识，purge 时必须清除。
        if conversation.archived_by is not None:
            conversation.archived_by = None
            cleared += 1
        if conversation.deleted_by is not None:
            conversation.deleted_by = None
            cleared += 1
        return cleared

    async def _redact_messages(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, now: datetime
    ) -> int:
        """Message 转 redacted tombstone + author 匿名化（per-row 取旧 author_id）。

        只对 body_state='present' 的 Message 生效（幂等：已 redacted 不动）。
        author_id 置 NULL 前用其值生成 tenant-scoped HMAC digest；assistant_output
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
                    secret=self._audit_secret,
                    tenant_id=tenant_id,
                    actor_id=author_id,
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

    # --- purge operation/owner checkpoint 推进（P1-4/P1-5）-------------

    async def _record_blocked(
        self,
        *,
        purge_operation_id: uuid.UUID | None,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        reason: str,
        now: datetime,
    ) -> None:
        """记 blocked：operation + owner checkpoint 经 CAS 推进 blocked + 稳定
        reason code（P1-5：正常返回路径调用，随调用方事务 commit）。

        无 purge_operation_id（直接调用）时为空操作--fence 状态（erasing/blocked）
        已是安全记录，不阻塞 fail-closed 语义。有 operation 时用 state 谓词 CAS，
        不 clobber 已 completed/cancelled/failed 的行（P2：CAS 安全）。
        """
        if purge_operation_id is None:
            return
        operation = (
            (
                await self._session.execute(
                    select(PurgeOperationModel)
                    .where(
                        PurgeOperationModel.tenant_id == tenant_id,
                        PurgeOperationModel.id == purge_operation_id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if operation is None or operation.purge_revision != purge_revision:
            return
        if operation.state in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.RUNNING.value,
        ):
            operation.state = PurgeOperationState.BLOCKED.value
            operation.failure_code = reason
            operation.updated_at = now
        checkpoint = (
            (
                await self._session.execute(
                    select(PurgeOwnerCheckpointModel)
                    .where(
                        PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                        PurgeOwnerCheckpointModel.purge_operation_id
                        == purge_operation_id,
                        PurgeOwnerCheckpointModel.owner_key == WORKSPACE_CORE_OWNER,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if checkpoint is not None and checkpoint.state in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.ERASING.value,
        ):
            checkpoint.state = PurgeOwnerState.BLOCKED.value
            checkpoint.reason_code = reason
            checkpoint.updated_at = now
        await self._session.flush()

    async def _ack_owner_checkpoint(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        purge_revision: int,
        ack_digest: str,
        checkpoint_digest: str,
        now: datetime,
    ) -> None:
        """ACK owner checkpoint（P1-4：绑定具体 operation + registry drift 校验 + CAS）。

        - 加载具体 operation FOR UPDATE，校验 purge_revision 一致 + registry
          digest 仍匹配已安装 registry（drift -> fail closed，不基于过期能力
          视图 ACK）。
        - 加载具体 owner checkpoint FOR UPDATE，CAS state（pending/erasing ->
          acked），落 ack_digest + checkpoint_digest（scan digest，与 ack_digest
          分离）。
        """
        operation = (
            (
                await self._session.execute(
                    select(PurgeOperationModel)
                    .where(
                        PurgeOperationModel.tenant_id == tenant_id,
                        PurgeOperationModel.id == purge_operation_id,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if operation is None:
            raise ValueError(
                f"purge operation {purge_operation_id} not found; cannot ACK"
            )
        if operation.purge_revision != purge_revision:
            raise ValueError(
                f"purge_revision mismatch: operation={operation.purge_revision} "
                f"ack_request={purge_revision}"
            )
        if operation.registry_digest != registry_digest():
            raise OwnerRegistryChangedError(
                "purge operation registry digest no longer matches installed "
                "registry; cannot ACK on stale capability view"
            )
        checkpoint = (
            (
                await self._session.execute(
                    select(PurgeOwnerCheckpointModel)
                    .where(
                        PurgeOwnerCheckpointModel.tenant_id == tenant_id,
                        PurgeOwnerCheckpointModel.purge_operation_id
                        == purge_operation_id,
                        PurgeOwnerCheckpointModel.owner_key == WORKSPACE_CORE_OWNER,
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .one_or_none()
        )
        if checkpoint is None:
            raise ValueError(
                f"workspace owner checkpoint for operation {purge_operation_id} "
                "not found; cannot ACK"
            )
        if checkpoint.state not in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.ERASING.value,
            PurgeOwnerState.BLOCKED.value,
        ):
            raise ValueError(
                f"owner checkpoint not ackable from state {checkpoint.state!r}"
            )
        checkpoint.state = PurgeOwnerState.ACKED.value
        checkpoint.ack_digest = ack_digest
        checkpoint.checkpoint_digest = checkpoint_digest
        checkpoint.reason_code = None
        checkpoint.updated_at = now
        await self._session.flush()


__all__ = [
    "REASON_LEGAL_HOLD_ACTIVE",
    "REASON_WORKSPACE_BODY_SCAN_NONZERO",
    "WORKSPACE_CORE_OWNER",
    "WorkspaceBodyScan",
    "WorkspaceErasureOutcome",
    "WorkspaceErasureParticipant",
    "WorkspaceErasureSummary",
]
