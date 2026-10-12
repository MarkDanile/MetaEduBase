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


class WorkspaceBodyScanNonZeroError(AgentWorkspaceError):
    """R1-S2 S2-D：workspace 正文清除后 final body scan 非零，participant 不得 ACK。

    Spec §5.2/§7.1：只有正文扫描为零才允许 owner ACK；「已执行 DELETE 的受影响
    行数」不构成完成（没有查到正文不是隐式 ACK 的反面——扫到残留正文必须
    fail closed，fence 保持 erasing、记稳定 reason code，由重试/reconcile 处理）。
    """


class IdempotencyConflictError(AgentWorkspaceError):
    pass


class ConversationNotPurgeableError(AgentWorkspaceError):
    """R1-S2 S2-D：会话不满足 purge 前置条件（Spec §3）。

    purge 只能作用于已删除且恢复窗口已过（``now >= purge_after``）、尚未被
    purged（``purged_at IS NULL``）的会话。active/archived 或未到期的会话不得
    被直接擦除--执行器无条件强制该前置，不依赖 scheduler 只 claim 到期行。
    """


class ResourceReferenceForbiddenError(AgentWorkspaceError, PermissionError):
    pass


class TitleSourceConflictError(AgentWorkspaceError):
    pass


class WorkspaceIntegrationConflictError(AgentWorkspaceError):
    """An inbox/outbox replay conflicts with durable workspace facts."""


class AgentDefinitionNotFoundError(AgentWorkspaceError, LookupError):
    """WS-S2 phase-B §3.2-1：租户内不存在该 ``agent_definition_version_id``。

    映射到 phase-A §10 ``422 validation_error``（未知 definition），不是 404：
    会话本身仍存在，失败的是请求体引用的 definition 选择。
    """


class CapabilityDeniedError(AgentWorkspaceError, PermissionError):
    """WS-S2 phase-B §3.2-2：无可服务的 enabled compatibility profile。

    映射到 phase-A §10 ``403 capability_denied``，fail-closed 不降级放行。
    """


class LaunchPolicyInternalError(AgentWorkspaceError):
    """WS-S2 phase-B §3.2-3：构造的 launch 与 profile 登记事实不一致。

    属服务端缺陷（不是客户端错误），映射到 phase-A §10 ``500 internal_error``，
    构造失败即提交失败，绝不返回 2xx。
    """
