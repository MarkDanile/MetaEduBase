"""TD-085 Slice D (ADR-085-4) boundary tests for ``app.composition.runtime_snapshot``.

Covers:

1. ``snapshot_digest`` re-export equivalence — the composition helper is the
   same function object as ``agent_execution.domain.snapshots.snapshot_digest``
   and produces identical digests on the frozen receipt-tombstone payload
   shape (plus nested / non-ASCII payloads).
2. ``WorkspaceSnapshotAdapter`` structural conformance to
   ``WorkspaceSnapshotPort`` — all 7 port methods exist with matching
   keyword-only parameter names.
3. Fence / legal-hold delegation — the adapter forwards kwargs verbatim to
   the underlying ``AgentErasureRepository`` methods (lock order / fence CAS
   semantics stay in the repository, unchanged).
4. FOR UPDATE lock selects — the three ``lock_*_for_update`` statements are
   the verbatim-moved queries (correct table + full predicate columns +
   ``FOR UPDATE``), executed against the injected session.
5. Default wiring — ``ExecutionErasureParticipant(session)`` constructs a
   ``WorkspaceSnapshotAdapter`` as its workspace snapshot port; the existing
   constructor contract (session-only) is unchanged, and a missing/broken
   adapter would fail closed at import/construction time.
6. Import-graph boundary — AST scan (both ``ast.Import`` and
   ``ast.ImportFrom``) asserting:
   - ``agent_workspace`` → ``agent_execution`` direct imports: 0;
   - ``agent_execution`` → ``agent_workspace`` direct imports: only
     ``app.contexts.agent_workspace.application.ports`` (legal port channel).

Behavioral fence-ledger bilateral invariance, bilateral participant erase /
ACK / blocked semantics and idempotency remain anchored by the existing
hermetic PG suites (``tests/contexts/agent_control_plane/test_s3d_*``,
``tests/composition/test_s4da_*`` 等), which run unchanged. All assertions
below are AST-time / construction-time / mock-session based; none connect to
PG beyond the directory conftest's shared cleanup fixture.
"""

from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.composition.runtime_snapshot import (
    WorkspaceSnapshotAdapter,
    snapshot_digest,
)
from app.contexts.agent_execution.domain.snapshots import (
    snapshot_digest as execution_snapshot_digest,
)
from app.contexts.agent_execution.infrastructure.execution_erasure_participant import (
    EXECUTION_CORE_OWNER,
    ExecutionErasureParticipant,
)
from app.contexts.agent_workspace.application.ports import WorkspaceSnapshotPort
from app.contexts.agent_workspace.domain.erasure import ErasureFenceState

_CONTEXTS_ROOT = Path(__file__).resolve().parents[2] / "app" / "contexts"
_REPO_ROOT = Path(__file__).resolve().parents[2]

_PORT_METHODS = (
    "get_fence_for_update",
    "ensure_fence_under_owner_lock",
    "transition_fence_state",
    "has_active_legal_hold",
    "lock_conversation_for_update",
    "lock_operation_for_update",
    "lock_checkpoint_for_update",
)

_EXECUTION_PREFIX = "app.contexts.agent_execution"
_WORKSPACE_PREFIX = "app.contexts.agent_workspace"
_WORKSPACE_PORTS = "app.contexts.agent_workspace.application.ports"


def _cross_imports(src_dir: Path, target_prefix: str) -> list[str]:
    """AST scan (both ast.Import and ast.ImportFrom) for direct imports whose
    module starts with ``target_prefix``; returns ``path:lineno: module`` hits."""
    hits: list[str] = []
    for path in sorted(src_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(target_prefix):
                        module = alias.name
            elif isinstance(node, ast.ImportFrom) and (
                node.module is not None and node.module.startswith(target_prefix)
            ):
                module = node.module
            if module is not None:
                rel = path.relative_to(_REPO_ROOT)
                hits.append(f"{rel}:{node.lineno}: {module}")
    return hits


# --- 1. snapshot_digest re-export equivalence -----------------------------


def test_snapshot_digest_reexport_identity() -> None:
    """composition helper 与 execution domain 纯函数是同一函数对象。"""
    assert snapshot_digest is execution_snapshot_digest


def test_snapshot_digest_equivalence_on_frozen_payloads() -> None:
    """冻结 receipt tombstone 负载形态 + 嵌套/非 ASCII 负载 digest 等价。"""
    payloads = [
        {
            "schema_version": 1,
            "reason": "purge_erasure",
            "event_id": str(uuid.uuid4()),
        },
        {
            "schema_version": 1,
            "reason": "epoch_unknown_rejected",
            "event_id": "evt-中文-🛡-0042",
        },
        {"a": [1, 2, {"b": None}], "z": {"k": "v", "k2": 35}},
    ]
    for payload in payloads:
        digest = snapshot_digest(payload)
        assert digest == execution_snapshot_digest(payload)
        assert len(digest) == 64
        int(digest, 16)  # hex


# --- 2. adapter structural conformance to WorkspaceSnapshotPort -----------


def test_adapter_surface_matches_workspace_snapshot_port() -> None:
    port_methods = {
        name
        for name, member in inspect.getmembers(
            WorkspaceSnapshotPort, inspect.isfunction
        )
        if not name.startswith("_")
    }
    assert port_methods == set(_PORT_METHODS)
    adapter = WorkspaceSnapshotAdapter(AsyncMock())
    for name in _PORT_METHODS:
        adapter_params = list(inspect.signature(getattr(adapter, name)).parameters)
        port_params = [
            p
            for p in inspect.signature(
                getattr(WorkspaceSnapshotPort, name)
            ).parameters
            if p != "self"
        ]
        # bound adapter method drops ``self``；参数名与顺序须与 port 完全一致
        assert adapter_params == port_params, name


# --- 3. fence / legal-hold delegation -------------------------------------


async def test_adapter_delegates_fence_calls_verbatim() -> None:
    adapter = WorkspaceSnapshotAdapter(AsyncMock())
    adapter._erasure = AsyncMock()
    tenant_id, conversation_id = uuid.uuid4(), uuid.uuid4()

    await adapter.get_fence_for_update(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=EXECUTION_CORE_OWNER,
    )
    adapter._erasure.get_fence_for_update.assert_awaited_once_with(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=EXECUTION_CORE_OWNER,
    )

    await adapter.ensure_fence_under_owner_lock(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=EXECUTION_CORE_OWNER,
    )
    adapter._erasure.ensure_fence_under_owner_lock.assert_awaited_once_with(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=EXECUTION_CORE_OWNER,
    )

    await adapter.transition_fence_state(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=EXECUTION_CORE_OWNER,
        expected_state=ErasureFenceState.ACTIVE,
        expected_revision=3,
        new_state=ErasureFenceState.ERASING,
        purge_revision=2,
        hold_revision=1,
        ack_digest="d" * 64,
    )
    adapter._erasure.transition_fence_state.assert_awaited_once_with(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        owner_key=EXECUTION_CORE_OWNER,
        expected_state=ErasureFenceState.ACTIVE,
        expected_revision=3,
        new_state=ErasureFenceState.ERASING,
        purge_revision=2,
        hold_revision=1,
        ack_digest="d" * 64,
    )

    await adapter.has_active_legal_hold(
        tenant_id=tenant_id, conversation_id=conversation_id
    )
    adapter._erasure.has_active_legal_hold.assert_awaited_once_with(
        tenant_id=tenant_id, conversation_id=conversation_id
    )


# --- 4. FOR UPDATE lock selects（逐字搬迁核验）----------------------------


def _mock_session() -> AsyncMock:
    """execute() 返回配置好的同步 result mock（await 后取 return_value）。"""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    result.scalars.return_value.one_or_none.return_value = None
    session.execute.return_value = result
    return session


def _only_statement(session: AsyncMock) -> str:
    assert session.execute.await_count == 1
    return str(session.execute.await_args_list[0].args[0])


async def test_lock_conversation_for_update_select() -> None:
    session = _mock_session()
    adapter = WorkspaceSnapshotAdapter(session)
    await adapter.lock_conversation_for_update(
        tenant_id=uuid.uuid4(), conversation_id=uuid.uuid4()
    )
    sql = _only_statement(session)
    assert "agent_conversations" in sql
    assert "tenant_id" in sql
    assert "agent_conversations.id" in sql
    assert "FOR UPDATE" in sql


async def test_lock_operation_for_update_select() -> None:
    session = _mock_session()
    adapter = WorkspaceSnapshotAdapter(session)
    await adapter.lock_operation_for_update(
        tenant_id=uuid.uuid4(), purge_operation_id=uuid.uuid4()
    )
    sql = _only_statement(session)
    assert "agent_conversation_purges" in sql
    assert "tenant_id" in sql
    assert "agent_conversation_purges.id" in sql
    assert "FOR UPDATE" in sql


async def test_lock_checkpoint_for_update_select() -> None:
    session = _mock_session()
    adapter = WorkspaceSnapshotAdapter(session)
    await adapter.lock_checkpoint_for_update(
        tenant_id=uuid.uuid4(),
        purge_operation_id=uuid.uuid4(),
        owner_key=EXECUTION_CORE_OWNER,
    )
    sql = _only_statement(session)
    assert "agent_conversation_purge_owners" in sql
    assert "tenant_id" in sql
    assert "purge_operation_id" in sql
    assert "owner_key" in sql
    assert "FOR UPDATE" in sql


# --- 5. 默认 wiring（构造契约不变；缺 wiring 在装配期 fail closed）---------


def test_execution_participant_default_wiring() -> None:
    participant = ExecutionErasureParticipant(AsyncMock())
    assert isinstance(participant._erasure, WorkspaceSnapshotAdapter)
    for name in _PORT_METHODS:
        assert callable(getattr(participant._erasure, name))


# --- 6. import graph 边界（AST 双形式扫描）--------------------------------


def test_workspace_does_not_import_execution() -> None:
    hits = _cross_imports(
        _CONTEXTS_ROOT / "agent_workspace", _EXECUTION_PREFIX
    )
    assert hits == []


def test_execution_imports_workspace_only_via_application_ports() -> None:
    hits = _cross_imports(
        _CONTEXTS_ROOT / "agent_execution", _WORKSPACE_PREFIX
    )
    illegal = [
        hit
        for hit in hits
        if hit.rsplit(": ", 1)[1] != _WORKSPACE_PORTS
    ]
    assert illegal == []
