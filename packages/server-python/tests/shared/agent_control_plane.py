from sqlalchemy import text

AGENT_CONTROL_PLANE_CLEAN_SQL = """
TRUNCATE TABLE
    metaedu.agent_conversation_legal_holds,
    metaedu.agent_conversation_purge_owners,
    metaedu.agent_conversation_purges,
    metaedu.agent_erasure_fences,
    metaedu.agent_compatibility_outputs,
    metaedu.agent_run_events,
    metaedu.agent_turn_inputs,
    metaedu.agent_execution_inbox,
    metaedu.agent_execution_outbox,
    metaedu.agent_runs,
    metaedu.agent_runtime_session_bindings,
    metaedu.agent_runtime_profiles,
    metaedu.agent_definition_versions,
    metaedu.agent_workspace_inbox,
    metaedu.agent_workspace_outbox,
    metaedu.agent_message_parts,
    metaedu.agent_messages,
    metaedu.agent_conversation_user_state,
    metaedu.agent_conversations
"""


async def clean_agent_control_plane(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_CONTROL_PLANE_CLEAN_SQL))
