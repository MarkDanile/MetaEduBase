"""create REQ-047 E0 execution identity and Runtime binding catalog

Revision ID: 029_agent_execution_identity
Revises: 028_agent_workspace_store
Create Date: 2026-07-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "029_agent_execution_identity"
down_revision: str | None = "028_agent_workspace_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_definition_versions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("definition_key", sa.String(150), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("definition_digest", sa.String(64), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_agent_definition_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "definition_key",
            "version",
            name="uq_agent_definition_key_version",
        ),
        sa.CheckConstraint("version >= 1", name="ck_agent_definition_version"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'retired')",
            name="ck_agent_definition_status",
        ),
        sa.CheckConstraint(
            "char_length(definition_digest) = 64",
            name="ck_agent_definition_digest",
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_definition_catalog",
        "agent_definition_versions",
        ["tenant_id", "status", "definition_key", "version"],
        schema="metaedu",
    )

    op.create_table(
        "agent_runtime_profiles",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("profile_key", sa.String(150), nullable=False),
        sa.Column("runtime_kind", sa.String(50), nullable=False),
        sa.Column("adapter_key", sa.String(100), nullable=False),
        sa.Column("config_digest", sa.String(64), nullable=False),
        sa.Column("capability_digest", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_agent_runtime_profile_tenant_id"
        ),
        sa.UniqueConstraint(
            "tenant_id", "profile_key", name="uq_agent_runtime_profile_key"
        ),
        sa.CheckConstraint(
            "char_length(config_digest) = 64 AND "
            "char_length(capability_digest) = 64",
            name="ck_agent_runtime_profile_digests",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_agent_runtime_profile_revision"
        ),
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_runtime_profile_resolve",
        "agent_runtime_profiles",
        ["tenant_id", "enabled", "profile_key"],
        schema="metaedu",
    )

    op.create_table(
        "agent_runtime_session_bindings",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_profile_id", UUID(as_uuid=True), nullable=False),
        sa.Column("runtime_session_ref", sa.String(500), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="creating"
        ),
        sa.Column("current_epoch", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "next_expected_runtime_seq",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "acked_through_runtime_seq",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("active_stream_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "stream_lease_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "id", name="uq_agent_runtime_binding_tenant_id"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "runtime_profile_id"],
            [
                "metaedu.agent_runtime_profiles.tenant_id",
                "metaedu.agent_runtime_profiles.id",
            ],
            name="fk_agent_runtime_binding_profile",
        ),
        sa.CheckConstraint(
            "status IN ('creating', 'active', 'resume_required', 'closed', 'invalid')",
            name="ck_agent_runtime_binding_status",
        ),
        sa.CheckConstraint(
            "current_epoch >= 1 AND next_expected_runtime_seq >= 1 AND "
            "acked_through_runtime_seq >= 0 AND "
            "next_expected_runtime_seq = acked_through_runtime_seq + 1",
            name="ck_agent_runtime_binding_cursor",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_agent_runtime_binding_revision"
        ),
        sa.CheckConstraint(
            "(active_stream_id IS NULL AND stream_lease_expires_at IS NULL) OR "
            "(active_stream_id IS NOT NULL AND stream_lease_expires_at IS NOT NULL)",
            name="ck_agent_runtime_binding_stream_lease",
        ),
        sa.CheckConstraint(
            "runtime_session_ref IS NULL OR char_length(runtime_session_ref) > 0",
            name="ck_agent_runtime_binding_session_ref",
        ),
        schema="metaedu",
    )
    op.create_index(
        "uq_agent_runtime_binding_session_ref",
        "agent_runtime_session_bindings",
        ["tenant_id", "runtime_profile_id", "runtime_session_ref"],
        unique=True,
        schema="metaedu",
        postgresql_where=sa.text("runtime_session_ref IS NOT NULL"),
    )
    op.create_index(
        "ix_agent_runtime_binding_conversation",
        "agent_runtime_session_bindings",
        ["tenant_id", "conversation_id", "status", "updated_at"],
        schema="metaedu",
    )
    op.create_index(
        "ix_agent_runtime_binding_stream_lease",
        "agent_runtime_session_bindings",
        ["tenant_id", "stream_lease_expires_at"],
        schema="metaedu",
        postgresql_where=sa.text("active_stream_id IS NOT NULL"),
    )

    op.execute(
        """
        CREATE FUNCTION metaedu.guard_agent_runtime_binding_profile()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE
            profile_runtime_kind text;
        BEGIN
            SELECT runtime_kind INTO profile_runtime_kind
            FROM metaedu.agent_runtime_profiles
            WHERE tenant_id = NEW.tenant_id AND id = NEW.runtime_profile_id;
            IF profile_runtime_kind = 'compatibility' THEN
                RAISE EXCEPTION 'compatibility profile cannot own a Runtime binding'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_runtime_binding_profile
        BEFORE INSERT OR UPDATE OF tenant_id, runtime_profile_id
        ON metaedu.agent_runtime_session_bindings
        FOR EACH ROW EXECUTE FUNCTION metaedu.guard_agent_runtime_binding_profile()
        """
    )

    op.execute(
        """
        CREATE FUNCTION metaedu.guard_agent_definition_version_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
               OR OLD.id IS DISTINCT FROM NEW.id
               OR OLD.definition_key IS DISTINCT FROM NEW.definition_key
               OR OLD.version IS DISTINCT FROM NEW.version
               OR (OLD.status IN ('published', 'retired') AND
                   OLD.definition_digest IS DISTINCT FROM NEW.definition_digest)
               OR (OLD.status = 'published' AND NEW.status NOT IN ('published', 'retired'))
               OR (OLD.status = 'retired' AND NEW.status <> 'retired') THEN
                RAISE EXCEPTION 'published agent definition identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_definition_version_immutable
        BEFORE UPDATE ON metaedu.agent_definition_versions
        FOR EACH ROW EXECUTE FUNCTION
            metaedu.guard_agent_definition_version_immutable()
        """
    )
    op.execute(
        """
        CREATE FUNCTION metaedu.guard_agent_runtime_profile_immutable()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.tenant_id IS DISTINCT FROM NEW.tenant_id
               OR OLD.id IS DISTINCT FROM NEW.id
               OR OLD.profile_key IS DISTINCT FROM NEW.profile_key
               OR OLD.runtime_kind IS DISTINCT FROM NEW.runtime_kind
               OR OLD.adapter_key IS DISTINCT FROM NEW.adapter_key
               OR OLD.config_digest IS DISTINCT FROM NEW.config_digest
               OR OLD.capability_digest IS DISTINCT FROM NEW.capability_digest THEN
                RAISE EXCEPTION 'published runtime profile identity is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_agent_runtime_profile_immutable
        BEFORE UPDATE ON metaedu.agent_runtime_profiles
        FOR EACH ROW EXECUTE FUNCTION metaedu.guard_agent_runtime_profile_immutable()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_agent_runtime_binding_profile "
        "ON metaedu.agent_runtime_session_bindings"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS metaedu.guard_agent_runtime_binding_profile()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_agent_runtime_profile_immutable "
        "ON metaedu.agent_runtime_profiles"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS metaedu.guard_agent_runtime_profile_immutable()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_agent_definition_version_immutable "
        "ON metaedu.agent_definition_versions"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS metaedu.guard_agent_definition_version_immutable()"
    )
    op.drop_index(
        "ix_agent_runtime_binding_stream_lease",
        table_name="agent_runtime_session_bindings",
        schema="metaedu",
    )
    op.drop_index(
        "ix_agent_runtime_binding_conversation",
        table_name="agent_runtime_session_bindings",
        schema="metaedu",
    )
    op.drop_index(
        "uq_agent_runtime_binding_session_ref",
        table_name="agent_runtime_session_bindings",
        schema="metaedu",
    )
    op.drop_table("agent_runtime_session_bindings", schema="metaedu")
    op.drop_index(
        "ix_agent_runtime_profile_resolve",
        table_name="agent_runtime_profiles",
        schema="metaedu",
    )
    op.drop_table("agent_runtime_profiles", schema="metaedu")
    op.drop_index(
        "ix_agent_definition_catalog",
        table_name="agent_definition_versions",
        schema="metaedu",
    )
    op.drop_table("agent_definition_versions", schema="metaedu")
