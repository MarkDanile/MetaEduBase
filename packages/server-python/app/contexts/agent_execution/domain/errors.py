class AgentExecutionError(Exception):
    """Base error for the Agent execution context."""


class CatalogConflictError(AgentExecutionError):
    """A stable catalog key was reused with different immutable content."""


class CatalogNotFoundError(AgentExecutionError):
    """The requested tenant-scoped catalog entry does not exist."""


class RuntimeProfileDisabledError(AgentExecutionError):
    """The selected Runtime profile is disabled."""


class RuntimeBindingNotFoundError(AgentExecutionError):
    """The requested tenant-scoped Runtime binding does not exist."""


class RuntimeBindingConflictError(AgentExecutionError):
    """A Runtime binding lifecycle or revision precondition failed."""


class RuntimeEpochMismatchError(AgentExecutionError):
    """A stale Runtime owner attempted to use a fenced binding epoch."""


class RuntimeStreamLeaseConflictError(AgentExecutionError):
    """Another ingest stream still owns the binding lease."""


class RuntimeSequenceGapError(AgentExecutionError):
    def __init__(self, *, expected: int, received: int):
        self.expected = expected
        self.received = received
        super().__init__(
            f"runtime sequence gap: expected {expected}, received {received}"
        )


class RuntimeEventConflictError(AgentExecutionError):
    """A replayed Runtime sequence conflicts with its persisted receipt."""


class InvalidRuntimeProvenanceError(AgentExecutionError):
    """Runtime provenance is partial, malformed, or crosses a control boundary."""


class RunNotFoundError(AgentExecutionError):
    """The requested tenant-scoped Agent Run does not exist."""


class RunConflictError(AgentExecutionError):
    """A Run idempotency, revision, FIFO, or ownership precondition failed."""


class LateOutputReadRejectedError(RunConflictError):
    """R1-S3-E round-2：purge 已清除 terminal/compatibility 正文，迟到的 output
    publish 无法再读取正文——deterministic（重试永远无法成功），不可走 transient
    backoff 重试。

    与 workspace 侧 ``LateBodyWriteRejectedError``（fence 非 active 拒写）同语义：
    二者都表示「Conversation 已在 purge，迟到 publish 永不成功」。dispatcher 对二者
    统一 deterministic terminalize（outbox cancelled + late_body_write_rejected +
    不重试）。
    """


class RunRevisionConflictError(RunConflictError):
    """A Run command used a stale status revision."""


class RunActorAnonymizedError(RunConflictError):
    """S3-B round-2 P1-4：需 actor 的命令遇到已匿名化（tombstone）Run/TurnInput。

    ``created_by`` 已被 purge 清除（``actor_state=redacted`` + 不可逆 digest），
    需要 live actor 的命令 fail closed，不伪造 actor、不暴露 digest。
    """


class RunConversationMismatchError(AgentExecutionError):
    """R1-S3-C round-7：caller 传的 Run 身份与实际 Run 不一致。

    Wrapper 入口校验：
    - ``tenant_id / conversation_id / run_id`` 三元组与 ``AgentRun`` 自身字段不一致
    - ``queue_seq`` 与 ``AgentRun.queue_seq`` 不一致（仅 fenced_create_run /
      fenced_commit_terminal / fenced_stage 涉及 queue_seq）
    - ``fenced_ingest_runtime_event``：``command.frame.tenant_id / run_id`` 与
      外层 ``tenant_id / run_id`` 不一致

    防止用 Conversation A 的 active fence 授权 Conversation B 的 writer。
    """


class RuntimeIngestIdentityMismatchError(AgentExecutionError):
    """R1-S3-C round-7：``fenced_ingest_runtime_event`` 的 frame 身份与外层不一致。

    ``command.frame.tenant_id / frame.run_id`` 必须等于外层
    ``tenant_id / run_id``，避免 Runtime 通道绕过 fenced port 的归属校验。
    """


class InvalidRunTransitionError(AgentExecutionError):
    """The requested Agent Run state transition is not allowed."""


class RunGuardBlockedError(AgentExecutionError):
    """Durable Tool/Input/Approval state prevents a Run transition."""


class UnsupportedRunCapabilitiesError(AgentExecutionError):
    """The Run requests capabilities whose durable stores are not installed."""


class RunEventConflictError(AgentExecutionError):
    """A RunEvent identity, sequence, or immutable digest conflicts."""


class RunEventPayloadError(AgentExecutionError):
    """A RunEvent payload violates version, size, or classification policy."""


class EventHistoryExpiredError(AgentExecutionError):
    def __init__(
        self,
        *,
        first_available_event_seq: int,
        run_status: str,
        event_log_complete: bool,
    ):
        self.first_available_event_seq = first_available_event_seq
        self.run_status = run_status
        self.event_log_complete = event_log_complete
        super().__init__("requested event history is no longer available")


class EventCursorAheadError(AgentExecutionError):
    def __init__(self, *, after_seq: int, last_event_seq: int):
        self.after_seq = after_seq
        self.last_event_seq = last_event_seq
        super().__init__(
            f"event cursor {after_seq} is ahead of last issued seq {last_event_seq}"
        )


class EventGapDetectedError(AgentExecutionError):
    def __init__(self, *, expected_seq: int, received_seq: int | None):
        self.expected_seq = expected_seq
        self.received_seq = received_seq
        super().__init__(
            f"event gap detected at seq {expected_seq}; received {received_seq}"
        )


class TerminalResultConflictError(AgentExecutionError):
    """A terminal result conflicts with an already persisted result."""


class ExecutionIntegrationConflictError(AgentExecutionError):
    """An inbox/outbox replay conflicts with durable execution facts."""
