"""v2 memories table with vector(1024) for Voyage-3 multilingual embeddings.

category vocabulary: fact | emotional | pattern | negative | inside_joke |
                     observation | identity | behavioral

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
        """
        CREATE TABLE memories (
            id                  UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone       VARCHAR   REFERENCES contacts(phone_number),
            category            VARCHAR   NOT NULL,
            content             TEXT      NOT NULL,
            language            VARCHAR,
            embedding           vector(1024),
            importance          FLOAT     NOT NULL DEFAULT 0.5,
            created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by          VARCHAR   NOT NULL,
            source_conversation UUID      REFERENCES conversations(id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_memories_embedding "
        "ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.execute(
        "CREATE INDEX idx_memories_contact ON memories(contact_phone, importance DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memories CASCADE")
