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
