"""034 erasure foundation migration upgrade/downgrade/upgrade 往返。

独立成模块并在其他 erasure schema 测试之后运行，避免迁移往返影响同进程
其他 DB 依赖测试（与 ``test_agent_erasure_schema.py`` 中的表/列存在性断言分离）。
"""

from __future__ import annotations

import asyncio
import json
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


async def _seed_present_run() -> tuple:
    """插入一个 present Run（含 FK 链：definition + profile + run），返回 (run, tenant)。

    使用 'queued' 非 terminal 状态避免 terminal envelope CHECK；created_by 非空 +
    actor_state='present' + digest NULL（满足 ck_agent_runs_actor present 分支）。
    供 TurnInput redacted downgrade 隔离测试使用——父 Run 保持 present，使
    downgrade 失败仅由 TurnInput 分支触发。
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
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            "created_by, created_at) "
            "VALUES ($1, $2, $3, 1, 'published', $4, $2, now())",
            def_id, tid, f"def-{tid}", digest,
        )
        await connection.execute(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            "capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES ($1, $2, $3, 'compatibility', 'compatibility', $4, $4, "
            "true, 1, now(), now())",
            prof_id, tid, f"prof-{tid}", digest,
        )
        creator_id = _uuid.uuid4()
        await connection.execute(
            "INSERT INTO metaedu.agent_runs "
            "(id, tenant_id, conversation_id, queue_seq, root_input_message_id, "
            "agent_definition_version_id, runtime_profile_id, creation_digest, status, "
            "status_revision, next_event_seq, first_available_event_seq, last_event_seq, "
            "event_log_complete, queued_at, output_publish_state, created_by, actor_state, "
            "actor_identity_digest, correlation_id, runtime_capability_snapshot, "
            "run_config_snapshot, budget_snapshot, usage_summary) "
            "VALUES ($1, $2, $1, 1, $1, $3, $4, $5, 'queued', 1, 1, 1, 0, true, now(), "
            "'not_required', $6, 'present', NULL, $1, '{}'::jsonb, '{}'::jsonb, "
            "'{}'::jsonb, '{}'::jsonb)",
            run_id, tid, def_id, prof_id, digest, creator_id,
        )
        return run_id, tid
    finally:
        await connection.close()


async def _cleanup_present_run(tid) -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        await connection.execute(
            "DELETE FROM metaedu.agent_turn_inputs WHERE tenant_id=$1", tid
        )
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
    """S3-B round-4 P2-3：redacted TurnInput 阻止 downgrade，父 Run 保持 present。

    round-3 版本用 ``_seed_redacted_run()`` 创建 redacted 父 Run，downgrade
    失败总是被父 Run 触发，不验证 TurnInput 分支。本测试改用 present 父 Run
    + 仅 TurnInput redacted，downgrade 失败仅由 TurnInput 分支触发。
    """
    run_id, tid = asyncio.run(_seed_present_run())
    try:
        asyncio.run(_seed_redacted_turn_input(run_id, tid))
        raised = False
        try:
            _run_alembic("downgrade", "037_system_key_fingerprints")
        except Exception:
            raised = True
        assert raised, (
            "downgrade must fail closed when redacted TurnInput rows exist "
            "(with present parent Run)"
        )
        schema = asyncio.run(_execution_actor_schema())
        assert "actor_state" in schema["agent_turn_inputs"], (
            "still at head after fail-closed downgrade (turn_input)"
        )
    finally:
        asyncio.run(_cleanup_present_run(tid))

    # 清理 redacted TurnInput 后 downgrade 成功。
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


# ---------------------------------------------------------------------------
# 042 lease carrier（R1-S5 SCH-A）upgrade/downgrade/upgrade 往返
# ---------------------------------------------------------------------------


async def _lease_carrier_schema() -> dict:
    """042 的列与 partial index 存在性（information_schema + pg_indexes）。"""
    connection = await asyncpg.connect(_db_url())
    try:
        column = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'metaedu' "
            "AND table_name = 'agent_conversation_purges' "
            "AND column_name = 'lease_expires_at')"
        )
        index = await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_indexes "
            "WHERE schemaname = 'metaedu' "
            "AND tablename = 'agent_conversation_purges' "
            "AND indexname = 'ix_agent_purge_lease_active')"
        )
        return {"column": bool(column), "index": bool(index)}
    finally:
        await connection.close()


async def _seed_lease_carrier_row() -> str:
    """种子一行 operation（lease_expires_at 未写入 = NULL），模拟既有行。"""
    connection = await asyncpg.connect(_db_url())
    try:
        tid = "73000000-0000-0000-0000-000000000042"
        cid = "73000000-0000-0000-0000-000000000043"
        await connection.execute(
            "INSERT INTO metaedu.agent_conversations "
            "(id, tenant_id, created_by, actor_state, creation_digest, title, "
            "title_source, state, purge_after, purge_state, purge_revision, "
            "hold_revision, revision, created_at, updated_at) "
            "VALUES ($1, $2, $2, 'present', $3, 't', 'none', 'deleted', "
            "now() - interval '1 day', 'scheduled', 1, 0, 1, now(), now())",
            cid,
            tid,
            "a" * 64,
        )
        row_id = "73000000-0000-0000-0000-000000000044"
        await connection.execute(
            "INSERT INTO metaedu.agent_conversation_purges "
            "(id, tenant_id, conversation_id, purge_revision, state, "
            "registry_digest, registry_snapshot, retention_policy_snapshot, "
            "retention_policy_digest, hold_revision_snapshot, lease_epoch, "
            "scheduled_at, revision, created_at, updated_at) "
            "VALUES ($1, $2, $3, 1, 'scheduled', $4, $5::jsonb, $6::jsonb, "
            "$7, 0, 0, now(), 1, now(), now())",
            row_id,
            tid,
            cid,
            "b" * 64,
            '[{"owner_key": "workspace.core.v1", "owner_version": 1, '
            '"capability_digest": "cccccccccccccccccccccccccccccccccccccccc'
            'cccccccccccccccccccccccccccc"}]',
            '{"conversation_recovery_days": 30}',
            "d" * 64,
        )
        return row_id
    finally:
        await connection.close()


async def _lease_carrier_row_expiry_null(row_id: str) -> bool:
    connection = await asyncpg.connect(_db_url())
    try:
        return (
            await connection.fetchval(
                "SELECT lease_expires_at IS NULL FROM "
                "metaedu.agent_conversation_purges WHERE id = $1",
                row_id,
            )
            is True
        )
    finally:
        await connection.close()


def test_042_lease_carrier_downgrade_upgrade_round_trip():
    """SCH-14：migration 042 往返——head 有 nullable 列 + partial index；
    既有行 lease_expires_at 全 NULL（零 backfill、不伪造历史租约）；
    downgrade 先删 index 后删列（行数据保留）；再 upgrade 无损恢复。

    mutation（SCH-14）：042 upgrade 给列加 backfill/非空 server_default ->
    「既有行 NULL」断言转红。
    """
    schema = asyncio.run(_lease_carrier_schema())
    assert schema == {"column": True, "index": True}, (
        "head 状态应有 lease_expires_at 列 + ix_agent_purge_lease_active"
    )

    row_id = asyncio.run(_seed_lease_carrier_row())
    try:
        _run_alembic("downgrade", "041_run_event_ref_tombstone")
        assert asyncio.run(_lease_carrier_schema()) == {
            "column": False,
            "index": False,
        }, "downgrade 应删列 + 删 partial index"
        _run_alembic("upgrade", "head")
        schema = asyncio.run(_lease_carrier_schema())
        assert schema == {"column": True, "index": True}, "再 upgrade 恢复"
        assert asyncio.run(_lease_carrier_row_expiry_null(row_id)) is True, (
            "零 backfill：既有行 lease_expires_at 必须全 NULL（未认领）"
        )
    finally:
        _run_alembic("upgrade", "head")


# ---------------------------------------------------------------------------
# R1-S6 S6-I1: migration 043 retention guard 往返 + 白名单行为（P0-1 裁决）
# ---------------------------------------------------------------------------


async def _seed_guard_run() -> tuple:
    """种子 queued run + FK 链（definition + profile），返回 (run_id, tid)。"""
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
            "(id, tenant_id, definition_key, version, status, definition_digest, "
            "created_by, created_at) "
            "VALUES ($1, $2, $3, 1, 'published', $4, $2, now())",
            def_id, tid, f"def-{tid}", digest,
        )
        await connection.execute(
            "INSERT INTO metaedu.agent_runtime_profiles "
            "(id, tenant_id, profile_key, runtime_kind, adapter_key, config_digest, "
            "capability_digest, enabled, revision, created_at, updated_at) "
            "VALUES ($1, $2, $3, 'compatibility', 'compatibility', $4, $4, "
            "true, 1, now(), now())",
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
            "'not_required', $2, 'present', NULL, $1, '{}'::jsonb, '{}'::jsonb, "
            "'{}'::jsonb, '{}'::jsonb)",
            run_id, tid, def_id, prof_id, digest,
        )
        return run_id, tid
    finally:
        await connection.close()


async def _cleanup_guard_run(tid) -> None:
    connection = await asyncpg.connect(_db_url())
    try:
        # guard 拒绝 live 行 DELETE——用 TRUNCATE（同 _clean_tombstone_tables 模式；
        # 本文件独立运行，测试后清理 agent_run_events 全表）。
        await connection.execute("TRUNCATE TABLE metaedu.agent_run_events")
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


async def _insert_guard_event(
    run_id, tid, *, seq=1, payload_state="inline", ref=None
) -> None:
    """插入 event 行。inline 默认正文非空；external 需 ref；tombstone 态 inline NULL。
    与 ``_seed_guard_run`` 一致：run.conversation_id == run.correlation_id == run_id。"""
    connection = await asyncpg.connect(_db_url())
    inline_json = None
    if payload_state == "inline":
        inline = {"summary": "guard"}
        ref = None
        inline_json = json.dumps(inline)
    try:
        await connection.execute(
            "INSERT INTO metaedu.agent_run_events "
            "(id, tenant_id, conversation_id, run_id, seq, event_type, schema_version, "
            "occurred_at, persisted_at, visibility, classification, payload_inline, "
            "payload_ref, payload_state, payload_digest, payload_size, media_type, "
            "expires_at, correlation_id, causation_id) "
            "VALUES (gen_random_uuid(), $1, $2, $2, $3, 'tool.completed', 1, "
            "now(), now(), 'user', 'public', $4::jsonb, $5, $6, $7, 1, "
            "'application/json', NULL, $2, NULL)",
            tid, run_id, seq, inline_json, ref, payload_state, "b" * 64,
        )
    finally:
        await connection.close()


async def _try_guard_update(run_id, tid, *, seq, new_state, clear_inline=True) -> bool:
    """尝试 guard 受控 UPDATE；返回是否被放行（True=放行，False=guard RAISE）。"""
    connection = await asyncpg.connect(_db_url())
    try:
        try:
            if clear_inline:
                await connection.execute(
                    "UPDATE metaedu.agent_run_events "
                    "SET payload_inline = NULL, payload_state = $1 "
                    "WHERE tenant_id=$2 AND run_id=$3 AND seq=$4",
                    new_state, tid, run_id, seq,
                )
            else:
                await connection.execute(
                    "UPDATE metaedu.agent_run_events SET payload_state = $1 "
                    "WHERE tenant_id=$2 AND run_id=$3 AND seq=$4",
                    new_state, tid, run_id, seq,
                )
            return True
        except asyncpg.exceptions.ObjectNotInPrerequisiteStateError:
            return False
    finally:
        await connection.close()


async def _try_guard_delete(run_id, tid, *, seq) -> bool:
    connection = await asyncpg.connect(_db_url())
    try:
        try:
            await connection.execute(
                "DELETE FROM metaedu.agent_run_events "
                "WHERE tenant_id=$1 AND run_id=$2 AND seq=$3",
                tid, run_id, seq,
            )
            return True
        except asyncpg.exceptions.ObjectNotInPrerequisiteStateError:
            return False
    finally:
        await connection.close()


def test_043_retention_guard_downgrade_upgrade_round_trip():
    """043 往返：head（043）放行已 tombstone 行 DELETE + expired/archived tombstone
    UPDATE；downgrade 到 042 还原 041 白名单（DELETE 与 non-redacted 写均 RAISE）；
    upgrade 回 head 恢复 043 行为。守卫只作用于新写，downgrade 无条件可逆。"""
    run_id, tid = asyncio.run(_seed_guard_run())
    try:
        # 强制重放当前迁移文件版本的 043（mutation kill 的 clean 阶段依赖此重置——
        # 变异期间安装的 guard 必须被真实文件覆盖）。seed 不受 042 往返影响。
        _run_alembic("downgrade", "042_purge_lease_carrier")
        _run_alembic("upgrade", "head")
        # head：043 放行 inline → expired。
        asyncio.run(_insert_guard_event(run_id, tid, seq=1, payload_state="inline"))
        assert asyncio.run(
            _try_guard_update(run_id, tid, seq=1, new_state="expired")
        ) is True, "head 应放行 inline → expired（043(a) 分支 1）"
        # 已 tombstone（expired）行 DELETE 放行。
        assert asyncio.run(
            _try_guard_delete(run_id, tid, seq=1)
        ) is True, "head 应放行已 tombstone 行 DELETE（043(b)）"

        # downgrade 到 042（041 白名单）：DELETE 与 expired 写均 RAISE。
        _run_alembic("downgrade", "042_purge_lease_carrier")
        asyncio.run(_insert_guard_event(run_id, tid, seq=2, payload_state="inline"))
        assert asyncio.run(
            _try_guard_update(run_id, tid, seq=2, new_state="expired")
        ) is False, "041 白名单拒绝 expired 写（redacted-only）"
        assert asyncio.run(
            _try_guard_update(run_id, tid, seq=2, new_state="redacted")
        ) is True, "041 白名单放行 redacted 写"
        assert asyncio.run(
            _try_guard_delete(run_id, tid, seq=2)
        ) is False, "041 白名单拒绝 DELETE（043 才开 DELETE 洞）"

        # upgrade 回 head：043 行为恢复。
        _run_alembic("upgrade", "head")
        assert asyncio.run(
            _try_guard_delete(run_id, tid, seq=2)
        ) is True, "upgrade 回 head 恢复已 tombstone 行 DELETE"
        # M-043-2 判别：upgrade 重放 043 文件后，expired/archived 写仍放行
        # （widening 被还原 → 本断言转红）。
        asyncio.run(_insert_guard_event(run_id, tid, seq=3, payload_state="inline"))
        assert asyncio.run(
            _try_guard_update(run_id, tid, seq=3, new_state="expired")
        ) is True, "upgrade 后 043 仍放行 expired 写（widening 未还原）"
    finally:
        _run_alembic("upgrade", "head")
        asyncio.run(_cleanup_guard_run(tid))


def test_043_guard_rejects_live_delete_and_non_tombstone_write():
    """043 不洞开：live（inline）行 DELETE 仍 RAISE；inline 行转非 tombstone
    （非 redacted/expired/archived）仍 RAISE。"""
    run_id, tid = asyncio.run(_seed_guard_run())
    try:
        asyncio.run(_insert_guard_event(run_id, tid, seq=1, payload_state="inline"))
        assert asyncio.run(
            _try_guard_delete(run_id, tid, seq=1)
        ) is False, "live 行 DELETE 必须 RAISE"
        # 清正文但转回 'inline'（非 tombstone 态）→ RAISE。
        assert asyncio.run(
            _try_guard_update(run_id, tid, seq=1, new_state="inline")
        ) is False, "non-tombstone 写必须 RAISE"
        # 其余列变化（顺带改 media_type）→ RAISE。
        assert asyncio.run(
            _try_guard_update_with_extra(run_id, tid, seq=1, new_state="expired")
        ) is False, "其余列变化必须 RAISE"
    finally:
        asyncio.run(_cleanup_guard_run(tid))


async def _try_guard_update_with_extra(run_id, tid, *, seq, new_state) -> bool:
    """UPDATE 同时改动 media_type（其余列变化）→ guard 应 RAISE。"""
    connection = await asyncpg.connect(_db_url())
    try:
        try:
            await connection.execute(
                "UPDATE metaedu.agent_run_events "
                "SET payload_inline = NULL, payload_state = $1, media_type = 'text/plain' "
                "WHERE tenant_id=$2 AND run_id=$3 AND seq=$4",
                new_state, tid, run_id, seq,
            )
            return True
        except asyncpg.exceptions.ObjectNotInPrerequisiteStateError:
            return False
    finally:
        await connection.close()


def test_043_guard_external_state_only_and_ref_branch():
    """043 分支 2：external 行仅 state 变化（转 expired）放行且 ref 保留；分支 3
    （041）ref 清除仍 redacted-only——转 expired 清除 ref 必须 RAISE。"""
    run_id, tid = asyncio.run(_seed_guard_run())
    try:
        asyncio.run(
            _insert_guard_event(run_id, tid, seq=1, payload_state="external", ref="ext-1")
        )
        # 仅 state → expired（ref 保留）：放行。
        assert asyncio.run(
            _try_guard_update(run_id, tid, seq=1, new_state="expired", clear_inline=False)
        ) is True, "043(a) 分支 2 放行 external state-only"
        # 清 ref + 转 expired（非 redacted）→ 分支 3 要求 redacted-only → RAISE。
        assert asyncio.run(
            _try_guard_update_clear_ref(run_id, tid, seq=1, new_state="expired")
        ) is False, "ref 清除保持 redacted-only，expired 必须 RAISE"
        # 清 ref + 转 redacted → 放行（041 分支 3）。
        assert asyncio.run(
            _try_guard_update_clear_ref(run_id, tid, seq=1, new_state="redacted")
        ) is True, "ref 清除 + redacted 放行（041 分支 3）"
        # 有 ref 的已 tombstone 行不可 DELETE（043(b) 要求 payload_ref IS NULL）。
        asyncio.run(
            _insert_guard_event(run_id, tid, seq=2, payload_state="external", ref="ext-2")
        )
        assert asyncio.run(
            _try_guard_update(run_id, tid, seq=2, new_state="redacted", clear_inline=False)
        ) is True
        assert asyncio.run(
            _try_guard_delete(run_id, tid, seq=2)
        ) is False, "ref-bearing 行 DELETE 必须 RAISE（payload_ref 未清不满足 043(b)）"
    finally:
        asyncio.run(_cleanup_guard_run(tid))


async def _try_guard_update_clear_ref(run_id, tid, *, seq, new_state) -> bool:
    connection = await asyncpg.connect(_db_url())
    try:
        try:
            await connection.execute(
                "UPDATE metaedu.agent_run_events "
                "SET payload_ref = NULL, payload_state = $1 "
                "WHERE tenant_id=$2 AND run_id=$3 AND seq=$4",
                new_state, tid, run_id, seq,
            )
            return True
        except asyncpg.exceptions.ObjectNotInPrerequisiteStateError:
            return False
    finally:
        await connection.close()
