from sqlalchemy import text

# agent 控制面表（按依赖序）。注意：部分表由较新 migration 创建（如
# agent_transport_scope_reconcile / agent_external_object_refs 由 040 创建，
# agent_compatibility_outputs 由 033 创建）。迁移 round-trip 测试会把库降到
# 更早版本，此时这些表不存在；autouse fixture 的 teardown 若对不存在的表
# TRUNCATE 会报 UndefinedTableError，掩盖真实结果并污染后续测试。故清理时
# 逐表按 to_regclass 判定存在性，仅 TRUNCATE 当前存在的表。
_AGENT_CONTROL_PLANE_TABLES = (
    "agent_conversation_legal_holds",
    "agent_conversation_purge_owners",
    "agent_conversation_purges",
    "agent_erasure_fences",
    "agent_compatibility_outputs",
    "agent_transport_scope_reconcile",
    "agent_external_object_refs",
    "agent_run_events",
    "agent_turn_inputs",
    "agent_execution_inbox",
    "agent_execution_outbox",
    "agent_runs",
    "agent_runtime_session_bindings",
    "agent_runtime_profiles",
    "agent_definition_versions",
    "agent_workspace_inbox",
    "agent_workspace_outbox",
    "agent_message_parts",
    "agent_messages",
    "agent_conversation_user_state",
    "agent_conversations",
)


async def clean_agent_control_plane(engine) -> None:
    async with engine.begin() as connection:
        rows = await connection.execute(
            text(
                "SELECT t.name, to_regclass('metaedu.' || t.name) AS r "
                "FROM unnest(CAST(:names AS text[])) AS t(name)"
            ),
            {"names": list(_AGENT_CONTROL_PLANE_TABLES)},
        )
        present = [name for name, reg in rows.all() if reg is not None]
        if not present:
            return
        sql = "TRUNCATE TABLE " + ", ".join(f"metaedu.{t}" for t in present)
        await connection.execute(text(sql))
