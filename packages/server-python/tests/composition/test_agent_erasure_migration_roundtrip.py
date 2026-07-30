"""034 erasure foundation migration upgrade/downgrade/upgrade 往返。

独立成模块并在其他 erasure schema 测试之后运行，避免迁移往返影响同进程
其他 DB 依赖测试（与 ``test_agent_erasure_schema.py`` 中的表/列存在性断言分离）。
"""

from __future__ import annotations

import asyncio
import warnings
from pathlib import Path

import asyncpg
from alembic.config import Config

from alembic import command
from app.config import settings
from tests.conftest import TEST_DB_URL

SERVER_ROOT = Path(__file__).resolve().parents[2]
COORD_TABLES = {
    "agent_erasure_fences",
    "agent_conversation_purges",
    "agent_conversation_purge_owners",
    "agent_conversation_legal_holds",
}

# downgrade 会把 tombstone 放宽的列还原为 NOT NULL；含 tombstone（NULL 正文）的
# 遗留行会破坏还原。往返前清空携带 tombstone 的表与 coordination 表。
_CLEAN_TABLES = (
    "agent_conversation_legal_holds",
    "agent_conversation_purge_owners",
    "agent_conversation_purges",
    "agent_erasure_fences",
    "agent_compatibility_outputs",
    "agent_run_events",
    "agent_turn_inputs",
    "agent_execution_inbox",
    "agent_execution_outbox",
    "agent_runs",
    "agent_workspace_inbox",
    "agent_workspace_outbox",
    "agent_message_parts",
    "agent_messages",
    "agent_conversation_user_state",
    "agent_conversations",
)


def _db_url() -> str:
    return TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://", 1)


def _sqlalchemy_url() -> str:
    return _db_url().replace("postgresql://", "postgresql+asyncpg://", 1)


def _run_alembic(direction: str, revision: str) -> None:
    original_url = settings.database_url
    settings.database_url = _sqlalchemy_url()
    try:
        config = Config(str(SERVER_ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(SERVER_ROOT / "alembic"))
        fn = command.upgrade if direction == "upgrade" else command.downgrade
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fn(config, revision)
    finally:
        settings.database_url = original_url


async def _existing_coord_tables() -> set[str]:
    connection = await asyncpg.connect(_db_url())
    try:
        rows = await connection.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='metaedu' AND table_name = ANY($1::text[])",
            list(COORD_TABLES),
        )
        return {row["table_name"] for row in rows}
    finally:
        await connection.close()


def test_034_downgrade_upgrade_round_trip():
    asyncio.run(_clean_tombstone_tables())
    try:
        _run_alembic("downgrade", "033_agent_compat_output")
        assert asyncio.run(_existing_coord_tables()) == set()
    finally:
        _run_alembic("upgrade", "head")
    assert asyncio.run(_existing_coord_tables()) == COORD_TABLES


async def _clean_tombstone_tables() -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        await connection.execute(
            "TRUNCATE TABLE " + ", ".join(f"metaedu.{t}" for t in _CLEAN_TABLES)
        )
    finally:
        await connection.close()


# ---------------------------------------------------------------------------
# round-6 P2-4：037 system_key_fingerprints 专属迁移回归
# ---------------------------------------------------------------------------

_037_TABLE = "system_key_fingerprints"


async def _system_key_fingerprint_schema() -> dict:
    """返回 037 表的存在性 + PK + CHECK 约束名集合。"""
    connection = await asyncpg.connect(_db_url())
    try:
        exists = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='metaedu' AND table_name=$1)",
            _037_TABLE,
        )
        if not exists:
            return {"exists": False, "constraints": set()}
        rows = await connection.fetch(
            "SELECT conname FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname='metaedu' "
            "AND c.conrelid = $1::regclass",
            f"metaedu.{_037_TABLE}",
        )
        return {"exists": True, "constraints": {r["conname"] for r in rows}}
    finally:
        await connection.close()


def test_037_system_key_fingerprints_downgrade_upgrade_round_trip():
    """round-6 P2-4：037 真实 downgrade->upgrade--表 + PK + CHECK 重建。

    037 是纯 expand（新建表），downgrade drop_table，upgrade recreate。
    验证：(1) head 状态表存在且含 pk + check 约束；(2) downgrade 到 036 表消失；
    (3) upgrade 回 head 表重建且约束齐全。
    """
    # head 状态：表存在 + PK + CHECK。
    schema = asyncio.run(_system_key_fingerprint_schema())
    assert schema["exists"], "system_key_fingerprints should exist at head"
    assert "pk_system_key_fingerprints" in schema["constraints"]
    assert "ck_system_key_fingerprints_fingerprint" in schema["constraints"]

    try:
        _run_alembic("downgrade", "036_erasure_fence_empty_ingress")
        schema = asyncio.run(_system_key_fingerprint_schema())
        assert not schema["exists"], (
            "system_key_fingerprints should be dropped after downgrade to 036"
        )
    finally:
        _run_alembic("upgrade", "head")

    # upgrade 回 head：表 + 约束重建。
    schema = asyncio.run(_system_key_fingerprint_schema())
    assert schema["exists"], "system_key_fingerprints should exist after upgrade to head"
    assert "pk_system_key_fingerprints" in schema["constraints"]
    assert "ck_system_key_fingerprints_fingerprint" in schema["constraints"]


_038_TABLES = ("agent_runs", "agent_turn_inputs")


async def _execution_actor_schema() -> dict:
    """返回 038 actor tombstone 列 + CHECK 约束状态（每表）。"""
    connection = await asyncpg.connect(_db_url())
    try:
        result: dict = {}
        for table in _038_TABLES:
            cols = await connection.fetch(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema='metaedu' AND table_name=$1 "
                "AND column_name IN ('actor_state', 'actor_identity_digest', 'created_by')",
                table,
            )
            result[table] = {r["column_name"]: r["is_nullable"] for r in cols}
            rows = await connection.fetch(
                "SELECT conname FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname='metaedu' AND c.conrelid = $1::regclass "
                "AND c.contype='c'",
                f"metaedu.{table}",
            )
            result[f"{table}_checks"] = {r["conname"] for r in rows}
        return result
    finally:
        await connection.close()


def test_038_execution_actor_tombstone_downgrade_upgrade_round_trip():
    """S3-B：038 真实 downgrade->upgrade--actor_state/digest 列 + CHECK 重建。

    验证：(1) head 状态 agent_runs/agent_turn_inputs 含 actor_state/
    actor_identity_digest 列 + created_by nullable + ck_*_actor CHECK；
    (2) downgrade 到 037 列消失、created_by NOT NULL、CHECK 消失；
    (3) upgrade 回 head 列 + CHECK 重建。
    """
    schema = asyncio.run(_execution_actor_schema())
    for table in _038_TABLES:
        assert "actor_state" in schema[table], f"{table} missing actor_state"
        assert "actor_identity_digest" in schema[table], f"{table} missing digest"
        assert schema[table]["created_by"] == "YES", f"{table} created_by should be nullable"
        assert f"ck_{table}_actor" in schema[f"{table}_checks"], f"{table} missing ck_actor"

    try:
        _run_alembic("downgrade", "037_system_key_fingerprints")
        schema = asyncio.run(_execution_actor_schema())
        for table in _038_TABLES:
            assert "actor_state" not in schema[table], f"{table} actor_state should be dropped"
            assert "actor_identity_digest" not in schema[table], f"{table} digest should be dropped"
            assert schema[table]["created_by"] == "NO", f"{table} created_by should be NOT NULL"
            assert f"ck_{table}_actor" not in schema[f"{table}_checks"], (
                f"{table} ck_actor should be dropped"
            )
    finally:
        _run_alembic("upgrade", "head")

    schema = asyncio.run(_execution_actor_schema())
    for table in _038_TABLES:
        assert "actor_state" in schema[table]
        assert "actor_identity_digest" in schema[table]
        assert schema[table]["created_by"] == "YES"
        assert f"ck_{table}_actor" in schema[f"{table}_checks"]


async def _seed_redacted_run() -> tuple:
    """插入一个 redacted Run（含 FK 链：definition + profile + run），返回 (run, tenant)。

    使用 'queued' 非 terminal 状态避免 terminal envelope CHECK；redacted 满足
    ck_agent_runs_actor（created_by NULL + actor_state redacted + 64-hex digest）。
    """
    import uuid as _uuid

    connection = await asyncpg.connect(_db_url())
    tid = _uuid.uuid4()
    def_id = _uuid.uuid4()
    prof_id = _uuid.uuid4()
    run_id = _uuid.uuid4()
    digest = "a" * 64
    try:
        await connection.execute(
            "INSERT INTO metaedu.agent_definition_versions "
            "(id, tenant_id, definition_key, version, status, "
            "definition_digest, created_by, created_at) "
            "VALUES ($1, $2, $3, 1, 'published', $4, $2, now())",
            def_id, tid, f"def-{tid}", digest,
        )
        await connection.execute(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            "capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES ($1, $2, $3, 'compatibility', 'compatibility', $4, $4, true, 1, now(), now())",
            prof_id, tid, f"prof-{tid}", digest,
        )
        await connection.execute(
            "INSERT INTO metaedu.agent_runs "
            "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            "agent_definition_version_id, runtime_profile_id, creation_digest, status, "
            "status_revision, next_event_seq, first_available_event_seq, last_event_seq, "
            "event_log_complete, queued_at, output_publish_state, created_by, actor_state, "
            "actor_identity_digest, correlation_id, runtime_capability_snapshot, "
            "run_config_snapshot, budget_snapshot, usage_summary) "
            "VALUES ($1, $2, $1, 1, $1, $3, $4, $5, 'queued', 1, 1, 1, 0, true, now(), "
            "'not_required', NULL, 'redacted', $5, $1, '{}'::jsonb, '{}'::jsonb, "
            "'{}'::jsonb, '{}'::jsonb)",
            run_id, tid, def_id, prof_id, digest,
        )
        return run_id, tid
    finally:
        await connection.close()


async def _cleanup_redacted_run(tid) -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        await connection.execute(
            "DELETE FROM metaedu.agent_runs WHERE tenant_id=$1", tid
        )
        await connection.execute(
            "DELETE FROM metaedu.agent_runtime_profiles WHERE tenant_id=$1", tid
        )
        await connection.execute(
            "DELETE FROM metaedu.agent_definition_versions WHERE tenant_id=$1", tid
        )
    finally:
        await connection.close()


def test_038_downgrade_fail_closed_on_redacted_rows():
    """S3-B round-2 P2-3：anonymization 后 downgrade 必须 fail closed（不伪造 UUID）。

    插入 redacted Run 后 downgrade 应 raise；清理 redacted 行后 downgrade 才成功。
    """
    run_id, tid = asyncio.run(_seed_redacted_run())
    try:
        # redacted 行存在 -> downgrade 必须 fail closed。
        raised = False
        try:
            _run_alembic("downgrade", "037_system_key_fingerprints")
        except Exception:
            raised = True
        assert raised, (
            "downgrade must fail closed when redacted rows exist "
            "(irreversible anonymization)"
        )
        # 确认仍在 head（038），downgrade 未执行。
        schema = asyncio.run(_execution_actor_schema())
        assert "actor_state" in schema["agent_runs"], "still at head after fail-closed downgrade"
    finally:
        asyncio.run(_cleanup_redacted_run(tid))

    # 清理 redacted 行后 downgrade 成功（reversible path）。
    try:
        _run_alembic("downgrade", "037_system_key_fingerprints")
        schema = asyncio.run(_execution_actor_schema())
        assert "actor_state" not in schema["agent_runs"], (
            "actor_state dropped after clean downgrade"
        )
    finally:
        _run_alembic("upgrade", "head")


async def _seed_redacted_turn_input(run_id, tid) -> None:
    """为既有 Run 追加一个 redacted root TurnInput（FK 链：run -> turn_input）。"""
    connection = await asyncpg.connect(_db_url())
    digest = "a" * 64
    try:
        await connection.execute(
            "INSERT INTO metaedu.agent_turn_inputs "
            "(id, tenant_id, run_id, ordinal, input_kind, message_id, request_id, "
            "expected_runtime_epoch, context_digest, created_by, actor_state, "
            "actor_identity_digest, created_at) "
            "VALUES (gen_random_uuid(), $1, $2, 0, 'root', "
            "gen_random_uuid(), gen_random_uuid(), NULL, $3, "
            "NULL, 'redacted', $3, now())",
            tid, run_id, digest,
        )
    finally:
        await connection.close()


async def _cleanup_redacted_turn_input(tid) -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        await connection.execute(
            "DELETE FROM metaedu.agent_turn_inputs WHERE tenant_id=$1", tid
        )
    finally:
        await connection.close()


def test_038_downgrade_fail_closed_on_redacted_turn_input() -> None:
    """S3-B round-3 P2-4：redacted TurnInput 同样阻止 downgrade（与 agent_runs 同源）。"""
    run_id, tid = asyncio.run(_seed_redacted_run())
    try:
        asyncio.run(_seed_redacted_turn_input(run_id, tid))
        raised = False
        try:
            _run_alembic("downgrade", "037_system_key_fingerprints")
        except Exception:
            raised = True
        assert raised, (
            "downgrade must fail closed when redacted TurnInput rows exist"
        )
        schema = asyncio.run(_execution_actor_schema())
        assert "actor_state" in schema["agent_turn_inputs"], (
            "still at head after fail-closed downgrade (turn_input)"
        )
    finally:
        asyncio.run(_cleanup_redacted_turn_input(tid))
        asyncio.run(_cleanup_redacted_run(tid))

    # 清理 redacted 行后 downgrade 成功。
    try:
        _run_alembic("downgrade", "037_system_key_fingerprints")
        schema = asyncio.run(_execution_actor_schema())
        assert "actor_state" not in schema["agent_turn_inputs"]
    finally:
        _run_alembic("upgrade", "head")


def test_038_actor_digest_must_be_lowercase_hex() -> None:
    """S3-B round-3 P1-2：actor_identity_digest CHECK 强制 lowercase 64-hex。

    PostgreSQL 真实反例：长度 64 但含非 hex 字符（含大写 Z）应被 CHECK 拒绝。
    """
    import uuid as _uuid

    connection = asyncpg.connect(_db_url())

    async def _setup_and_attempt(digest_value: str, *, table: str, fk_col: str) -> str:
        conn = await connection
        try:
            if table == "agent_runs":
                # 复用既有 _seed_redacted_run 的 FK 链
                run_id, tid, _def_id = await _seed_redacted_run()
                await conn.execute(
                    "DELETE FROM metaedu.agent_runs WHERE tenant_id=$1", tid
                )
                return run_id, tid
            return None, None
        finally:
            await conn.close()

    async def _try_redacted_insert_redacted_run(digest_value: str) -> None:
        """尝试向 agent_runs 插入非 hex digest，期望 CHECK 拒绝。"""
        conn = await asyncpg.connect(_db_url())
        try:
            tid = _uuid.uuid4()
            def_id = _uuid.uuid4()
            prof_id = _uuid.uuid4()
            creation_digest = "a" * 64
            await conn.execute(
                "INSERT INTO metaedu.agent_definition_versions "
                "(id, tenant_id, definition_key, version, status, definition_digest, "
                "created_by, created_at) "
                "VALUES ($1, $2, $3, 1, 'published', $4, $2, now())",
                def_id, tid, f"def-{tid}", creation_digest,
            )
            await conn.execute(
                "INSERT INTO metaedu.agent_runtime_profiles "
                "(id, tenant_id, profile_key, runtime_kind, adapter_key, "
                "config_digest, capability_digest, enabled, revision, "
                "created_at, updated_at) "
                "VALUES ($1, $2, $3, 'compatibility', 'compatibility', $4, $4, "
                "true, 1, now(), now())",
                prof_id, tid, f"prof-{tid}", creation_digest,
            )
            try:
                await conn.execute(
                    "INSERT INTO metaedu.agent_runs "
                    "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
                    "agent_definition_version_id, runtime_profile_id, creation_digest, "
                    "status, status_revision, next_event_seq, first_available_event_seq, "
                    "last_event_seq, event_log_complete, queued_at, output_publish_state, "
                    "created_by, actor_state, actor_identity_digest, correlation_id, "
                    "runtime_capability_snapshot, run_config_snapshot, budget_snapshot, "
                    "usage_summary) "
                    "VALUES ($1, $2, $1, 1, $1, $3, $4, $5, 'queued', 1, 1, 1, 0, true, "
                    "now(), 'not_required', NULL, 'redacted', $6, $1, '{}'::jsonb, "
                    "'{}'::jsonb, '{}'::jsonb, '{}'::jsonb)",
                    _uuid.uuid4(),
                    tid,
                    def_id,
                    prof_id,
                    creation_digest,
                    digest_value,
                )
                return False  # 未被拒绝 -> 失败
            except asyncpg.exceptions.CheckViolationError:
                return True  # 被 CHECK 拒绝 -> 通过
            finally:
                await conn.execute(
                    "DELETE FROM metaedu.agent_runs WHERE tenant_id=$1", tid
                )
                await conn.execute(
                    "DELETE FROM metaedu.agent_runtime_profiles WHERE tenant_id=$1",
                    tid,
                )
                await conn.execute(
                    "DELETE FROM metaedu.agent_definition_versions WHERE tenant_id=$1",
                    tid,
                )
        finally:
            await conn.close()

    async def _try_redacted_insert_redacted_turn_input(digest_value: str) -> bool:
        """尝试向 agent_turn_inputs 插入非 hex digest，期望 CHECK 拒绝。"""
        # 先 seed 一个合法 Run 取得 FK
        run_id, tid = await _seed_redacted_run()
        conn = await asyncpg.connect(_db_url())
        try:
            try:
                await conn.execute(
                    "INSERT INTO metaedu.agent_turn_inputs "
                    "(id, tenant_id, run_id, ordinal, input_kind, message_id, "
                    "request_id, expected_runtime_epoch, context_digest, created_by, "
                    "actor_state, actor_identity_digest, created_at) "
                    "VALUES (gen_random_uuid(), $1, $2, 1, 'steer', "
                    "gen_random_uuid(), gen_random_uuid(), 1, 'a' || repeat('a', 63), "
                    "NULL, 'redacted', $3, now())",
                    tid,
                    run_id,
                    digest_value,
                )
                return False
            except asyncpg.exceptions.CheckViolationError:
                return True
        finally:
            await conn.close()
            await _cleanup_redacted_run(tid)

    # "z"*64：长度对但含非 hex 字符（'z' 非 [0-9a-f]）— round-3 P1-2 反例。
    bad_z = "z" * 64
    # "A"*64：长度对但大写 — round-3 P1-2 反例。
    bad_upper = "A" * 64

    # 反例：长度 64 但非 hex 必须被 CHECK 拒绝。
    assert asyncio.run(_try_redacted_insert_redacted_run(bad_z)), (
        "agent_runs: 'z'*64 must fail ck_agent_runs_actor (not lowercase hex)"
    )
    assert asyncio.run(_try_redacted_insert_redacted_run(bad_upper)), (
        "agent_runs: 'A'*64 must fail (uppercase hex rejected)"
    )

    # TurnInput 同源 CHECK。
    assert asyncio.run(_try_redacted_insert_redacted_turn_input(bad_z)), (
        "agent_turn_inputs: 'z'*64 must fail ck_agent_turn_inputs_actor"
    )
    assert asyncio.run(_try_redacted_insert_redacted_turn_input(bad_upper)), (
        "agent_turn_inputs: 'A'*64 must fail (uppercase rejected)"
    )
