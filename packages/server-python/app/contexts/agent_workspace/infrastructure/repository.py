from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import DateTime, and_, exists, func, literal, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.contexts.agent_workspace.domain import (
    AuthorType,
    ContentClassification,
    Conversation,
    ConversationIdConflictError,
    ConversationNotFoundError,
    ConversationPurgedError,
    ConversationPurgeInProgressError,
    ConversationRecoveryExpiredError,
    ConversationState,
    ConversationTitleSource,
    ConversationUserState,
    IdempotencyConflictError,
    InvalidConversationStateError,
    Message,
    MessageContentState,
    MessageKind,
    MessagePart,
    MessagePartType,
    PurgeState,
    RevisionConflictError,
    TitleSourceConflictError,
    TurnDispatchState,
)
from app.contexts.agent_workspace.infrastructure.erasure_repository import (
    AgentErasureRepository,
)
from app.contexts.agent_workspace.infrastructure.models import (
    ConversationModel,
    ConversationUserStateModel,
    MessageModel,
    MessagePartModel,
)

UNPINNED_SORT = datetime(1970, 1, 1, tzinfo=UTC)


class AgentWorkspaceRepository:
    """Tenant- and owner-scoped PostgreSQL adapter for workspace facts."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_conversation(
        self, conversation: Conversation
    ) -> tuple[Conversation, bool]:
        values = {
            "id": conversation.id,
            "tenant_id": conversation.tenant_id,
            "created_by": conversation.created_by,
            "creation_digest": conversation.creation_digest,
            "title": conversation.title,
            "title_source": conversation.title_source.value,
            "state": conversation.state.value,
            "parent_conversation_id": conversation.parent_conversation_id,
            "forked_from_message_id": conversation.forked_from_message_id,
            "next_message_seq": conversation.next_message_seq,
            "next_run_queue_seq": conversation.next_run_queue_seq,
            "last_activity_at": conversation.last_activity_at,
            "purge_state": conversation.purge_state.value,
            "purge_revision": conversation.purge_revision,
            "revision": conversation.revision,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }
        stmt = (
            insert(ConversationModel)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[ConversationModel.id])
            .returning(ConversationModel.id)
        )
        inserted_id = (await self._session.execute(stmt)).scalar_one_or_none()
        row = await self._get_owned_row(
            conversation.tenant_id,
            conversation.created_by,
            conversation.id,
            include_deleted=True,
        )
        if row is None:
            raise ConversationIdConflictError("conversation id is already in use")
        if row.creation_digest != conversation.creation_digest:
            raise IdempotencyConflictError(
                "conversation id was already used with a different create command"
            )
        if inserted_id is not None:
            # 真实新建分支（Spec §4.2/§6.2，S2-C）：为 workspace.core.v1 建
            # baseline active fence——缺失 fence 不得被解释为安全。经
            # create_fence_under_owner_lock（自带 Conversation 行锁 -> owner
            # lock -> fence，防 AB-BA）。幂等重放分支（行已存在）不重建 fence。
            # 其余 owner 由受控 backfill 补齐。
            erasure = AgentErasureRepository(self._session)
            await erasure.create_fence_under_owner_lock(
                tenant_id=conversation.tenant_id,
                conversation_id=conversation.id,
                owner_key="workspace.core.v1",
            )
            # S2-C P1-4 复审：初始 title 非空（title_source=user，真实 title 写）
            # 时必须同事务推进 title ingress——watermark 取创建时的 Conversation
            # revision（=1），epoch 取 purge_revision（=0）。仅 title=None（none
            # tombstone）不算 title 写、不推进。
            if conversation.title is not None:
                await erasure.advance_ingress_checkpoint_for_update(
                    tenant_id=conversation.tenant_id,
                    conversation_id=conversation.id,
                    owner_key="workspace.core.v1",
                    source_key="title",
                    watermark=row.revision,
                    epoch=row.purge_revision,
                )
        return self._to_conversation(row), inserted_id is not None

    async def get_conversation(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> tuple[Conversation, datetime | None] | None:
        stmt = (
            select(ConversationModel, ConversationUserStateModel.pinned_at)
            .outerjoin(
                ConversationUserStateModel,
                and_(
                    ConversationUserStateModel.tenant_id
                    == ConversationModel.tenant_id,
                    ConversationUserStateModel.conversation_id
                    == ConversationModel.id,
                    ConversationUserStateModel.user_id == actor_id,
                ),
            )
            .where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.created_by == actor_id,
                ConversationModel.id == conversation_id,
            )
        )
        if not include_deleted:
            stmt = stmt.where(ConversationModel.state != ConversationState.DELETED.value)
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return self._to_conversation(row[0]), row[1]

    async def list_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        state: ConversationState,
        query: str | None,
        issued_at: datetime,
        anchor_pinned_sort: datetime | None,
        anchor_last_activity_at: datetime | None,
        anchor_id: uuid.UUID | None,
        limit: int,
    ) -> tuple[list[tuple[Conversation, datetime | None]], bool]:
        pinned_sort = func.coalesce(
            ConversationUserStateModel.pinned_at,
            literal(UNPINNED_SORT, type_=DateTime(timezone=True)),
        )
        stmt = (
            select(ConversationModel, ConversationUserStateModel.pinned_at)
            .outerjoin(
                ConversationUserStateModel,
                and_(
                    ConversationUserStateModel.tenant_id
                    == ConversationModel.tenant_id,
                    ConversationUserStateModel.conversation_id
                    == ConversationModel.id,
                    ConversationUserStateModel.user_id == actor_id,
                ),
            )
            .where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.created_by == actor_id,
                ConversationModel.state == state.value,
                ConversationModel.created_at <= issued_at,
            )
        )
        if query is not None:
            pattern = f"%{self._escape_like(query)}%"
            visible_text_match = exists(
                select(MessageModel.id)
                .select_from(MessageModel)
                .join(
                    MessagePartModel,
                    and_(
                        MessagePartModel.tenant_id == MessageModel.tenant_id,
                        MessagePartModel.message_id == MessageModel.id,
                    ),
                )
                .where(
                    MessageModel.tenant_id == tenant_id,
                    MessageModel.conversation_id == ConversationModel.id,
                    MessageModel.content_state == MessageContentState.VISIBLE.value,
                    MessagePartModel.part_type == MessagePartType.TEXT.value,
                    MessagePartModel.text_content.ilike(pattern, escape="\\"),
                )
            )
            stmt = stmt.where(
                or_(
                    ConversationModel.title.ilike(pattern, escape="\\"),
                    visible_text_match,
                )
            )
        if anchor_pinned_sort is not None:
            if anchor_last_activity_at is None or anchor_id is None:
                raise ValueError("incomplete conversation cursor anchor")
            stmt = stmt.where(
                or_(
                    pinned_sort < anchor_pinned_sort,
                    and_(
                        pinned_sort == anchor_pinned_sort,
                        ConversationModel.last_activity_at < anchor_last_activity_at,
                    ),
                    and_(
                        pinned_sort == anchor_pinned_sort,
                        ConversationModel.last_activity_at == anchor_last_activity_at,
                        ConversationModel.id < anchor_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            pinned_sort.desc(),
            ConversationModel.last_activity_at.desc(),
            ConversationModel.id.desc(),
        ).limit(limit + 1)
        rows = (await self._session.execute(stmt)).all()
        has_more = len(rows) > limit
        return [
            (self._to_conversation(row[0]), row[1]) for row in rows[:limit]
        ], has_more

    async def set_title(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        title: str,
        expected_revision: int,
        source: ConversationTitleSource,
        require_no_title: bool = False,
    ) -> Conversation:
        row = await self._require_owned_row_for_update(
            tenant_id, actor_id, conversation_id
        )
        self._check_revision(row, expected_revision)
        if require_no_title and row.title_source != ConversationTitleSource.NONE.value:
            raise TitleSourceConflictError("conversation title is no longer unset")
        # Spec §6.2（S2-C）：title 是 workspace.core.v1 的 conversation_title
        # 能力，rename/auto-title 与正文同走 fence 裁决——fence 非 active
        # （purge 进行中/已完成）fail closed，不得在清除路径上改写 title。
        await AgentErasureRepository(
            self._session
        ).require_body_write_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
        )
        row.title = title
        row.title_source = source.value
        row.revision += 1
        row.updated_at = datetime.now(UTC)
        # title ingress（S2-C 契约注记）：watermark 取 title CAS 后的 Conversation
        # revision，epoch 取 purge_revision；与 title 写同一事务 commit。
        await AgentErasureRepository(
            self._session
        ).advance_ingress_checkpoint_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
            source_key="title",
            watermark=row.revision,
            epoch=row.purge_revision,
        )
        await self._session.flush()
        return self._to_conversation(row)

    async def archive(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
    ) -> Conversation:
        row = await self._require_owned_row_for_update(
            tenant_id, actor_id, conversation_id
        )
        self._check_revision(row, expected_revision)
        if row.state != ConversationState.ACTIVE.value:
            raise InvalidConversationStateError("only active conversations can be archived")
        now = datetime.now(UTC)
        row.state = ConversationState.ARCHIVED.value
        row.archived_at = now
        row.archived_by = actor_id
        row.revision += 1
        row.updated_at = now
        await self._session.flush()
        return self._to_conversation(row)

    async def restore(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
        now: datetime | None = None,
    ) -> Conversation:
        row = await self._require_owned_row_for_update(
            tenant_id, actor_id, conversation_id, include_deleted=True
        )
        self._check_revision(row, expected_revision)
        if row.purged_at is not None:
            raise ConversationPurgedError("purged conversations cannot be restored")
        # R1-S2 恢复截止（Spec §3）：purge_state=running|completed 拒绝普通恢复。
        # 这些检查必须在清除 purge_after 之前、同一行锁下完成。
        if row.purge_state in {
            PurgeState.RUNNING.value,
            PurgeState.COMPLETED.value,
        }:
            raise ConversationPurgeInProgressError(
                "conversation purge is running or completed; cannot be restored"
            )
        # 生产默认裁决时间取数据库时钟（bridge 在锁后注入时尊重注入值）。
        effective_now = now or await self._database_now()
        # deleted 且 purge_after IS NULL：无法证明 now < purge_after -> fail
        # closed，不得把「无截止记录」当作可恢复放行。
        if row.state == ConversationState.DELETED.value:
            if row.purge_after is None:
                raise ConversationRecoveryExpiredError(
                    "deleted conversation has no recovery deadline recorded; "
                    "cannot prove the recovery window is still open"
                )
            if effective_now >= row.purge_after:
                raise ConversationRecoveryExpiredError(
                    "conversation recovery window has expired"
                )
        if row.state not in {
            ConversationState.ARCHIVED.value,
            ConversationState.DELETED.value,
        }:
            raise InvalidConversationStateError(
                "only archived or deleted conversations can be restored"
            )
        # Spec §3-3：恢复成功通过 CAS 取消尚未开始的 purge operation（置
        # cancelled 终态、保留审计行）；与下方 Conversation 状态恢复同一事务
        # 原子提交。started 的 checkpoint 会在取消前 fail closed。
        await AgentErasureRepository(
            self._session
        ).cancel_scheduled_operations_for_restore(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            now=effective_now,
        )
        # revision/hold/purge CAS：Conversation FOR UPDATE 行锁已串行并发写
        # （任何 hold/purge 变更须先取同一行锁），UPDATE 谓词作兜底；恢复同时
        # 推进 purge_revision，旧 purge lease/revision 随后失效（Spec §3-3）。
        result = await self._session.execute(
            update(ConversationModel)
            .where(
                ConversationModel.tenant_id == tenant_id,
                ConversationModel.id == row.id,
                ConversationModel.revision == row.revision,
                ConversationModel.hold_revision == row.hold_revision,
                ConversationModel.purge_revision == row.purge_revision,
            )
            .values(
                state=ConversationState.ACTIVE.value,
                archived_at=None,
                archived_by=None,
                deleted_at=None,
                deleted_by=None,
                purge_after=None,
                purge_state=PurgeState.NOT_SCHEDULED.value,
                purge_revision=row.purge_revision + 1,
                revision=row.revision + 1,
                updated_at=effective_now,
            )
            .execution_options(synchronize_session=False)
        )
        if not isinstance(result, CursorResult) or result.rowcount != 1:
            raise RevisionConflictError(
                "conversation revision/hold/purge token changed during restore"
            )
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_conversation(row)

    async def soft_delete_after_guard(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
        purge_after: datetime,
        deleted_at: datetime | None = None,
    ) -> Conversation:
        """Persist deletion after B1's coordinator has proved its execution guard.

        deleted_at 与 purge_after 必须同源（purge_after = deleted_at + 恢复
        窗口）；生产默认在锁后取数据库时钟，调用方注入同一采样值。
        """
        row = await self._require_owned_row_for_update(
            tenant_id, actor_id, conversation_id
        )
        self._check_revision(row, expected_revision)
        now = deleted_at or await self._database_now()
        row.state = ConversationState.DELETED.value
        row.deleted_at = now
        row.deleted_by = actor_id
        row.purge_after = purge_after
        row.purge_state = PurgeState.SCHEDULED.value
        row.purge_revision += 1
        row.revision += 1
        row.updated_at = now
        await self._session.flush()
        return self._to_conversation(row)

    async def set_pinned(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        pinned: bool,
    ) -> ConversationUserState:
        if await self._get_owned_row(
            tenant_id, actor_id, conversation_id, include_deleted=False
        ) is None:
            raise ConversationNotFoundError("conversation not found")
        now = datetime.now(UTC)
        pinned_at = now if pinned else None
        stmt = (
            insert(ConversationUserStateModel)
            .values(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                user_id=actor_id,
                pinned_at=pinned_at,
                last_read_message_seq=0,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=[
                    ConversationUserStateModel.tenant_id,
                    ConversationUserStateModel.conversation_id,
                    ConversationUserStateModel.user_id,
                ],
                set_={"pinned_at": pinned_at, "updated_at": now},
            )
            .returning(ConversationUserStateModel)
        )
        row = (await self._session.execute(stmt)).scalar_one()
        return self._to_user_state(row)

    async def list_messages(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        before_seq: int | None,
        after_seq: int | None,
        limit: int,
    ) -> tuple[list[Message], bool]:
        if await self._get_owned_row(
            tenant_id, actor_id, conversation_id, include_deleted=False
        ) is None:
            raise ConversationNotFoundError("conversation not found")
        stmt = select(MessageModel).where(
            MessageModel.tenant_id == tenant_id,
            MessageModel.conversation_id == conversation_id,
        )
        descending = after_seq is None
        if before_seq is not None:
            stmt = stmt.where(MessageModel.seq < before_seq)
        elif after_seq is not None:
            stmt = stmt.where(MessageModel.seq > after_seq)
        stmt = stmt.order_by(
            MessageModel.seq.desc() if descending else MessageModel.seq.asc()
        ).limit(limit + 1)
        rows = list((await self._session.execute(stmt)).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        if descending:
            rows.reverse()
        return await self._messages_with_parts(tenant_id, rows), has_more

    async def reserve_user_turn(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        client_message_id: uuid.UUID,
        requested_run_id: uuid.UUID,
        turn_request_digest: str,
        content_digest: str,
        parts: Sequence[MessagePart],
    ) -> tuple[Message, bool]:
        row = await self._require_owned_row_for_update(
            tenant_id, actor_id, conversation_id, include_deleted=False
        )
        if row.state != ConversationState.ACTIVE.value:
            raise InvalidConversationStateError(
                "new turns require an active conversation"
            )
        # Spec §6.2 正文 writer fence：Conversation 行锁之后取 owner lock +
        # fence FOR UPDATE，仅 workspace.core.v1 fence active 才允许写用户正文；
        # purge 进行中/已完成 fail closed（late_body_write_rejected），不得复活
        # 正在清除路径上的正文。
        await AgentErasureRepository(
            self._session
        ).require_body_write_fence_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
        )
        existing_stmt = select(MessageModel).where(
            MessageModel.tenant_id == tenant_id,
            MessageModel.conversation_id == conversation_id,
            MessageModel.author_id == actor_id,
            MessageModel.client_message_id == client_message_id,
            MessageModel.message_kind == MessageKind.USER_INPUT.value,
        )
        existing = (await self._session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return (await self._messages_with_parts(tenant_id, [existing]))[0], False

        now = datetime.now(UTC)
        message_row = MessageModel(
            id=message_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            seq=row.next_message_seq,
            message_kind=MessageKind.USER_INPUT.value,
            author_type=AuthorType.USER.value,
            author_id=actor_id,
            client_message_id=client_message_id,
            requested_run_id=requested_run_id,
            requested_run_queue_seq=row.next_run_queue_seq,
            turn_request_digest=turn_request_digest,
            turn_dispatch_state=TurnDispatchState.PENDING.value,
            turn_dispatch_updated_at=now,
            content_state=MessageContentState.VISIBLE.value,
            content_digest=content_digest,
            created_at=now,
        )
        self._session.add(message_row)
        self._session.add_all(
            [
                MessagePartModel(
                    id=part.id,
                    tenant_id=part.tenant_id,
                    message_id=part.message_id,
                    part_seq=part.part_seq,
                    part_type=part.part_type.value,
                    text_content=part.text_content,
                    content_format=part.content_format,
                    resource_id=part.resource_id,
                    media_type=part.media_type,
                    display_name=part.display_name,
                    digest=part.digest,
                    classification=part.classification.value,
                )
                for part in parts
            ]
        )
        row.next_message_seq += 1
        row.next_run_queue_seq += 1
        row.last_activity_at = now
        row.updated_at = now
        # Spec §6.2 第 5 步（S2-C）：正文写 + ingress checkpoint 同一事务 commit。
        # body_messages source 的 watermark 记录本写分配到的真实 message seq
        # （连续水位），epoch 取 Conversation 当前 purge_revision——不用
        # last_body_write_at 或 fence revision 冒充 ingress checkpoint。
        await AgentErasureRepository(
            self._session
        ).advance_ingress_checkpoint_for_update(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            owner_key="workspace.core.v1",
            source_key="body_messages",
            watermark=message_row.seq,
            epoch=row.purge_revision,
        )
        await self._session.flush()
        return self._to_message(message_row, tuple(parts)), True

    async def _get_owned_row(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        include_deleted: bool,
        for_update: bool = False,
    ) -> ConversationModel | None:
        stmt = select(ConversationModel).where(
            ConversationModel.tenant_id == tenant_id,
            ConversationModel.created_by == actor_id,
            ConversationModel.id == conversation_id,
        )
        if not include_deleted:
            stmt = stmt.where(ConversationModel.state != ConversationState.DELETED.value)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _require_owned_row_for_update(
        self,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        include_deleted: bool = False,
    ) -> ConversationModel:
        row = await self._get_owned_row(
            tenant_id,
            actor_id,
            conversation_id,
            include_deleted=include_deleted,
            for_update=True,
        )
        if row is None:
            raise ConversationNotFoundError("conversation not found")
        return row

    @staticmethod
    def _check_revision(row: ConversationModel, expected_revision: int) -> None:
        if row.revision != expected_revision:
            raise RevisionConflictError(
                f"expected revision {expected_revision}, current revision is {row.revision}"
            )

    async def _database_now(self) -> datetime:
        """生产默认时钟源：数据库 ``clock_timestamp()``（不是应用进程时钟）。"""
        now = await self._session.scalar(select(func.clock_timestamp()))
        assert now is not None
        return now

    async def _messages_with_parts(
        self, tenant_id: uuid.UUID, rows: Sequence[MessageModel]
    ) -> list[Message]:
        if not rows:
            return []
        message_ids = [row.id for row in rows]
        stmt = (
            select(MessagePartModel)
            .where(
                MessagePartModel.tenant_id == tenant_id,
                MessagePartModel.message_id.in_(message_ids),
            )
            .order_by(MessagePartModel.message_id, MessagePartModel.part_seq)
        )
        part_rows = (await self._session.execute(stmt)).scalars().all()
        by_message: dict[uuid.UUID, list[MessagePart]] = defaultdict(list)
        for part in part_rows:
            by_message[part.message_id].append(self._to_message_part(part))
        return [self._to_message(row, tuple(by_message[row.id])) for row in rows]

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _to_conversation(row: ConversationModel) -> Conversation:
        # actor tombstone（redacted）的 created_by 已被清除为 None；S1 无清除
        # writer，该读路径不应遇到。若遇到说明存在越权写 -> fail closed。
        if row.created_by is None:
            raise ConversationIdConflictError(
                "conversation actor is erased; snapshot unavailable"
            )
        return Conversation(
            id=row.id,
            tenant_id=row.tenant_id,
            created_by=row.created_by,
            creation_digest=row.creation_digest,
            title=row.title,
            title_source=ConversationTitleSource(row.title_source),
            state=ConversationState(row.state),
            parent_conversation_id=row.parent_conversation_id,
            forked_from_message_id=row.forked_from_message_id,
            next_message_seq=row.next_message_seq,
            next_run_queue_seq=row.next_run_queue_seq,
            last_activity_at=row.last_activity_at,
            archived_at=row.archived_at,
            archived_by=row.archived_by,
            deleted_at=row.deleted_at,
            deleted_by=row.deleted_by,
            purge_after=row.purge_after,
            purge_state=PurgeState(row.purge_state),
            purge_revision=row.purge_revision,
            purged_at=row.purged_at,
            revision=row.revision,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _to_user_state(row: ConversationUserStateModel) -> ConversationUserState:
        return ConversationUserState(
            tenant_id=row.tenant_id,
            conversation_id=row.conversation_id,
            user_id=row.user_id,
            pinned_at=row.pinned_at,
            last_read_message_seq=row.last_read_message_seq,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _to_message_part(row: MessagePartModel) -> MessagePart:
        return MessagePart(
            id=row.id,
            tenant_id=row.tenant_id,
            message_id=row.message_id,
            part_seq=row.part_seq,
            part_type=MessagePartType(row.part_type),
            text_content=row.text_content,
            content_format=row.content_format,
            resource_id=row.resource_id,
            media_type=row.media_type,
            display_name=row.display_name,
            digest=row.digest,
            classification=ContentClassification(row.classification),
        )

    @staticmethod
    def _to_message(row: MessageModel, parts: tuple[MessagePart, ...]) -> Message:
        return Message(
            id=row.id,
            tenant_id=row.tenant_id,
            conversation_id=row.conversation_id,
            seq=row.seq,
            message_kind=MessageKind(row.message_kind),
            author_type=AuthorType(row.author_type),
            author_id=row.author_id,
            client_message_id=row.client_message_id,
            requested_run_id=row.requested_run_id,
            requested_run_queue_seq=row.requested_run_queue_seq,
            turn_request_digest=row.turn_request_digest,
            turn_dispatch_state=(
                TurnDispatchState(row.turn_dispatch_state)
                if row.turn_dispatch_state
                else None
            ),
            turn_dispatch_error_code=row.turn_dispatch_error_code,
            turn_dispatch_updated_at=row.turn_dispatch_updated_at,
            origin_run_id=row.origin_run_id,
            output_ordinal=row.output_ordinal,
            reply_to_message_id=row.reply_to_message_id,
            content_state=MessageContentState(row.content_state),
            content_digest=row.content_digest,
            created_at=row.created_at,
            redacted_at=row.redacted_at,
            redacted_reason=row.redacted_reason,
            parts=parts,
        )
