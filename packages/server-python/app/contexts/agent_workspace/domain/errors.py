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


class IdempotencyConflictError(AgentWorkspaceError):
    pass


class ResourceReferenceForbiddenError(AgentWorkspaceError, PermissionError):
    pass


class TitleSourceConflictError(AgentWorkspaceError):
    pass


class WorkspaceIntegrationConflictError(AgentWorkspaceError):
    """An inbox/outbox replay conflicts with durable workspace facts."""
