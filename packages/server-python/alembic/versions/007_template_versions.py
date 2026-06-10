"""create template_versions table

Revision ID: 007_template_versions
Revises: 9466ea6e5d33
Create Date: 2026-06-10

REQ-002-2: template version snapshot per Q2 decision
(full retention + pagination, no auto-cleanup).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = '007_template_versions'
down_revision = '9466ea6e5d33'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'template_versions',
        sa.Column('id', UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('template_id', UUID(), nullable=False),
        sa.Column('tenant_id', UUID(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('doc_types', ARRAY(sa.String(length=50)), nullable=False),
        sa.Column('fields', JSONB(), nullable=False),
        sa.Column('ai_prompt', sa.Text(), nullable=True),
        sa.Column('ai_context', sa.Text(), nullable=True),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_id', 'version_number', name='uq_template_versions_template_version'),
        sa.ForeignKeyConstraint(['template_id'], ['metaedu.templates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['metaedu.tenants.id']),
    )
    op.create_index('ix_template_versions_template_id', 'template_versions', ['template_id'])
    op.create_index('ix_template_versions_snapshot_at', 'template_versions', ['snapshot_at'])


def downgrade() -> None:
    op.drop_table('template_versions')
