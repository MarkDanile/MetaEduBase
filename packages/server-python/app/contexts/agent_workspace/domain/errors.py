class AgentWorkspaceError(Exception):
    """Base class for stable Agent Workspace command failures."""


class ConversationNotFoundError(AgentWorkspaceError, LookupError):
    pass


class ConversationIdConflictError(AgentWorkspaceError):
    pass


class RevisionConflictError(AgentWorkspaceError):
    pass


class InvalidConversationStateError(AgentWorkspaceError):
    pass


class ConversationPurgedError(AgentWorkspaceError):
    pass


class ConversationRecoveryExpiredError(AgentWorkspaceError):
    pass


class ConversationPurgeInProgressError(AgentWorkspaceError):
    pass


class ConversationRestoreNotAllowedError(AgentWorkspaceError):
    """Restore 的安全账本不完整或不可信（fence 缺失/未知 owner/版本漂移）。"""


class DeletedConversationListingError(AgentWorkspaceError):
    """公开 list/search 不接受 deleted 状态过滤。

    R1-S2 S2-C P1-3 复审：`state=deleted` 的 list/search 会返回原始 title 并对
    `MessagePart.text_content` 求值，泄露已删除会话的标题与正文匹配关系，违反
    deleted/purged fail-closed 契约。deleted 会话的恢复走
    `get_conversation(include_deleted=True)` 的 redacted tombstone 路径（已知
    UUID、不搜索正文），不走列表/搜索。
    """


class LateBodyWriteRejectedError(AgentWorkspaceError):
    """正文 writer 在 owner fence 非 active（purge 进行中/已完成）时写正文被拒。"""


class IdempotencyConflictError(AgentWorkspaceError):
    pass


class ResourceReferenceForbiddenError(AgentWorkspaceError, PermissionError):
    pass


class TitleSourceConflictError(AgentWorkspaceError):
    pass


class WorkspaceIntegrationConflictError(AgentWorkspaceError):
    """An inbox/outbox replay conflicts with durable workspace facts."""
