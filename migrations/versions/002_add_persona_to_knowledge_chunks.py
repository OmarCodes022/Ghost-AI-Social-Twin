"""Add persona column to knowledge_chunks.

Allows multiple identity profiles (e.g. 'default' = Omar, 'lea' = French girl persona).
Contacts are assigned a persona via voice_profile.persona; the response_generator
filters identity chunks by persona when building the system prompt.

Revision ID: 002
Revises: 001
Create Date: 2026-03-12
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_chunks "
        "ADD COLUMN persona VARCHAR(50) NOT NULL DEFAULT 'default'"
    )
    op.execute(
        "CREATE INDEX idx_knowledge_chunks_persona ON knowledge_chunks(persona)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_knowledge_chunks_persona")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN persona")
