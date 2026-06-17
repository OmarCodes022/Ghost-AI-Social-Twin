"""v2 memories table with vector(1024) for Voyage-3 multilingual embeddings.

Revision ID: 011
Revises: 010
Create Date: 2026-06-17
"""
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE memory_type AS ENUM ('episodic', 'semantic', 'procedural')"
    )
    op.execute(
        "CREATE TYPE memory_source AS ENUM ('conversation', 'reflection', 'manual')"
    )

    op.execute(
        """
        CREATE TABLE memories (
            id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone VARCHAR       REFERENCES contacts(phone_number),
            memory_type   memory_type   NOT NULL,
            content       TEXT          NOT NULL,
            embedding     TEXT,
            importance    FLOAT         NOT NULL DEFAULT 0.5,
            source        memory_source NOT NULL DEFAULT 'conversation',
            access_count  INTEGER       NOT NULL DEFAULT 0,
            accessed_at   TIMESTAMP,
            created_at    TIMESTAMP     NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "ALTER TABLE memories ALTER COLUMN embedding TYPE vector(1024) "
        "USING embedding::vector(1024)"
    )
    op.execute(
        "CREATE INDEX idx_memories_embedding "
        "ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX idx_memories_contact ON memories(contact_phone)"
    )
    op.execute(
        "CREATE INDEX idx_memories_importance ON memories(importance DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memories CASCADE")
    op.execute("DROP TYPE IF EXISTS memory_source")
    op.execute("DROP TYPE IF EXISTS memory_type")
