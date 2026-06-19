"""v2 conversations and messages tables.

Revision ID: 008
Revises: 007
Create Date: 2026-06-17
"""
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations (
            id                 UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            contact_phone      VARCHAR   NOT NULL REFERENCES contacts(phone_number),
            state              VARCHAR   NOT NULL DEFAULT 'open',
            started_at         TIMESTAMP NOT NULL DEFAULT NOW(),
            closed_at          TIMESTAMP,
            message_count      INTEGER   NOT NULL DEFAULT 0,
            quality_score      FLOAT,
            emotional_tone     VARCHAR,
            close_condition    JSONB,
            summary            TEXT,
            unresolved_threads JSONB     NOT NULL DEFAULT '[]',
            updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_conversations_contact ON conversations(contact_phone)"
    )
    op.execute(
        "CREATE INDEX idx_conversations_open "
        "ON conversations(contact_phone) WHERE state = 'open'"
    )

    op.execute(
        """
        CREATE TABLE messages (
            id                  UUID      PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id     UUID      NOT NULL REFERENCES conversations(id),
            contact_phone       VARCHAR   NOT NULL REFERENCES contacts(phone_number),
            role                VARCHAR   NOT NULL,
            content             TEXT      NOT NULL,
            language            VARCHAR,
            sent_at             TIMESTAMP NOT NULL DEFAULT NOW(),
            was_deferred        BOOLEAN   NOT NULL DEFAULT FALSE,
            defer_duration      INTEGER,
            whatsapp_message_id VARCHAR   UNIQUE
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_messages_conversation ON messages(conversation_id)"
    )
    op.execute(
        "CREATE INDEX idx_messages_contact ON messages(contact_phone, sent_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages CASCADE")
    op.execute("DROP TABLE IF EXISTS conversations CASCADE")
