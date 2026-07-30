"""R1-S2 S2-D/E：workspace.core.v1 participant 正文清除 + final body scan + ACK。

Spec §3/§5.2/§6.1/§7.1/§9.2（plan §R1-S2「S2-D/E 契约注记」+「S2-D/E 复审修订」）：

- capability gate（P1-1）：执行器入口经 ``require_capability(workspace.core.v1,
  "erase")`` 放行；registry 已为 workspace.core.v1 翻 ``erase_available=True``。
- purge 前置（Spec §3，P1-1）：仅 state=deleted + now>=purge_after +
  purged_at IS NULL。但**已 erased fence 的幂等重放先于前置**（P1-4：purged_at
  后不得在读 fence 前被拒绝）。
- HMAC secret 隔离（P1-2）：actor audit digest 用独立
  ``actor_erasure_secret``（非 jwt_secret），生产 fail-fast，版本固定。
- 清除锁序 Conversation row -> owner lock -> fence（防 AB-BA）；清除所有直接
  主体标识（created_by/archived_by/deleted_by + Message.author_id，P1-3/P1-5），
  HMAC tenant-scoped 不可逆匿名化；物理删除 MessagePart/UserState。
- final body scan 完成门禁（P1-5）：扫描含 archived_by/deleted_by；非零 ->
  fence erasing->blocked + operation/checkpoint 记 blocked + scan digest（P2-2），
  正常返回提交（P1-5，不抛异常致回滚）。
- ACK fencing（P1-3）：``purge_operation_id`` 必填；ACK 绑定具体 operation--
  校验 conversation_id / purge_revision / lease_epoch / registry drift /
  hold_revision_snapshot / operation 允许状态 + checkpoint owner_version /
  capability_digest CAS。同 tenant 同 revision 跨 Conversation operation 不得误 ACK。
- operation 投影 + erased 恢复（P1-4）：erasing 开始 operation->running；blocked
  ->blocked；erased fence 幂等重放时修复 pending checkpoint（ACK 丢失恢复）。
- 重试（P1-5）：fence blocked->erasing 重新进入，清除幂等（已 redacted/已删除
  no-op，P1-5：处理所有 author_id 残留不只是 body_state=present）。
- 时钟（P2-3）：purge 截止在 Conversation 锁后取 PostgreSQL ``clock_timestamp()``。
- reason code（P2-4）：legal hold 用 Spec §9.2 ``purge_blocked_by_legal_hold``。

本模块组合既有 ``AgentErasureRepository``（锁序/fence CAS），只新增正文清除与
body scan，不复制 fence/锁逻辑。redacted_reason 走受控白名单，自由文本不落库。
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition.agent_erasure_locks import acquire_owner_lock
from app.composition.agent_erasure_registry import (
    OwnerRegistryChangedError,
    capability_digest,
    registry_digest,
    require_capability,
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

# body scan 非零时的稳定 reason code（Spec §5.2 owner checkpoint reason_code）。
REASON_WORKSPACE_BODY_SCAN_NONZERO = "workspace_body_scan_nonzero"
# active legal hold 阻止 purge（Spec §9.2 稳定错误码，P2-4）。
REASON_PURGE_BLOCKED_BY_LEGAL_HOLD = "purge_blocked_by_legal_hold"

# Message 转 redacted tombstone 时落的受控 reason（Spec §7.1，白名单 code）。
_ERASURE_REDACTED_REASON = "retention_expired"

# 生产环境 actor_erasure_secret 必须显式设置（P1-2：fail-fast，不与 jwt_secret 共用）。
_PROD_ENVS = frozenset({"production"})


def _actor_audit_digest(
    *, secret: str, tenant_id: uuid.UUID, actor_id: uuid.UUID
) -> str:
    """tenant-scoped 不可逆 actor audit digest（Spec §7.1，P1-2：HMAC + 独立 secret）。

    ``HMAC(HMAC(secret, tenant_id), actor_id)``（SHA-256）：tenant-scoped 派生
    key、密钥隔离（独立 ``actor_erasure_secret``，非 jwt_secret）。digest 不含
    actor UUID 明文、不可逆；不同 tenant/secret 产生不同 digest；可复现。64-hex。
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
        """body scan 的 canonical digest（owner checkpoint 的 checkpoint_digest）。"""
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
    """erase_conversation_body 的结果（P1-5：blocked 为正常返回，不抛异常）。"""

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
        # P1-2：独立 actor_erasure_secret，非 jwt_secret；生产 fail-fast。
        secret = audit_secret if audit_secret is not None else settings.actor_erasure_secret
        if not secret and settings.environment in _PROD_ENVS:
            raise RuntimeError(
                "actor_erasure_secret must be set in production; "
                "refusing to derive actor audit digests from an empty secret"
            )
        self._audit_secret = secret or "dev-only-actor-erasure-secret"

    async def _database_now(self) -> datetime:
        """P2-3：purge 截止用 PostgreSQL ``clock_timestamp()``（非进程时钟）。"""
        result = await self._session.scalar(select(func.clock_timestamp()))
        # clock_timestamp() 在 PostgreSQL 始终返回一行一列；测试用 SQLite 也提供标量。
        assert result is not None, "clock_timestamp() must return a value"
        return result

    async def scan_body(
        self, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> WorkspaceBodyScan:
        """final workspace body scan（P1-5：含 archived_by/deleted_by；P2-1：tenant 谓词）。"""
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
        unanonymized_msgs = await self._session.scalar(
            select(func.count())
            .select_from(MessageModel)
            .where(
                MessageModel.tenant_id == tenant_id,
                MessageModel.conversation_id == conversation_id,
                MessageModel.author_id.is_not(None),
            )
        )
        # P2-1：Conversation 查询带 tenant_id 谓词（不用裸 get(PK)）。
        conversation = (
            (
                await self._session.execute(
                    select(ConversationModel).where(
                        ConversationModel.tenant_id == tenant_id,
                        ConversationModel.id == conversation_id,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        # P1-5：archived_by/deleted_by 也是直接主体标识，必须计入未匿名扫描。
        conversation_actor = 0
        if conversation is not None:
            if conversation.actor_state == "present":
                conversation_actor += 1
            if conversation.archived_by is not None:
                conversation_actor += 1
            if conversation.deleted_by is not None:
                conversation_actor += 1
        return WorkspaceBodyScan(
            present_body_messages=int(present_body or 0),
            message_parts=int(parts or 0),
            user_states=int(user_states or 0),
            unanonymized_actors=int(unanonymized_msgs or 0) + conversation_actor,
        )

    async def erase_conversation_body(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        purge_operation_id: uuid.UUID,
        now: datetime | None = None,
        expected_lease_epoch: int = 0,
    ) -> WorkspaceErasureOutcome:
        """清除 workspace.core.v1 正文并 ACK（S2-D/E 主入口，同一事务）。

        ``purge_operation_id`` 必填（P1-3：ACK 绑定具体 operation fencing）。
        锁序：Conversation row -> owner lock -> fence -> owner aggregate rows。
        """
        # P1-1：capability gate--workspace.core.v1 eraser 必须已安装。
        require_capability(WORKSPACE_CORE_OWNER, "erase")
        require_owner(WORKSPACE_CORE_OWNER)

        # 锁序第一步：Conversation 行锁。
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
        # P2-3：锁后取 DB 时钟作为 purge 截止（不依赖进程时钟）。
        effective_now = now if now is not None else await self._database_now()

        # 锁序第二步：owner advisory lock。
        await acquire_owner_lock(
            self._session,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key=WORKSPACE_CORE_OWNER,
        )

        # 锁内探测 fence：缺失 -> owner lock 下建。
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

        # P1-4：已 erased fence 的幂等重放先于 purge 前置（purged_at 后不得在读
        # fence 前被拒绝）。修复 pending checkpoint（ACK 丢失恢复）。
        if fence.state is ErasureFenceState.ERASED:
            # erased fence 必然携带 ack_digest（transition_fence_state 强制要求）。
            fence_ack_digest = fence.ack_digest
            assert fence_ack_digest is not None, "erased fence must carry ack_digest"
            scan = await self.scan_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            await self._repair_checkpoint_if_pending(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                ack_digest=fence_ack_digest,
                checkpoint_digest=scan.digest(),
                now=effective_now,
            )
            return WorkspaceErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=False,
                block_reason=None,
                ack_digest=fence_ack_digest,
            )

        # P1-1：purge 前置（仅对非 erased fence = 新 purge 强制）。
        self._require_purgeable(conversation, now=effective_now)

        # active legal hold -> blocked 正常返回（P2-4：purge_blocked_by_legal_hold）。
        if await self._erasure.has_active_legal_hold(
            tenant_id=tenant_id, conversation_id=conversation_id
        ):
            scan = await self.scan_body(
                tenant_id=tenant_id, conversation_id=conversation_id
            )
            await self._record_blocked(
                purge_operation_id=purge_operation_id,
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                purge_revision=purge_revision,
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                scan=scan,
                now=effective_now,
            )
            return WorkspaceErasureOutcome(
                fence=fence,
                body_scan=scan,
                blocked=True,
                block_reason=REASON_PURGE_BLOCKED_BY_LEGAL_HOLD,
                ack_digest=None,
            )

        # 推进 fence -> erasing（首写 active->erasing；重试 blocked->erasing；
        # crash 恢复 erasing 继续）。
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

        # P1-4：operation 投影 -> running；conversation.purge_state -> running。
        await self._mark_operation_running(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation.hold_revision,
            now=effective_now,
        )
        conversation.purge_state = PurgeState.RUNNING.value
        conversation.updated_at = effective_now

        # 锁序第四步：owner aggregate rows 清除正文（幂等）。
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
            # 非零 -> fence erasing->blocked + operation/checkpoint 记 blocked +
            # scan digest（P2-2）。正常返回（不抛异常），调用方 commit 后可重试。
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
                expected_lease_epoch=expected_lease_epoch,
                hold_revision=conversation.hold_revision,
                reason=REASON_WORKSPACE_BODY_SCAN_NONZERO,
                scan=scan,
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

        # body scan 为零 -> ACK。
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
        # P1-3：ACK 绑定具体 operation + 完整 fencing。
        await self._ack_owner_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=conversation.hold_revision,
            fence_owner_version=fence.owner_version,
            ack_digest=ack_digest,
            checkpoint_digest=scan.digest(),
            now=effective_now,
        )
        # 单 owner ACK 不写 purge_state=completed（多 owner 完成判定属 S3/S4）。
        return WorkspaceErasureOutcome(
            fence=fence,
            body_scan=scan,
            blocked=False,
            block_reason=None,
            ack_digest=ack_digest,
        )

    # --- operation fencing（P1-3/P1-4）--------------------------------

    async def _load_verified_operation(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
    ) -> PurgeOperationModel:
        """加载具体 operation FOR UPDATE + 完整 fencing（P1-3）。

        校验 conversation_id（跨 Conversation 误 ACK 防护）、purge_revision、
        lease_epoch（stale lease）、registry_digest（drift）、hold_revision_snapshot
        （hold 状态漂移）。任一不符 fail closed。
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
                f"purge operation {purge_operation_id} not found"
            )
        if operation.conversation_id != conversation_id:
            raise ValueError(
                f"operation conversation_id {operation.conversation_id} != "
                f"erase target {conversation_id}; cross-conversation ACK rejected"
            )
        if operation.purge_revision != purge_revision:
            raise ValueError(
                f"purge_revision mismatch: operation={operation.purge_revision} "
                f"request={purge_revision}"
            )
        if operation.lease_epoch != expected_lease_epoch:
            raise ValueError(
                f"lease_epoch mismatch: operation={operation.lease_epoch} "
                f"expected={expected_lease_epoch}; stale lease rejected"
            )
        if operation.registry_digest != registry_digest():
            raise OwnerRegistryChangedError(
                "purge operation registry digest no longer matches installed "
                "registry; cannot proceed on stale capability view"
            )
        if operation.hold_revision_snapshot != hold_revision:
            raise ValueError(
                f"hold_revision drift: operation snapshot "
                f"{operation.hold_revision_snapshot} != conversation "
                f"{hold_revision}; operation stale, create new purge_revision"
            )
        return operation

    async def _load_verified_checkpoint(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        fence_owner_version: int,
    ) -> PurgeOwnerCheckpointModel:
        """加载具体 owner checkpoint FOR UPDATE + 校验 owner_version/capability_digest
        （P1-3）。"""
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
                f"workspace owner checkpoint for operation "
                f"{purge_operation_id} not found"
            )
        if checkpoint.owner_version != fence_owner_version:
            raise ValueError(
                f"checkpoint owner_version {checkpoint.owner_version} != "
                f"fence {fence_owner_version}"
            )
        if checkpoint.capability_digest != capability_digest(WORKSPACE_CORE_OWNER):
            raise ValueError(
                "checkpoint capability_digest does not match installed "
                "workspace.core.v1 capability"
            )
        return checkpoint

    async def _mark_operation_running(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        now: datetime,
    ) -> None:
        """P1-4：operation scheduled->running（首次）；running/blocked 保持。"""
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
        )
        if operation.state not in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.RUNNING.value,
            PurgeOperationState.BLOCKED.value,
        ):
            raise ValueError(
                f"operation not in runnable state: {operation.state!r}"
            )
        if operation.state == PurgeOperationState.SCHEDULED.value:
            operation.state = PurgeOperationState.RUNNING.value
            if operation.started_at is None:
                operation.started_at = now
            operation.updated_at = now
            await self._session.flush()

    async def _record_blocked(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        reason: str,
        scan: WorkspaceBodyScan,
        now: datetime,
    ) -> None:
        """记 blocked：operation + owner checkpoint 经 CAS 推进 blocked + 稳定
        reason code + scan digest（P2-2）。正常返回路径调用，随调用方事务 commit。"""
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
        )
        if operation.state not in (
            PurgeOperationState.SCHEDULED.value,
            PurgeOperationState.RUNNING.value,
            PurgeOperationState.BLOCKED.value,
        ):
            raise ValueError(
                f"operation not in blockable state: {operation.state!r}"
            )
        if operation.state != PurgeOperationState.BLOCKED.value:
            operation.state = PurgeOperationState.BLOCKED.value
            operation.failure_code = reason
            operation.updated_at = now
        checkpoint = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=1,  # workspace.core.v1 owner_version=1（registry 固定）
        )
        if checkpoint.state not in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.ERASING.value,
            PurgeOwnerState.BLOCKED.value,
        ):
            raise ValueError(
                f"checkpoint not blockable from state {checkpoint.state!r}"
            )
        checkpoint.state = PurgeOwnerState.BLOCKED.value
        checkpoint.reason_code = reason
        # P2-2：blocked 路径也写 scan digest（非零 scan 的证据）。
        checkpoint.checkpoint_digest = scan.digest()
        checkpoint.updated_at = now
        await self._session.flush()

    async def _ack_owner_checkpoint(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        fence_owner_version: int,
        ack_digest: str,
        checkpoint_digest: str,
        now: datetime,
    ) -> None:
        """ACK owner checkpoint（P1-3：完整 fencing + CAS）。"""
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
        )
        if operation.state not in (
            PurgeOperationState.RUNNING.value,
            PurgeOperationState.BLOCKED.value,
        ):
            raise ValueError(
                f"operation not in ackable state: {operation.state!r}"
            )
        checkpoint = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=fence_owner_version,
        )
        if checkpoint.state not in (
            PurgeOwnerState.PENDING.value,
            PurgeOwnerState.ERASING.value,
            PurgeOwnerState.BLOCKED.value,
        ):
            raise ValueError(
                f"checkpoint not ackable from state {checkpoint.state!r}"
            )
        checkpoint.state = PurgeOwnerState.ACKED.value
        checkpoint.ack_digest = ack_digest
        checkpoint.checkpoint_digest = checkpoint_digest
        checkpoint.reason_code = None
        checkpoint.updated_at = now
        # operation 保持 running（单 owner 不伪造 completed）。
        await self._session.flush()

    async def _repair_checkpoint_if_pending(
        self,
        *,
        purge_operation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        purge_revision: int,
        expected_lease_epoch: int,
        hold_revision: int,
        ack_digest: str,
        checkpoint_digest: str,
        now: datetime,
    ) -> None:
        """P1-4：erased fence 幂等重放时修复 pending checkpoint（ACK 丢失恢复）。

        fence 已 erased 但 checkpoint 未 acked（ACK 丢失/前次未绑定 operation）->
        用 fence 的 ack_digest 补 ACK。已 acked 则 no-op。
        """
        operation = await self._load_verified_operation(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            purge_revision=purge_revision,
            expected_lease_epoch=expected_lease_epoch,
            hold_revision=hold_revision,
        )
        checkpoint = await self._load_verified_checkpoint(
            purge_operation_id=purge_operation_id,
            tenant_id=tenant_id,
            fence_owner_version=1,
        )
        if checkpoint.state == PurgeOwnerState.ACKED.value:
            return  # 已 acked，无需修复。
        checkpoint.state = PurgeOwnerState.ACKED.value
        checkpoint.ack_digest = ack_digest
        checkpoint.checkpoint_digest = checkpoint_digest
        checkpoint.reason_code = None
        checkpoint.updated_at = now
        # operation 也修复到 running（ACK 丢失可能 operation 卡在 scheduled）。
        if operation.state == PurgeOperationState.SCHEDULED.value:
            operation.state = PurgeOperationState.RUNNING.value
        await self._session.flush()

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

        created_by -> NULL + HMAC digest；archived_by/deleted_by -> NULL。
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
        """Message 转 redacted tombstone + author 匿名化（P1-5：处理所有
        author_id 残留，不只 body_state=present）。

        选择 body_state=present **或** author_id 非空的所有 Message：已 redacted
        但仍带 author_id 的 assistant/system Message 也清除（否则 scan 永久非零、
        无法自愈）。幂等：已 redacted + author_id=NULL 的 no-op。
        """
        rows = (
            (
                await self._session.execute(
                    select(MessageModel)
                    .where(
                        MessageModel.tenant_id == tenant_id,
                        MessageModel.conversation_id == conversation_id,
                        or_(
                            MessageModel.body_state == "present",
                            MessageModel.author_id.is_not(None),
                        ),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        for message in rows:
            if message.body_state == "present":
                message.body_state = "redacted"
                message.content_state = "redacted"
                message.redacted_at = now
                message.redacted_reason = _ERASURE_REDACTED_REASON
            author_id = message.author_id
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
        """物理删除该 Conversation 所有 MessagePart 正文行。"""
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
        """物理删除 ConversationUserState。"""
        result = await self._session.execute(
            delete(ConversationUserStateModel).where(
                ConversationUserStateModel.tenant_id == tenant_id,
                ConversationUserStateModel.conversation_id == conversation_id,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)


__all__ = [
    "REASON_PURGE_BLOCKED_BY_LEGAL_HOLD",
    "REASON_WORKSPACE_BODY_SCAN_NONZERO",
    "WORKSPACE_CORE_OWNER",
    "WorkspaceBodyScan",
    "WorkspaceErasureOutcome",
    "WorkspaceErasureParticipant",
    "WorkspaceErasureSummary",
]
