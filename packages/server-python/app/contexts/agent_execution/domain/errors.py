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


class RunRevisionConflictError(RunConflictError):
    """A Run command used a stale status revision."""


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
