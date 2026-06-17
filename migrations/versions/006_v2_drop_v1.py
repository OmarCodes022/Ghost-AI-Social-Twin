"""Drop all v1 tables and types to make way for v2 schema.

Revision ID: 006
Revises: 005
Create Date: 2026-06-17
"""
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_traces CASCADE")
    op.execute("DROP TABLE IF EXISTS escalations CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS mood_states CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
    op.execute("DROP TABLE IF EXISTS ghost_state CASCADE")
    op.execute("DROP TABLE IF EXISTS contacts CASCADE")

    op.execute("DROP TYPE IF EXISTS escalation_resolution")
    op.execute("DROP TYPE IF EXISTS knowledge_source")
    op.execute("DROP TYPE IF EXISTS knowledge_category")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS arc_state")


def downgrade() -> None:
    pass
