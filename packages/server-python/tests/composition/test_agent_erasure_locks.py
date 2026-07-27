from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from app.composition.agent_control_plane import conversation_guard_key

SERVER_ROOT = Path(__file__).resolve().parents[2]

_TENANT = uuid.UUID("11111111-2222-3333-4444-555555555555")
_CONVERSATION = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_OWNER = "workspace.core.v1"

_PREFIX = b"metaedu.agent.owner.v1\x00"


def _reference_owner_key(
    tenant_id: uuid.UUID, conversation_id: uuid.UUID, owner_key: str
) -> int:
    material = (
        _PREFIX
        + tenant_id.bytes
        + conversation_id.bytes
        + b"\x00"
        + owner_key.encode("utf-8")
    )
    return int.from_bytes(
        hashlib.sha256(material).digest()[:8], byteorder="big", signed=True
    )


def _expected_material() -> bytes:
    return (
        _PREFIX
        + _TENANT.bytes
        + _CONVERSATION.bytes
        + b"\x00"
        + _OWNER.encode("utf-8")
    )


def _expected_value() -> int:
    return int.from_bytes(
        hashlib.sha256(_expected_material()).digest()[:8],
        byteorder="big",
        signed=True,
    )


def test_owner_key_matches_golden_vector() -> None:
    from app.composition.agent_erasure_locks import conversation_owner_key

    assert conversation_owner_key(
        tenant_id=_TENANT, conversation_id=_CONVERSATION, owner_key=_OWNER
    ) == _expected_value()


def test_owner_key_is_signed_64_bit() -> None:
    from app.composition.agent_erasure_locks import conversation_owner_key

    value = conversation_owner_key(
        tenant_id=_TENANT, conversation_id=_CONVERSATION, owner_key=_OWNER
    )
    assert isinstance(value, int)
    assert -(2**63) <= value <= 2**63 - 1


def test_owner_key_is_deterministic() -> None:
    from app.composition.agent_erasure_locks import conversation_owner_key

    first = conversation_owner_key(
        tenant_id=_TENANT, conversation_id=_CONVERSATION, owner_key=_OWNER
    )
    second = conversation_owner_key(
        tenant_id=_TENANT, conversation_id=_CONVERSATION, owner_key=_OWNER
    )
    assert first == second


def test_owner_key_differs_from_guard_key() -> None:
    from app.composition.agent_erasure_locks import conversation_owner_key

    owner = conversation_owner_key(
        tenant_id=_TENANT, conversation_id=_CONVERSATION, owner_key=_OWNER
    )
    guard = conversation_guard_key(_TENANT, _CONVERSATION)
    assert owner != guard


def test_owner_key_varies_with_owner_key() -> None:
    from app.composition.agent_erasure_locks import conversation_owner_key

    base = conversation_owner_key(
        tenant_id=_TENANT, conversation_id=_CONVERSATION, owner_key="workspace.core.v1"
    )
    other = conversation_owner_key(
        tenant_id=_TENANT,
        conversation_id=_CONVERSATION,
        owner_key="execution.core.v1",
    )
    assert base != other


def test_owner_key_rejects_empty_owner_key() -> None:
    from app.composition.agent_erasure_locks import conversation_owner_key

    with pytest.raises(ValueError):
        conversation_owner_key(
            tenant_id=_TENANT, conversation_id=_CONVERSATION, owner_key=""
        )


def test_owner_key_stable_across_processes() -> None:
    # 在独立子进程中重算并断言与 golden vector 一致：证明 SHA-256 + 固定
    # canonical bytes 的派生跨进程确定。子进程经 PYTHONPATH=SERVER_ROOT
    # 解析 namespace 包 ``app``（与 pytest rootdir 机制一致）。
    code = (
        "import uuid;"
        "from app.composition.agent_erasure_locks import conversation_owner_key;"
        "print(conversation_owner_key("
        f"tenant_id=uuid.UUID('{_TENANT}'),"
        f"conversation_id=uuid.UUID('{_CONVERSATION}'),"
        f"owner_key='{_OWNER}'))"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SERVER_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=SERVER_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(_expected_value())
