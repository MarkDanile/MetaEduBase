from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.contexts.agent_workspace.application.command_digest import (
    canonical_digest,
    message_content_digest,
    message_part_digest,
)
from app.contexts.agent_workspace.application.command_digest import (
    turn_request_digest as build_turn_request_digest,
)
from app.contexts.agent_workspace.application.cursor import (
    ConversationCursor,
    ConversationCursorCodec,
)
from app.contexts.agent_workspace.application.dto import (
    ConversationPage,
    ConversationView,
    MessagePage,
    MessagePartInput,
    ReservedUserTurn,
    TurnCommand,
)
from app.contexts.agent_workspace.application.ports import ResourceReferenceAccessPort
from app.contexts.agent_workspace.domain import (
    Conversation,
    ConversationNotFoundError,
    ConversationState,
    ConversationTitleSource,
    IdempotencyConflictError,
    MessagePart,
    MessagePartType,
    PurgeState,
    ResourceReferenceForbiddenError,
)
from app.contexts.agent_workspace.infrastructure.repository import (
    UNPINNED_SORT,
    AgentWorkspaceRepository,
)

MAX_MESSAGE_TEXT_BYTES = 64 * 1024
MAX_MESSAGE_PARTS = 64


class AgentWorkspaceService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        cursor_secret: str | None = None,
        resource_access: ResourceReferenceAccessPort | None = None,
    ):
        self._repo = AgentWorkspaceRepository(session)
        self._resource_access = resource_access
        self._cursor_codec = ConversationCursorCodec(
            cursor_secret if cursor_secret is not None else settings.jwt_secret
        )

    async def create_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID | None = None,
        title: str | None = None,
    ) -> tuple[ConversationView, bool]:
        now = datetime.now(UTC)
        clean_title = self.normalize_title(title) if title is not None else None
        resolved_id = conversation_id or uuid.uuid4()
        creation_digest = canonical_digest(
            {
                "actor_id": str(actor_id),
                "conversation_id": str(resolved_id),
                "schema_version": 1,
                "tenant_id": str(tenant_id),
                "title": clean_title,
            }
        )
        conversation = Conversation(
            id=resolved_id,
            tenant_id=tenant_id,
            created_by=actor_id,
            creation_digest=creation_digest,
            title=clean_title,
            title_source=(
                ConversationTitleSource.USER
                if clean_title is not None
                else ConversationTitleSource.NONE
            ),
            state=ConversationState.ACTIVE,
            parent_conversation_id=None,
            forked_from_message_id=None,
            next_message_seq=1,
            next_run_queue_seq=1,
            last_activity_at=now,
            archived_at=None,
            archived_by=None,
            deleted_at=None,
            deleted_by=None,
            purge_after=None,
            purge_state=PurgeState.NOT_SCHEDULED,
            purge_revision=0,
            purged_at=None,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        stored, created = await self._repo.create_conversation(conversation)
        return ConversationView(stored, None), created

    async def get_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        include_deleted: bool = False,
    ) -> ConversationView:
        result = await self._repo.get_conversation(
            tenant_id,
            actor_id,
            conversation_id,
            include_deleted=include_deleted,
        )
        if result is None:
            raise ConversationNotFoundError("conversation not found")
        return ConversationView(result[0], result[1])

    async def list_conversations(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        state: ConversationState = ConversationState.ACTIVE,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 30,
    ) -> ConversationPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        normalized_query = self.normalize_search_query(query) if query else None
        filter_digest = canonical_digest(
            {
                "actor_id": str(actor_id),
                "query": normalized_query,
                "schema_version": 1,
                "state": state.value,
                "tenant_id": str(tenant_id),
            }
        )
        if cursor:
            decoded = self._cursor_codec.decode(
                cursor, expected_filter_digest=filter_digest
            )
            issued_at = decoded.issued_at
            anchor_pinned = decoded.pinned_sort
            anchor_activity = decoded.last_activity_at
            anchor_id = decoded.conversation_id
        else:
            issued_at = datetime.now(UTC)
            anchor_pinned = None
            anchor_activity = None
            anchor_id = None
        rows, has_more = await self._repo.list_conversations(
            tenant_id=tenant_id,
            actor_id=actor_id,
            state=state,
            query=normalized_query,
            issued_at=issued_at,
            anchor_pinned_sort=anchor_pinned,
            anchor_last_activity_at=anchor_activity,
            anchor_id=anchor_id,
            limit=limit,
        )
        views = tuple(ConversationView(item, pinned_at) for item, pinned_at in rows)
        next_cursor = None
        if has_more and views:
            last = views[-1]
            next_cursor = self._cursor_codec.encode(
                ConversationCursor(
                    filter_digest=filter_digest,
                    issued_at=issued_at,
                    pinned_sort=last.pinned_at or UNPINNED_SORT,
                    last_activity_at=last.conversation.last_activity_at,
                    conversation_id=last.conversation.id,
                )
            )
        return ConversationPage(items=views, next_cursor=next_cursor)

    async def rename_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        title: str,
        expected_revision: int,
    ) -> ConversationView:
        await self._repo.set_title(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            title=self.normalize_title(title),
            expected_revision=expected_revision,
            source=ConversationTitleSource.USER,
        )
        return await self.get_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )

    async def apply_auto_title(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        title: str,
        expected_revision: int,
    ) -> Conversation:
        return await self._repo.set_title(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            title=self.normalize_title(title),
            expected_revision=expected_revision,
            source=ConversationTitleSource.AUTO,
            require_no_title=True,
        )

    async def archive_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
    ) -> ConversationView:
        await self._repo.archive(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
        )
        return await self.get_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )

    async def restore_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        expected_revision: int,
    ) -> ConversationView:
        await self._repo.restore(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            expected_revision=expected_revision,
        )
        return await self.get_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )

    async def set_pinned(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        pinned: bool,
    ) -> ConversationView:
        await self._repo.set_pinned(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            pinned=pinned,
        )
        return await self.get_conversation(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
        )

    async def list_messages(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        before_seq: int | None = None,
        after_seq: int | None = None,
        limit: int = 50,
    ) -> MessagePage:
        if before_seq is not None and after_seq is not None:
            raise ValueError("before_seq and after_seq are mutually exclusive")
        if before_seq is not None and before_seq < 1:
            raise ValueError("before_seq must be positive")
        if after_seq is not None and after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        messages, has_more = await self._repo.list_messages(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            before_seq=before_seq,
            after_seq=after_seq,
            limit=limit,
        )
        return MessagePage(tuple(messages), has_more)

    async def reserve_user_turn(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        conversation_id: uuid.UUID,
        command: TurnCommand,
    ) -> ReservedUserTurn:
        """Persist a turn envelope for contract tests and the future B1 coordinator.

        W1 deliberately does not expose this method through HTTP and does not
        dispatch to an execution context.
        """
        normalized_parts = self._validate_parts(command.parts)
        await self._authorize_resource_references(
            tenant_id=tenant_id,
            actor_id=actor_id,
            parts=normalized_parts,
        )
        digest = build_turn_request_digest(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            client_message_id=command.client_message_id,
            parts=normalized_parts,
            agent_definition_version_id=command.agent_definition_version_id,
            client_options=command.client_options,
        )
        message_id = uuid.uuid4()
        parts = tuple(
            MessagePart(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                message_id=message_id,
                part_seq=index,
                part_type=part.type,
                text_content=part.text,
                content_format=part.format,
                resource_id=part.resource_id,
                media_type=part.media_type,
                display_name=part.display_name,
                digest=message_part_digest(part),
                classification=part.classification,
            )
            for index, part in enumerate(normalized_parts, start=1)
        )
        message, created = await self._repo.reserve_user_turn(
            tenant_id=tenant_id,
            actor_id=actor_id,
            conversation_id=conversation_id,
            message_id=message_id,
            client_message_id=command.client_message_id,
            requested_run_id=uuid.uuid4(),
            turn_request_digest=digest,
            content_digest=message_content_digest(normalized_parts),
            parts=parts,
        )
        if not created and message.turn_request_digest != digest:
            raise IdempotencyConflictError(
                "idempotency key was already used with a different turn command"
            )
        return ReservedUserTurn(message=message, idempotent_replay=not created)

    async def _authorize_resource_references(
        self,
        *,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        parts: Sequence[MessagePartInput],
    ) -> None:
        resource_ids = tuple(
            sorted(
                {
                    part.resource_id
                    for part in parts
                    if part.resource_id is not None
                },
                key=str,
            )
        )
        if not resource_ids:
            return
        if self._resource_access is None:
            raise ResourceReferenceForbiddenError(
                "resource references require an installed authorization adapter"
            )
        allowed = await self._resource_access.can_reference_resources(
            tenant_id=tenant_id,
            actor_id=actor_id,
            resource_ids=resource_ids,
        )
        if not allowed:
            raise ResourceReferenceForbiddenError(
                "one or more resource references are not accessible"
            )

    @staticmethod
    def normalize_title(value: str) -> str:
        clean = "".join(
            char for char in value if not unicodedata.category(char).startswith("C")
        )
        clean = re.sub(r"\s+", " ", clean).strip()
        if not clean:
            raise ValueError("title must not be empty")
        if len(clean) > 200:
            raise ValueError("title must not exceed 200 characters")
        return clean

    @staticmethod
    def normalize_search_query(value: str) -> str:
        clean = "".join(
            char for char in value if not unicodedata.category(char).startswith("C")
        )
        clean = re.sub(r"\s+", " ", clean).strip().casefold()
        if not 2 <= len(clean) <= 100:
            raise ValueError("q must contain between 2 and 100 characters")
        return clean

    @staticmethod
    def _validate_parts(
        parts: Sequence[MessagePartInput],
    ) -> tuple[MessagePartInput, ...]:
        if not parts:
            raise ValueError("a turn must contain at least one message part")
        if len(parts) > MAX_MESSAGE_PARTS:
            raise ValueError(f"a turn may contain at most {MAX_MESSAGE_PARTS} parts")
        normalized: list[MessagePartInput] = []
        total_text_bytes = 0
        for part in parts:
            if part.type is MessagePartType.TEXT:
                if part.text is None or not part.text:
                    raise ValueError("text parts require non-empty text")
                if "\x00" in part.text:
                    raise ValueError("text parts cannot contain NUL characters")
                if part.resource_id is not None:
                    raise ValueError("text parts cannot contain resource_id")
                content_format = part.format or "plain_text"
                if content_format not in {"plain_text", "markdown"}:
                    raise ValueError("text format must be plain_text or markdown")
                total_text_bytes += len(part.text.encode("utf-8"))
                normalized.append(
                    MessagePartInput(
                        type=part.type,
                        text=part.text,
                        format=content_format,
                        classification=part.classification,
                    )
                )
            elif part.type is MessagePartType.RESOURCE_REF:
                if part.resource_id is None:
                    raise ValueError("resource_ref parts require resource_id")
                if part.text is not None or part.format is not None:
                    raise ValueError("resource_ref parts cannot contain text")
                if part.media_type is not None and len(part.media_type) > 100:
                    raise ValueError("media_type must not exceed 100 characters")
                if part.display_name is not None and len(part.display_name) > 255:
                    raise ValueError("display_name must not exceed 255 characters")
                normalized.append(
                    MessagePartInput(
                        type=part.type,
                        resource_id=part.resource_id,
                        media_type=part.media_type,
                        display_name=part.display_name,
                        classification=part.classification,
                    )
                )
            else:
                raise ValueError(f"unsupported message part type: {part.type}")
        if total_text_bytes > MAX_MESSAGE_TEXT_BYTES:
            raise ValueError(
                f"message text exceeds {MAX_MESSAGE_TEXT_BYTES} UTF-8 bytes"
            )
        return tuple(normalized)
